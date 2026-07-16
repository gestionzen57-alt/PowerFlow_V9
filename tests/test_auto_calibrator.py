"""Tests — core/v9/auto_calibrator.py (Brief Q2, 2026-07-12).

Garde-fous vérifiés : kill switch OFF par défaut (no-op complet, 0 lecture
DB), jamais d'auto-apply (aucune écriture core/v9/config.py|risk_manager.py
possible par construction — le module ne fait que lire + proposer), ne
lève jamais, propositions bornées.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9.auto_calibrator import (
    AUTO_CALIBRATOR_ENABLED_ENV,
    MIN_SAMPLE_SESSION,
    WR_LOW_THRESHOLD,
    _propose_session_scale_adjustments,
    _propose_threshold_adjustments,
    _session_wr_buckets,
    auto_calibrator_enabled,
    run_calibration_cycle,
)

DECISIONS_SCHEMA = """
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT UNIQUE,
    timestamp TEXT,
    action TEXT,
    resolution_strategy TEXT,
    is_win INTEGER,
    resolution_pips REAL
)
"""


def _make_db(tmp_path: Path, rows: list[tuple]) -> Path:
    """rows: (decision_id, timestamp_iso, action, resolution_strategy, is_win, pips)"""
    db_path = tmp_path / "test_v9.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(DECISIONS_SCHEMA)
    conn.executemany(
        "INSERT INTO decisions (decision_id, timestamp, action, resolution_strategy, "
        "is_win, resolution_pips) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db_path


def _session_rows(session_hour: int, n: int, n_wins: int, prefix: str) -> list[tuple]:
    rows = []
    for i in range(n):
        is_win = 1 if i < n_wins else 0
        ts = f"2026-07-{10 + (i % 2):02d}T{session_hour:02d}:{i % 60:02d}:00Z"
        rows.append((f"{prefix}_{i}", ts, "preparer_entree", "DYNAMIC", is_win, 5.0 if is_win else -3.0))
    return rows


def test_auto_calibrator_enabled_by_default():
    """V9_AUTO_CALIBRATOR_ENABLED=1 (activé 2026-07-14)."""
    assert auto_calibrator_enabled() is True


def test_auto_calibrator_enabled_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(AUTO_CALIBRATOR_ENABLED_ENV, "1")
    assert auto_calibrator_enabled() is True


def test_run_calibration_cycle_noop_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Kill switch OFF -> retour immédiat, aucune lecture DB (db_path bidon jamais ouvert)."""
    monkeypatch.delenv(AUTO_CALIBRATOR_ENABLED_ENV, raising=False)
    report = run_calibration_cycle(db_path=tmp_path / "does_not_exist.db")
    assert report == {"enabled": False}


def test_run_calibration_cycle_enabled_no_crash_on_empty_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(AUTO_CALIBRATOR_ENABLED_ENV, "1")
    db_path = _make_db(tmp_path, [])
    report = run_calibration_cycle(db_path=db_path, notify=False, journal=False, auto_apply=False)
    assert report["enabled"] is True
    assert report["n_total_decisions"] == 0
    assert report["global_wr_pct"] is None
    assert report["auto_apply"] is False


def test_session_wr_buckets_low_wr_session(tmp_path: Path):
    # session "asie" = heure UTC 0-7 ; WR très bas, échantillon suffisant.
    rows = _session_rows(session_hour=3, n=MIN_SAMPLE_SESSION + 5, n_wins=5, prefix="asie")
    db_path = _make_db(tmp_path, rows)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    buckets = _session_wr_buckets(conn)
    conn.close()
    assert buckets["asie"]["n"] == MIN_SAMPLE_SESSION + 5
    assert buckets["asie"]["wr_pct"] < WR_LOW_THRESHOLD


def test_propose_session_scale_adjustments_below_min_sample_not_proposed():
    buckets = {"asie": {"n": 5, "wins": 1, "wr_pct": 20.0, "avg_pips": -1.0, "current_scale": 1.0}}
    proposals = _propose_session_scale_adjustments(buckets)
    assert proposals[0]["proposed"] is False
    assert "min=" in proposals[0]["reason"]


def test_propose_session_scale_adjustments_wr_below_threshold_proposes_reduction():
    buckets = {
        "asie": {
            "n": MIN_SAMPLE_SESSION + 1, "wins": 10, "wr_pct": 30.0,
            "avg_pips": -2.0, "current_scale": 1.0,
        }
    }
    proposals = _propose_session_scale_adjustments(buckets)
    p = proposals[0]
    assert p["proposed"] is True
    assert p["proposed_scale"] < p["current_scale"]
    assert p["proposed_scale"] >= 0.0


def test_propose_session_scale_adjustments_wr_above_threshold_not_proposed():
    buckets = {
        "asie": {
            "n": MIN_SAMPLE_SESSION + 1, "wins": 90, "wr_pct": 90.0,
            "avg_pips": 5.0, "current_scale": 1.0,
        }
    }
    proposals = _propose_session_scale_adjustments(buckets)
    assert proposals[0]["proposed"] is False


def test_propose_threshold_adjustments_insufficient_sample():
    result = _propose_threshold_adjustments(50.0, n_total=5, current_confiance_min=70, current_nb_principes_min=2)
    assert result["proposed"] is False


def test_propose_threshold_adjustments_low_wr_tightens_thresholds():
    result = _propose_threshold_adjustments(
        40.0, n_total=100, current_confiance_min=70, current_nb_principes_min=2,
    )
    assert result["proposed"] is True
    assert result["proposed_confiance_min"] >= result["current_confiance_min"]
    assert result["proposed_nb_principes_min"] >= result["current_nb_principes_min"]


def test_propose_threshold_adjustments_bounds_never_exceeded():
    from core.v9.auto_calibrator import CONFIANCE_MIN_BOUNDS, NB_PRINCIPES_MIN_BOUNDS

    result = _propose_threshold_adjustments(
        0.0, n_total=1000, current_confiance_min=70, current_nb_principes_min=2,
    )
    lo_c, hi_c = CONFIANCE_MIN_BOUNDS
    lo_p, hi_p = NB_PRINCIPES_MIN_BOUNDS
    assert lo_c <= result["proposed_confiance_min"] <= hi_c
    assert lo_p <= result["proposed_nb_principes_min"] <= hi_p


def test_run_calibration_cycle_never_writes_to_decisions_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Garde-fou central du brief : le cycle est 100% lecture sur `decisions`."""
    monkeypatch.setenv(AUTO_CALIBRATOR_ENABLED_ENV, "1")
    rows = _session_rows(session_hour=3, n=10, n_wins=8, prefix="asie")
    db_path = _make_db(tmp_path, rows)

    conn_before = sqlite3.connect(str(db_path))
    before = conn_before.execute("SELECT * FROM decisions ORDER BY decision_id").fetchall()
    conn_before.close()

    run_calibration_cycle(db_path=db_path, notify=False, journal=False)

    conn_after = sqlite3.connect(str(db_path))
    after = conn_after.execute("SELECT * FROM decisions ORDER BY decision_id").fetchall()
    conn_after.close()
    assert before == after


def test_run_calibration_cycle_report_never_raises_on_notify_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """notify=True mais pas de config/telegram.json valide -> best-effort, pas d'exception."""
    monkeypatch.setenv(AUTO_CALIBRATOR_ENABLED_ENV, "1")
    db_path = _make_db(tmp_path, [])
    report = run_calibration_cycle(db_path=db_path, notify=True, journal=False)
    assert report["enabled"] is True
