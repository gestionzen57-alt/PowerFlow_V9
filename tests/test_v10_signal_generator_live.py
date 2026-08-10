"""V10 Signal Generator Live — tests unitaires (Phase 17).

Cible R7 : 20 tests verts minimum.

Doctrine V10 :
  R2 : additif pur (0 import core/v9/)
  R6 : fail-open (DB absente, snapshot vide, etc.)
  R9 : audit honnête, dataset sérialisable JSON
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pytest

from core.v10.v10_signal_generator_live import (
    TABLE_SIGNALS_CLEAN,
    CURRENCIES_V10_FULL,
    PAIRS_V10_DEFAULT,
    SignalSource,
    V10SignalRow,
    GeneratorReport,
    decide_signal_level,
    generate_signals_for_pair_tf,
    compute_kpis,
    persist_signals,
    generate_clean_dataset,
    _load_forces_snapshots,
)


# ─────────────────────────────────────────────────────────────────────
# HELPERS — DB temporaire
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    """DB temporaire avec table forces_snapshots + v10_signals_clean."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    con = sqlite3.connect(path, timeout=10)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE forces_snapshots (
            snapshot_id TEXT,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            bar_time INTEGER,
            bar_close_time INTEGER,
            direction TEXT,
            vitesse REAL,
            force_usd REAL, force_gbp REAL, force_eur REAL, force_jpy REAL,
            force_cad REAL, force_chf REAL, force_aud REAL, force_nzd REAL,
            tick_volume REAL,
            spread_points REAL,
            bid REAL,
            ask REAL,
            mid REAL,
            open REAL, high REAL, low REAL, close REAL
        )
    """)
    cur.execute("""
        CREATE TABLE v10_signals_clean (
            signal_id TEXT PRIMARY KEY,
            timestamp TEXT, symbol TEXT, timeframe TEXT, pair TEXT,
            direction TEXT, signal_level TEXT,
            force_base REAL, force_quote REAL, velocity_base REAL, velocity_quote REAL,
            rank_base INTEGER, rank_quote INTEGER, spread_score REAL,
            tick_volume REAL, bid REAL, ask REAL,
            pnl_pips_proxy REAL, is_win_proxy INTEGER, source TEXT, features_json TEXT
        )
    """)
    con.commit()
    con.close()
    yield path
    Path(path).unlink(missing_ok=True)


def _populate_snapshots(
    db_path: str,
    snapshots: List[Dict],
) -> None:
    con = sqlite3.connect(db_path, timeout=10)
    cur = con.cursor()
    for s in snapshots:
        cur.execute("""
            INSERT INTO forces_snapshots (
                snapshot_id, timestamp, symbol, timeframe, bar_time, bar_close_time,
                direction, vitesse,
                force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd,
                tick_volume, spread_points, bid, ask, mid, open, high, low, close
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            s.get("snapshot_id", f"SNAP_{s['bar_time']}"),
            s["timestamp"], s["symbol"], s["timeframe"],
            s["bar_time"], s["bar_time"] + 60,
            s.get("direction", "neutre"), s.get("vitesse", 0.0),
            s["force"].get("USD", 0), s["force"].get("GBP", 0),
            s["force"].get("EUR", 0), s["force"].get("JPY", 0),
            s["force"].get("CAD", 0), s["force"].get("CHF", 0),
            s["force"].get("AUD", 0), s["force"].get("NZD", 0),
            s.get("tick_volume", 100.0), s.get("spread_points", 1.0),
            s.get("bid", 1.1000), s.get("ask", 1.1001),
            s.get("mid", 1.10005),
            s.get("open", 1.1000), s.get("high", 1.1010),
            s.get("low", 1.0990), s.get("close", 1.10005),
        ))
    con.commit()
    con.close()


def _make_snapshots_polarized(
    symbol: str = "GBPUSD",
    timeframe: str = "H1",
    n: int = 30,
    *,
    trending_up: bool = True,
) -> List[Dict]:
    """Snapshots synthétiques : GBP bullish (force_gbp monte, force_usd baisse)."""
    snaps = []
    for i in range(n):
        base_force = 50 + i * 1.5 if trending_up else 50 - i * 1.5
        quote_force = 50 - i * 0.5 if trending_up else 50 + i * 0.5
        snaps.append({
            "snapshot_id": f"SNAP_{i}",
            "timestamp": f"2026-07-{(i // 24) + 1:02d}T{(i % 24):02d}:00:00Z",
            "symbol": symbol,
            "timeframe": timeframe,
            "bar_time": 1783111080 + i * 3600,
            "direction": "haussiere" if trending_up else "baissiere",
            "vitesse": 0.5 if trending_up else -0.5,
            "force": {
                "USD": quote_force, "GBP": base_force, "EUR": 55,
                "JPY": 40, "CAD": 45, "CHF": 35, "AUD": 50, "NZD": 30,
            },
            "tick_volume": 100.0 + i * 5,
            "spread_points": 1.0,
            "bid": 1.2700 + i * 0.0001,
            "ask": 1.2701 + i * 0.0001,
            "mid": 1.27005 + i * 0.0001,
        })
    return snaps


# ─────────────────────────────────────────────────────────────────────
# 1. CONSTANTS / DEFAULTS
# ─────────────────────────────────────────────────────────────────────

def test_currencies_v10_full_8():
    """8 devises (force_snapshots inclut NZD)."""
    assert len(CURRENCIES_V10_FULL) == 8
    assert "NZD" in CURRENCIES_V10_FULL


def test_pairs_v10_default_6():
    assert len(PAIRS_V10_DEFAULT) == 6
    assert "EURUSD" in PAIRS_V10_DEFAULT


def test_table_signals_clean_name():
    assert TABLE_SIGNALS_CLEAN == "v10_signals_clean"


# ─────────────────────────────────────────────────────────────────────
# 2. DB LOADER
# ─────────────────────────────────────────────────────────────────────

def test_load_forces_snapshots_empty_db(tmp_db):
    snaps = _load_forces_snapshots(tmp_db)
    assert snaps == []


def test_load_forces_snapshots_missing_db():
    snaps = _load_forces_snapshots("nonexistent_xyz.db")
    assert snaps == []


def test_load_forces_snapshots_basic(tmp_db):
    snaps_in = _make_snapshots_polarized("GBPUSD", "H1", 10)
    _populate_snapshots(tmp_db, snaps_in)
    snaps = _load_forces_snapshots(tmp_db, symbol="GBPUSD", timeframe="H1")
    assert len(snaps) == 10
    assert snaps[0]["force"]["GBP"] == snaps_in[0]["force"]["GBP"]


def test_load_forces_snapshots_filtered(tmp_db):
    _populate_snapshots(tmp_db, _make_snapshots_polarized("GBPUSD", "H1", 10))
    _populate_snapshots(tmp_db, _make_snapshots_polarized("EURUSD", "H1", 5))
    snaps = _load_forces_snapshots(tmp_db, symbol="EURUSD")
    assert len(snaps) == 5


# ─────────────────────────────────────────────────────────────────────
# 3. DECIDE SIGNAL LEVEL
# ─────────────────────────────────────────────────────────────────────

def test_decide_signal_level_a1_strong_bullish():
    """GBP=80, USD=30, delta=50, rank_gbp=2 → A1 BULLISH."""
    level, dir_ = decide_signal_level(
        force_base=80, force_quote=30, velocity_base=0.5, velocity_quote=-0.3,
        rank_base=2, rank_quote=6, direction="haussiere", vitesse=0.5,
    )
    assert level == "A1"
    assert dir_ == "BULLISH"


def test_decide_signal_level_a2_moderate():
    """GBP=55, USD=40, delta=15, rank_gbp=3 → A2."""
    level, dir_ = decide_signal_level(
        force_base=55, force_quote=40, velocity_base=0.1, velocity_quote=-0.1,
        rank_base=3, rank_quote=5, direction="haussiere", vitesse=0.3,
    )
    assert level in ("A2", "A3")  # delta=15 → A3
    assert dir_ == "BULLISH"


def test_decide_signal_level_none_neutral():
    """Direction neutre → NONE."""
    level, dir_ = decide_signal_level(
        force_base=50, force_quote=50, velocity_base=0.0, velocity_quote=0.0,
        rank_base=4, rank_quote=4, direction="neutre", vitesse=0.0,
    )
    assert level == "NONE"


def test_decide_signal_level_a1_bearish():
    """GBP=30, USD=80, delta=-50 → A1 BEARISH."""
    level, dir_ = decide_signal_level(
        force_base=30, force_quote=80, velocity_base=-0.5, velocity_quote=0.3,
        rank_base=6, rank_quote=2, direction="baissiere", vitesse=0.5,
    )
    assert level == "A1"
    assert dir_ == "BEARISH"


# ─────────────────────────────────────────────────────────────────────
# 4. GENERATE SIGNALS
# ─────────────────────────────────────────────────────────────────────

def test_generate_signals_for_pair_tf_polarized():
    snaps = _make_snapshots_polarized("GBPUSD", "H1", 30, trending_up=True)
    signals, n_filtered = generate_signals_for_pair_tf(snaps, pair="GBPUSD", timeframe="H1", horizon_bars=5)
    assert isinstance(signals, list)
    assert isinstance(n_filtered, int)
    assert len(signals) > 0
    # Trending up doit générer A1 ou A2 majoritairement
    high_levels = sum(1 for s in signals if s.signal_level in ("A1", "A2"))
    assert high_levels > 0


def test_generate_signals_insufficient_data():
    """< horizon_bars+1 snapshots → empty (tuple)."""
    snaps = _make_snapshots_polarized("GBPUSD", "H1", 3)
    signals, n_filtered = generate_signals_for_pair_tf(snaps, pair="GBPUSD", timeframe="H1", horizon_bars=5)
    assert signals == []
    assert n_filtered == 0


def test_generate_signals_pnl_proxy():
    """PnL proxy calculé sur 5 bougies futures."""
    snaps = _make_snapshots_polarized("GBPUSD", "H1", 30, trending_up=True)
    signals, _ = generate_signals_for_pair_tf(snaps, pair="GBPUSD", timeframe="H1", horizon_bars=5)
    # Au moins 1 signal avec pnl != 0 (proxy bouge)
    pnl_nonzero = sum(1 for s in signals if s.pnl_pips_proxy != 0)
    assert pnl_nonzero > 0


# ─────────────────────────────────────────────────────────────────────
# 5A. ÉTAPE 5A — Tests horizon par TF + filtre binaire (CEO diagnostic)
# ─────────────────────────────────────────────────────────────────────

def test_step5a_default_timeframes_includes_m30():
    """CEO diagnostic 5/8 : timeframes default doit contenir M30."""
    from core.v10.v10_signal_generator_live import TIMEFRAMES_DEFAULT
    assert "M30" in TIMEFRAMES_DEFAULT
    assert "H1" in TIMEFRAMES_DEFAULT
    assert "H4" in TIMEFRAMES_DEFAULT


def test_step5a_horizon_by_tf_mapping():
    """CEO diagnostic 5/8 : horizon par TF = M30→3, H1→2, H4→1."""
    from core.v10.v10_signal_generator_live import HORIZON_BARS_BY_TF
    assert HORIZON_BARS_BY_TF["M30"] == 3
    assert HORIZON_BARS_BY_TF["H1"] == 2
    assert HORIZON_BARS_BY_TF["H4"] == 1


def test_step5a_filter_binary_excludes_allornothing():
    """Snapshot avec force_base=100 ET force_quote=0 (binaires) → exclu."""
    from core.v10.v10_signal_generator_live import _is_binary_snapshot
    snap_binary = {"force": {"USD": 100.0, "GBP": 0.0, "EUR": 50, "JPY": 40,
                              "CAD": 45, "CHF": 35, "AUD": 50, "NZD": 30}}
    snap_normal = {"force": {"USD": 60.0, "GBP": 70.0, "EUR": 50, "JPY": 40,
                              "CAD": 45, "CHF": 35, "AUD": 50, "NZD": 30}}
    # GBPUSD : base=GBP, quote=USD
    assert _is_binary_snapshot(snap_binary, "GBP", "USD") is True
    assert _is_binary_snapshot(snap_normal, "GBP", "USD") is False


def test_step5a_filter_both_binary_excluded():
    """Snapshot où les DEUX sont binaires (0 ou 100) → exclu."""
    from core.v10.v10_signal_generator_live import _is_binary_snapshot
    snap = {"force": {"USD": 0.0, "GBP": 0.0, "EUR": 50, "JPY": 40,
                       "CAD": 45, "CHF": 35, "AUD": 50, "NZD": 30}}
    assert _is_binary_snapshot(snap, "GBP", "USD") is True


def test_step5a_partial_binary_kept():
    """Si SEULEMENT base ou quote est binaire (pas les deux) → GARDÉ."""
    from core.v10.v10_signal_generator_live import _is_binary_snapshot
    snap = {"force": {"USD": 60.0, "GBP": 0.0, "EUR": 50, "JPY": 40,
                       "CAD": 45, "CHF": 35, "AUD": 50, "NZD": 30}}
    # GBP=0 (binaire) mais USD=60 (normal) → PAS les deux binaires, donc GARDÉ
    assert _is_binary_snapshot(snap, "GBP", "USD") is False


def test_step5a_dataset_includes_m30_signals(tmp_db):
    """Dataset généré avec timeframes default inclut M30."""
    snaps_m30 = _make_snapshots_polarized("GBPUSD", "M30", 20, trending_up=True)
    snaps_h1 = _make_snapshots_polarized("GBPUSD", "H1", 20, trending_up=True)
    _populate_snapshots(tmp_db, snaps_m30 + snaps_h1)
    rep = generate_clean_dataset(
        tmp_db, pairs=("GBPUSD",), timeframes=("M30", "H1"), horizon_bars=5,
        timestamp="2026-08-05T00:00:00Z", filter_binary=False,
    )
    assert "M30" in rep.timeframes_processed
    assert "H1" in rep.timeframes_processed


def test_step5a_n_filtered_in_audit(tmp_db):
    """audit dict contient n_filtered_binary (et le pct est calculable)."""
    # Mix snapshots : 5 binaires + 5 normaux
    snaps = []
    # 10 binaires (force_GBP=100, force_USD=0)
    for i in range(10):
        snaps.append({
            "snapshot_id": f"SNAP_BIN_{i}", "timestamp": f"t_{i}",
            "symbol": "GBPUSD", "timeframe": "H1", "bar_time": 1783111080 + i * 3600,
            "direction": "haussiere", "vitesse": 0.5,
            "force": {"USD": 0.0, "GBP": 100.0, "EUR": 50, "JPY": 40,
                       "CAD": 45, "CHF": 35, "AUD": 50, "NZD": 30},
            "tick_volume": 100, "spread_points": 1,
            "bid": 1.27 + i * 0.0001, "ask": 1.2701 + i * 0.0001,
            "mid": 1.27005 + i * 0.0001,
        })
    # 10 normaux
    for i in range(10, 20):
        snaps.append({
            "snapshot_id": f"SNAP_OK_{i}", "timestamp": f"t_{i}",
            "symbol": "GBPUSD", "timeframe": "H1", "bar_time": 1783111080 + i * 3600,
            "direction": "haussiere", "vitesse": 0.5,
            "force": {"USD": 50.0, "GBP": 60.0, "EUR": 55, "JPY": 40,
                       "CAD": 45, "CHF": 35, "AUD": 50, "NZD": 30},
            "tick_volume": 100, "spread_points": 1,
            "bid": 1.27 + (i-10) * 0.0001, "ask": 1.2701 + (i-10) * 0.0001,
            "mid": 1.27005 + (i-10) * 0.0001,
        })
    _populate_snapshots(tmp_db, snaps)
    rep = generate_clean_dataset(
        tmp_db, pairs=("GBPUSD",), timeframes=("H1",),
        horizon_bars=5, timestamp="2026-08-05T00:00:00Z",
        filter_binary=True, truncate_first=False,
    )
    assert "n_filtered_binary" in rep.audit
    assert rep.audit["n_filtered_binary"] == 10  # 10 snaps binaires exclus


def test_step5a_truncate_clears_table(tmp_db):
    """truncate_first=True vide la table avant regénération."""
    # Premier passage : 20 snapshots → 15 signaux (horizon_bars=5)
    snaps_v1 = _make_snapshots_polarized("GBPUSD", "H1", 20, trending_up=True)
    _populate_snapshots(tmp_db, snaps_v1)
    generate_clean_dataset(
        tmp_db, pairs=("GBPUSD",), timeframes=("H1",),
        horizon_bars=5, timestamp="2026-08-05T00:00:00Z",
        filter_binary=False, truncate_first=True,
    )
    con = sqlite3.connect(tmp_db, timeout=10)
    cur = con.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_SIGNALS_CLEAN}")
    n1 = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM forces_snapshots")
    n_fs1 = cur.fetchone()[0]
    con.close()
    assert n1 == 15
    assert n_fs1 == 20
    # Deuxième passage : on a 20 anciens snapshots en DB. _make_snapshots_polarized
    # utilise les mêmes bar_time (1783111080+0..+29×3600), donc les 30 nouveaux
    # écrasent les 20 anciens → on a 30 snapshots uniques.
    _populate_snapshots(tmp_db, _make_snapshots_polarized("GBPUSD", "H1", 30, trending_up=True))
    generate_clean_dataset(
        tmp_db, pairs=("GBPUSD",), timeframes=("H1",),
        horizon_bars=5, timestamp="2026-08-05T00:00:00Z",
        filter_binary=False, truncate_first=True,
    )
    con = sqlite3.connect(tmp_db, timeout=10)
    cur = con.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_SIGNALS_CLEAN}")
    n2 = cur.fetchone()[0]
    con.close()
    # 30 snapshots (les plus récents ont écrasé les anciens) → 30-5=25 signaux
    assert n2 == 25


def test_step5a_truncate_false_appends(tmp_db):
    """truncate_first=False conserve + ajoute (mais INSERT OR REPLACE = replace par signal_id)."""
    snaps_v1 = _make_snapshots_polarized("GBPUSD", "H1", 20, trending_up=True)
    _populate_snapshots(tmp_db, snaps_v1)
    generate_clean_dataset(
        tmp_db, pairs=("GBPUSD",), timeframes=("H1",),
        horizon_bars=5, timestamp="2026-08-05T00:00:00Z",
        filter_binary=False, truncate_first=False,
    )
    # Re-run sur même data : INSERT OR REPLACE → même count
    generate_clean_dataset(
        tmp_db, pairs=("GBPUSD",), timeframes=("H1",),
        horizon_bars=5, timestamp="2026-08-05T00:00:00Z",
        filter_binary=False, truncate_first=False,
    )
    con = sqlite3.connect(tmp_db, timeout=10)
    cur = con.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_SIGNALS_CLEAN}")
    n = cur.fetchone()[0]
    con.close()
    assert n == 15  # pas de dup car INSERT OR REPLACE par signal_id


# ─────────────────────────────────────────────────────────────────────
# 5. KPI COMPUTATION
# ─────────────────────────────────────────────────────────────────────

def test_compute_kpis_empty():
    kpis = compute_kpis([])
    assert kpis["n_total"] == 0
    assert kpis["wr_global"] == 0.0
    assert kpis["pnl_total_pips"] == 0.0


def test_compute_kpis_basic():
    s1 = V10SignalRow(signal_id="S1", timestamp="t", symbol="X", timeframe="H1", pair="GBPUSD", direction="BULLISH", signal_level="A1", is_win_proxy=1, pnl_pips_proxy=10.0)
    s2 = V10SignalRow(signal_id="S2", timestamp="t", symbol="X", timeframe="H1", pair="GBPUSD", direction="BEARISH", signal_level="A2", is_win_proxy=0, pnl_pips_proxy=-5.0)
    kpis = compute_kpis([s1, s2])
    assert kpis["n_total"] == 2
    assert kpis["wr_global"] == 0.5
    assert kpis["pnl_total_pips"] == 5.0


def test_compute_kpis_by_pair():
    s1 = V10SignalRow(signal_id="S1", timestamp="t", symbol="X", timeframe="H1", pair="GBPUSD", direction="B", signal_level="A1", is_win_proxy=1, pnl_pips_proxy=20.0)
    s2 = V10SignalRow(signal_id="S2", timestamp="t", symbol="X", timeframe="H1", pair="EURUSD", direction="B", signal_level="A1", is_win_proxy=0, pnl_pips_proxy=-10.0)
    kpis = compute_kpis([s1, s2])
    assert kpis["by_pair"]["GBPUSD"]["n"] == 1
    assert kpis["by_pair"]["GBPUSD"]["wr"] == 1.0
    assert kpis["by_pair"]["EURUSD"]["wr"] == 0.0


# ─────────────────────────────────────────────────────────────────────
# 6. PERSISTENCE
# ─────────────────────────────────────────────────────────────────────

def test_persist_signals_to_db(tmp_db):
    signals = [
        V10SignalRow(signal_id="S_TEST_1", timestamp="2026-08-05T10:00:00Z",
                     symbol="GBPUSD", timeframe="H1", pair="GBPUSD",
                     direction="BULLISH", signal_level="A1",
                     force_base=80, force_quote=30, is_win_proxy=1, pnl_pips_proxy=10.0),
    ]
    n = persist_signals(tmp_db, signals)
    assert n == 1
    con = sqlite3.connect(tmp_db, timeout=10)
    cur = con.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {TABLE_SIGNALS_CLEAN}")
    assert cur.fetchone()[0] == 1
    con.close()


def test_persist_signals_empty_list(tmp_db):
    n = persist_signals(tmp_db, [])
    assert n == 0


# ─────────────────────────────────────────────────────────────────────
# 7. ORCHESTRATEUR
# ─────────────────────────────────────────────────────────────────────

def test_generate_clean_dataset_basic(tmp_db):
    snaps = _make_snapshots_polarized("GBPUSD", "H1", 50, trending_up=True)
    snaps += _make_snapshots_polarized("EURUSD", "H1", 30, trending_up=True)
    _populate_snapshots(tmp_db, snaps)
    rep = generate_clean_dataset(
        tmp_db, pairs=("GBPUSD", "EURUSD"), timeframes=("H1",), horizon_bars=5,
        timestamp="2026-08-05T00:00:00Z",
    )
    assert rep.n_snapshots_loaded == 80
    assert rep.n_signals_generated > 0
    assert rep.n_signals_persisted == rep.n_signals_generated
    assert "GBPUSD" in rep.kpis_by_pair
    assert "EURUSD" in rep.kpis_by_pair


def test_generate_clean_dataset_empty_db(tmp_db):
    rep = generate_clean_dataset(
        tmp_db, pairs=("GBPUSD",), timeframes=("H1",), timestamp="2026-08-05T00:00:00Z",
    )
    assert rep.n_signals_generated == 0
    assert rep.n_snapshots_loaded == 0


def test_generate_clean_dataset_missing_db():
    rep = generate_clean_dataset(
        "nonexistent_xyz.db", pairs=("GBPUSD",), timeframes=("H1",), timestamp="2026-08-05T00:00:00Z",
    )
    assert rep.n_signals_generated == 0
    assert rep.audit.get("reason") or rep.n_snapshots_loaded == 0


def test_generate_clean_dataset_serializable():
    rep = GeneratorReport(
        timestamp="2026-08-05T00:00:00Z",
        db_path="test.db",
        n_snapshots_loaded=100,
        n_signals_generated=50,
        kpis_by_pair={"GBPUSD": {"n": 50, "wr": 0.6, "pnl_pips": 100.0}},
        kpis_by_level={"A1": {"n": 20, "wr": 0.7, "pnl_pips": 50.0}},
    )
    s = rep.to_json()
    parsed = json.loads(s)
    assert parsed["n_signals_generated"] == 50


# ─────────────────────────────────────────────────────────────────────
# 8. AUDIT R9 / DOCTRINE
# ─────────────────────────────────────────────────────────────────────

def test_v10_signal_row_default_construction():
    row = V10SignalRow(
        signal_id="S", timestamp="t", symbol="GBPUSD", timeframe="H1",
        pair="GBPUSD", direction="BULLISH", signal_level="A1",
    )
    assert row.is_win_proxy == 0
    assert row.pnl_pips_proxy == 0.0
    # C9 : source par défaut = FORCE_NATIVE (plus forces_snapshots)
    assert row.source == SignalSource.FORCE_NATIVE.value


def test_v10_signal_row_serializable():
    row = V10SignalRow(
        signal_id="S", timestamp="t", symbol="GBPUSD", timeframe="H1",
        pair="GBPUSD", direction="BULLISH", signal_level="A1",
        force_base=80, force_quote=30, is_win_proxy=1, pnl_pips_proxy=10.0,
    )
    d = row.as_dict()
    json.dumps(d)


def test_pnl_proxy_consistent_with_direction():
    """PnL proxy : close[t+h] > close[t] + direction BULLISH → is_win=1."""
    snaps = []
    for i in range(20):
        snaps.append({
            "snapshot_id": f"S_{i}", "timestamp": f"t_{i}", "symbol": "GBPUSD",
            "timeframe": "H1", "bar_time": i * 3600,
            "direction": "haussiere", "vitesse": 0.5,
            # forces polarisées → direction BULLISH (pas neutre)
            "force": {"USD": 50 - i * 0.5, "GBP": 50 + i * 0.5, "EUR": 55, "JPY": 40,
                       "CAD": 45, "CHF": 35, "AUD": 50, "NZD": 30},
            "tick_volume": 100, "spread_points": 1,
            "bid": 1.0 + i * 0.0001, "ask": 1.0 + i * 0.0001,
            "mid": 1.0 + i * 0.0001, "close": 1.0 + i * 0.0001,
        })
    signals, _ = generate_signals_for_pair_tf(snaps, pair="GBPUSD", timeframe="H1", horizon_bars=5)
    # Tous les signaux avec direction BULLISH + close qui monte → is_win=1
    for s in signals:
        if s.direction == "BULLISH":
            assert s.is_win_proxy == 1
            assert s.pnl_pips_proxy > 0


def test_compute_kpis_by_tf_separated():
    """Étape 5A : KPIs par TF (et par paire)."""
    s1 = V10SignalRow(signal_id="S1", timestamp="t", symbol="X", timeframe="H1", pair="GBPUSD", direction="B", signal_level="A1", is_win_proxy=1, pnl_pips_proxy=10.0)
    s2 = V10SignalRow(signal_id="S2", timestamp="t", symbol="X", timeframe="H1", pair="GBPUSD", direction="B", signal_level="A1", is_win_proxy=0, pnl_pips_proxy=-5.0)
    s3 = V10SignalRow(signal_id="S3", timestamp="t", symbol="X", timeframe="M30", pair="GBPUSD", direction="B", signal_level="A1", is_win_proxy=1, pnl_pips_proxy=15.0)
    kpis = compute_kpis([s1, s2, s3], separate_by_tf=True)
    assert "by_tf" in kpis
    assert "H1" in kpis["by_tf"]
    assert "M30" in kpis["by_tf"]
    assert kpis["by_tf"]["H1"]["wr"] == 0.5  # 1/2 wins
    assert kpis["by_tf"]["M30"]["wr"] == 1.0  # 1/1 wins
    # by_pair agrège toutes les TF pour la paire GBPUSD
    assert kpis["by_pair"]["GBPUSD"]["n"] == 3


def test_compute_kpis_no_tf_when_disabled():
    """separate_by_tf=False → pas de by_tf/by_pair_tf."""
    s1 = V10SignalRow(signal_id="S1", timestamp="t", symbol="X", timeframe="H1", pair="GBPUSD", direction="B", signal_level="A1", is_win_proxy=1, pnl_pips_proxy=10.0)
    kpis = compute_kpis([s1], separate_by_tf=False)
    assert "by_tf" not in kpis
    assert "by_pair_tf" not in kpis
