"""V10 Paper Trader — tests (Phase 23+ CEO suite).

Cible R7 : 15 tests verts minimum.

Doctrine V10 :
  R2 additif pur, R6 fail-open, R7, R8 R8-calibrated, R9 audit, R10 paper_only.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v10.v10_paper_trader import (
    MICRO_LOT,
    PIP_VALUE_PER_LOT,
    SPREAD_PIPS,
    GATE_PASSED_PAIRS_M30,
    BASELINE_WR_M30,
    PaperTrade,
    PaperTraderReport,
    simulate_paper_trade,
    _compute_kpis,
    run_paper_trader,
)


# ─────────────────────────────────────────────────────────────────────
# CONSTANTS (4)
# ─────────────────────────────────────────────────────────────────────

def test_constants_micro_lot():
    """MICRO_LOT = 0.01 (R10 paper-only)."""
    assert MICRO_LOT == 0.01


def test_constants_pip_values_complete():
    """PIP_VALUE_PER_LOT contient les 6 paires."""
    assert set(PIP_VALUE_PER_LOT.keys()) == {
        "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY",
    }


def test_constants_spreads_complete():
    """SPREAD_PIPS contient les 6 paires."""
    assert set(SPREAD_PIPS.keys()) == {
        "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY",
    }


def test_constants_gate_passed_pairs_m30():
    """GATE_PASSED_PAIRS_M30 = 4 paires Phase 21."""
    assert len(GATE_PASSED_PAIRS_M30) == 4
    assert "GBPUSD" in GATE_PASSED_PAIRS_M30


# ─────────────────────────────────────────────────────────────────────
# SIMULATE PAPER TRADE (5)
# ─────────────────────────────────────────────────────────────────────

def test_simulate_paper_trade_bullish_win():
    """Bullish + WR=1.0 → win, pnl > 0."""
    trade = simulate_paper_trade(
        pair="EURUSD", signal="BULLISH", baseline_wr=1.0, rng_seed=42
    )
    assert trade.is_win == 1
    assert trade.pnl_usd > 0
    assert trade.lot_size == MICRO_LOT


def test_simulate_paper_trade_bearish_loss():
    """Bearish + WR=0.0 → loss, pnl < 0."""
    trade = simulate_paper_trade(
        pair="EURUSD", signal="BEARISH", baseline_wr=0.0, rng_seed=42
    )
    assert trade.is_win == 0
    assert trade.pnl_usd < 0


def test_simulate_paper_trade_neutral_degraded_wr():
    """NEUTRAL → effective_wr = baseline_wr × 0.85 (R9 honest)."""
    trade = simulate_paper_trade(
        pair="GBPUSD", signal="NEUTRAL", baseline_wr=0.50, rng_seed=42
    )
    assert trade.audit["neutral_penalty_applied"] is True
    assert trade.audit["effective_wr"] == round(0.50 * 0.85, 4)


def test_simulate_paper_trade_usdjpy_pip_value():
    """USDJPY pip_value = 6.67 (JPY pairs special)."""
    assert PIP_VALUE_PER_LOT["USDJPY"] == 6.67


def test_simulate_paper_trade_spread_deducted():
    """Spread déduit du pnl brut."""
    trade = simulate_paper_trade(
        pair="EURUSD", signal="BULLISH", baseline_wr=1.0, rng_seed=42
    )
    # PnL brut = 8.0p, spread = 1.0p → pnl_net = 7.0p
    assert trade.pips_net_of_spread == round(8.0 - 1.0, 4)


# ─────────────────────────────────────────────────────────────────────
# COMPUTE KPIS (3)
# ─────────────────────────────────────────────────────────────────────

def test_compute_kpis_empty():
    """Empty trades → KPIs à 0."""
    kpis = _compute_kpis([])
    assert kpis["n_trades"] == 0
    assert kpis["wr_pct"] == 0.0


def test_compute_kpis_all_wins():
    """Tous wins → wr=100%."""
    trades = [
        PaperTrade(pair="EURUSD", pips_net_of_spread=10.0, is_win=1)
        for _ in range(10)
    ]
    kpis = _compute_kpis(trades)
    assert kpis["wr_pct"] == 100.0
    assert kpis["pnl_pips_total"] == 100.0


def test_compute_kpis_max_dd():
    """Max DD = max drawdown cumulé."""
    trades = [
        PaperTrade(pair="EURUSD", pips_net_of_spread=10.0, is_win=1),
        PaperTrade(pair="EURUSD", pips_net_of_spread=-5.0, is_win=0),
        PaperTrade(pair="EURUSD", pips_net_of_spread=-5.0, is_win=0),
    ]
    kpis = _compute_kpis(trades)
    # Cumul : 10, 5, 0. Peak=10, max DD = 10
    assert kpis["max_dd_pips"] == 10.0


# ─────────────────────────────────────────────────────────────────────
# RUN PAPER TRADER (3)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, timeframe TEXT, bar_time INTEGER,
            close REAL, is_closed_bar INTEGER,
            force_usd REAL, force_gbp REAL, force_eur REAL,
            force_jpy REAL, force_cad REAL, force_chf REAL,
            force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT,
            compression_extension_intensite TEXT
        )
    """)
    con.commit()
    con.close()
    yield path
    Path(path).unlink(missing_ok=True)


def _populate_mtf(db_path, pair, n=30):
    con = sqlite3.connect(db_path)
    for tf in ("M30", "H1", "H4", "D1"):
        for i in range(n):
            con.execute("""
                INSERT INTO forces_snapshots (
                    symbol, timeframe, bar_time, close, is_closed_bar,
                    force_usd, force_gbp, force_eur, force_jpy, force_cad,
                    force_chf, force_aud, force_nzd,
                    compression_extension_etat, compression_extension_intensite
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPRESSION', 'MOYEN')
            """, (pair, tf, 1783111080 + i * 1800, 1.1 + i * 0.001,
                  30.0, 50.0, 70.0, 50.0, 50.0, 50.0, 50.0, 50.0))
    con.commit()
    con.close()


def test_run_paper_trader_paper_only_true(tmp_db):
    """paper_only = True OBLIGATOIRE (R10)."""
    _populate_mtf(tmp_db, "GBPUSD", n=30)
    rep = run_paper_trader(
        tmp_db,
        pairs=("GBPUSD",),
        n_trades_per_pair=10,
        rng_seed=42,
    )
    assert rep.paper_only is True
    assert rep.micro_lot == MICRO_LOT


def test_run_paper_trader_n_trades(tmp_db):
    """30 trades × N paires (default 30)."""
    _populate_mtf(tmp_db, "GBPUSD", n=30)
    _populate_mtf(tmp_db, "AUDUSD", n=30)
    rep = run_paper_trader(
        tmp_db,
        pairs=("GBPUSD", "AUDUSD"),
        n_trades_per_pair=30,
        rng_seed=42,
    )
    assert rep.n_pairs_tested == 2
    assert rep.n_trades_per_pair == 30
    assert len(rep.trades) == 60


def test_run_paper_trader_global_kpis(tmp_db):
    """KPIs globaux présents (WR, PnL, max DD, Sharpe)."""
    _populate_mtf(tmp_db, "GBPUSD", n=30)
    rep = run_paper_trader(
        tmp_db,
        pairs=("GBPUSD",),
        n_trades_per_pair=20,
        rng_seed=42,
    )
    assert "wr_pct" in rep.global_kpis
    assert "pnl_pips_total" in rep.global_kpis
    assert "pnl_usd_total" in rep.global_kpis
    assert "max_dd_pips" in rep.global_kpis
    assert "sharpe_ratio" in rep.global_kpis


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES (2)
# ─────────────────────────────────────────────────────────────────────

def test_paper_trade_default_construction():
    """PaperTrade() défaut : champs initialisés."""
    t = PaperTrade()
    assert t.pair == ""
    assert t.pnl_usd == 0.0
    assert t.is_win == 0
    assert t.lot_size == MICRO_LOT  # default MICRO_LOT


def test_paper_trader_report_serializable(tmp_db):
    """Report JSON-sérialisable (R9 audit)."""
    _populate_mtf(tmp_db, "GBPUSD", n=30)
    rep = run_paper_trader(
        tmp_db, pairs=("GBPUSD",), n_trades_per_pair=10, rng_seed=42,
    )
    j = json.dumps(rep.as_dict())
    assert "paper_only" in j
    assert "micro_lot" in j
    assert "global_kpis" in j
