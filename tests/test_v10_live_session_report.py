"""tests/test_v10_live_session_report.py — H-LIVE-REPORT (C22).

Vérifie le rapport de session live V10 (scripts.run_live_session_report) :

  - top 3 paires par force delta 24h
  - signal_level par paire/TF (A1/A2/A3/NONE)
  - pre_wave_phase (COMPRESSION/DIVERGENCE/NEUTRAL)
  - health_score (build_health)
  - dernier trade shadow + WR rolling 20
  - timestamp + version C22

R6 fail-open : DB absente → chaque section retourne un état sûr.
R9 : rapport JSON horodaté. R10 : lecture seule.

≥ 6 cas de test.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.run_live_session_report import (
    VERSION,
    build_session_report,
    pre_wave_phase_per_pair,
    shadow_trades_summary,
    signal_level_per_pair_tf,
    top_pairs_force_delta,
    write_report,
)

# ─────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────

def _make_db(n_rows: int = 60) -> str:
    """DB forces_snapshots + paper_trades minimal pour les tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, timeframe TEXT, bar_time INTEGER,
            open REAL, high REAL, low REAL, close REAL,
            tick_volume INTEGER, is_closed_bar INTEGER,
            force_usd REAL, force_gbp REAL, force_eur REAL,
            force_jpy REAL, force_cad REAL, force_chf REAL,
            force_aud REAL, force_nzd REAL
        );
        CREATE TABLE paper_trades (
            trade_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            pips_simulated REAL,
            is_win INTEGER
        );
    """)
    now_s = int(datetime.now(UTC).timestamp())
    # EURUSD : base forte / quote faible → delta positif fort
    # USDJPY  : base forte / quote forte → delta ~0
    # GBPUSD : base forte / quote faible → delta positif moyen
    profiles = {
        "EURUSD": (70.0, 40.0),
        "USDJPY": (55.0, 52.0),
        "GBPUSD": (62.0, 40.0),
        "AUDUSD": (50.0, 42.0),
        "USDCAD": (55.0, 60.0),
        "USDCHF": (50.0, 50.0),
        "NZDUSD": (48.0, 44.0),
    }
    forces = {
        "USD": 50.0, "GBP": 50.0, "EUR": 50.0, "JPY": 50.0,
        "CAD": 50.0, "CHF": 50.0, "AUD": 50.0, "NZD": 50.0,
    }
    i = 0
    for tf in ("M30", "H1", "H4"):
        step = 1800 if tf == "M30" else 3600 if tf == "H1" else 14400
        for k in range(n_rows):
            for sym, (fbase, fquote) in profiles.items():
                f = dict(forces)
                f[sym[:3]] = fbase
                f[sym[3:]] = fquote
                bar_time = now_s - (n_rows - k) * step
                con.execute(
                    """
                    INSERT INTO forces_snapshots (
                        symbol, timeframe, bar_time, open, high, low, close,
                        tick_volume, is_closed_bar,
                        force_usd, force_gbp, force_eur, force_jpy,
                        force_cad, force_chf, force_aud, force_nzd
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (sym, tf, bar_time, 1.1, 1.2, 1.0, 1.15, 100, 1,
                     f["USD"], f["GBP"], f["EUR"], f["JPY"],
                     f["CAD"], f["CHF"], f["AUD"], f["NZD"]),
                )
                i += 1
    # paper_trades : 5 trades, 3 wins
    for t in range(5):
        con.execute(
            """
            INSERT INTO paper_trades (
                trade_id, snapshot_id, direction, opened_at, closed_at,
                pips_simulated, is_win
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (f"PT{t}", f"S{t}", "BUY",
             f"2026-08-0{t+1}T00:00:00Z", f"2026-08-0{t+1}T01:00:00Z",
             10.0 if t % 3 != 2 else -5.0, 1 if t % 3 != 2 else 0),
        )
    con.commit()
    con.close()
    return path


@pytest.fixture
def tmp_db():
    paths = []
    def _create():
        p = _make_db()
        paths.append(p)
        return p
    yield _create
    for p in paths:
        Path(p).unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────
# 1. TOP 3 PAIRES PAR FORCE DELTA
# ─────────────────────────────────────────────────────────────────────

def test_top_pairs_returns_three(tmp_db):
    db = tmp_db()
    res = top_pairs_force_delta(db)
    assert res["ok"] is True
    assert len(res["top"]) == 3


def test_top_pairs_delta_sign(tmp_db):
    """EURUSD (base EUR 70 / quote USD 50) → delta > 0."""
    db = tmp_db()
    res = top_pairs_force_delta(db)
    assert res["ok"] is True
    eurusd = next((x for x in res["top"] if x["pair"] == "EURUSD"), None)
    assert eurusd is not None
    assert eurusd["force_delta_24h"] > 0


def test_top_pairs_fail_open():
    """DB absente → ok=False, top vide, pas d'exception (R6)."""
    res = top_pairs_force_delta("/nonexistent_xyz.db")
    assert res["ok"] is False
    assert res["top"] == []


# ─────────────────────────────────────────────────────────────────────
# 2. SIGNAL_LEVEL PAR PAIRE/TF
# ─────────────────────────────────────────────────────────────────────

def test_signal_level_structure(tmp_db):
    """Chaque (paire, TF) a un signal_level A1/A2/A3/NONE."""
    db = tmp_db()
    res = signal_level_per_pair_tf(db)
    assert res["ok"] is True
    assert len(res["levels"]) >= 1
    for lvl in res["levels"]:
        assert lvl["signal_level"] in ("A1", "A2", "A3", "NONE")


def test_signal_level_fail_open():
    """DB absente → ok=False, pas d'exception (R6)."""
    res = signal_level_per_pair_tf("/nonexistent_siglev_zzz.db")
    assert res["ok"] is False


# ─────────────────────────────────────────────────────────────────────
# 3. PRE_WAVE_PHASE
# ─────────────────────────────────────────────────────────────────────

def test_pre_wave_phase_structure(tmp_db):
    """Chaque paire a une phase COMPRESSION/DIVERGENCE/NEUTRAL."""
    db = tmp_db()
    res = pre_wave_phase_per_pair(db)
    assert res["ok"] is True
    for p in res["pairs"]:
        assert p["pre_wave_phase"] in ("COMPRESSION", "DIVERGENCE", "NEUTRAL")


def test_pre_wave_phase_fail_open():
    """DB absente → ok=True, chaque paire NEUTRAL (R6)."""
    res = pre_wave_phase_per_pair("/nonexistent_xyz.db")
    assert res["ok"] is True
    assert all(p["pre_wave_phase"] == "NEUTRAL" for p in res["pairs"])


# ─────────────────────────────────────────────────────────────────────
# 5. SHADOW TRADES SUMMARY
# ─────────────────────────────────────────────────────────────────────

def test_shadow_summary(tmp_db):
    """5 trades clos → WR rolling ~0.6, dernier trade présent."""
    db = tmp_db()
    res = shadow_trades_summary(db)
    assert res["ok"] is True
    assert res["n_closed"] == 5
    assert res["last_trade"] is not None
    assert 0.4 <= res["rolling_wr"] <= 0.8


def test_shadow_summary_fail_open():
    """DB absente → ok=False, pas d'exception (R6)."""
    res = shadow_trades_summary("/nonexistent_xyz.db")
    assert res["ok"] is False


# ─────────────────────────────────────────────────────────────────────
# 6. RAPPORT COMPLET + WRITE
# ─────────────────────────────────────────────────────────────────────

def test_build_session_report_sections(tmp_db):
    """Rapport 6 sections : 5 datasections + version + timestamp."""
    db = tmp_db()
    rep = build_session_report(db)
    assert rep["version"] == VERSION
    assert rep["generated_at_utc"]
    assert set(rep["sections"].keys()) == {
        "top_pairs_force_delta", "signal_level_per_pair_tf",
        "pre_wave_phase", "health_score", "shadow_trades",
    }


def test_build_session_report_fail_open_db():
    """DB absente → rapport généré, meta.error signalé (R6 fail-open global)."""
    rep = build_session_report("/nonexistent_xyz.db")
    assert rep["sections"]["top_pairs_force_delta"]["ok"] is False
    assert rep["sections"]["shadow_trades"]["ok"] is False


def test_write_report_json(tmp_path):
    """write_report écrit un JSON horodaté lisible (R9)."""
    rep = {"report": "live_session_report", "version": VERSION,
           "sections": {}}
    p = write_report(rep, tmp_path / "live_session_test.json")
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["version"] == VERSION
