"""Tests détecteur de divergence de résolution (réconciliation 2026-07-20)."""
from __future__ import annotations

import sqlite3

from core.v9.v9_resolution_drift import compute_resolution_drift


def _seed(db_path, paper_wins, decision_wins):
    """paper_wins / decision_wins = list[int 0|1]."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE paper_trades (is_win INTEGER, closed_at TEXT, "
        "pips_simulated REAL)"
    )
    conn.execute(
        "CREATE TABLE decisions (is_win INTEGER, resolved_at TEXT, "
        "resolution_pips REAL)"
    )
    conn.executemany(
        "INSERT INTO paper_trades (is_win, closed_at, pips_simulated) "
        "VALUES (?, datetime('now'), 1.0)",
        [(w,) for w in paper_wins],
    )
    conn.executemany(
        "INSERT INTO decisions (is_win, resolved_at, resolution_pips) "
        "VALUES (?, datetime('now'), 1.0)",
        [(w,) for w in decision_wins],
    )
    conn.commit()
    conn.close()


def _wins(n_win, n_total):
    return [1] * n_win + [0] * (n_total - n_win)


def test_drift_zero_when_identical(tmp_path):
    db = tmp_path / "d.db"
    _seed(db, _wins(70, 100), _wins(70, 100))
    r = compute_resolution_drift(db)
    assert r.drift_pct == 0.0
    assert r.alert_level == "none"


def test_drift_warn_at_25_pct(tmp_path):
    db = tmp_path / "d.db"
    # WR 70 vs 95 → drift 25 → WARN.
    _seed(db, _wins(70, 100), _wins(95, 100))
    r = compute_resolution_drift(db)
    assert r.drift_pct == 25.0
    assert r.alert_level == "WARN"


def test_drift_critical_at_45_pct(tmp_path):
    db = tmp_path / "d.db"
    # WR 50 vs 95 → drift 45 → CRITICAL.
    _seed(db, _wins(50, 100), _wins(95, 100))
    r = compute_resolution_drift(db)
    assert r.drift_pct == 45.0
    assert r.alert_level == "CRITICAL"


def test_drift_handles_empty_table(tmp_path):
    db = tmp_path / "d.db"
    _seed(db, [], [])
    r = compute_resolution_drift(db)
    assert r.wr_paper_trades is None
    assert r.wr_decisions is None
    assert r.drift_pct is None
    assert r.alert_level == "none"


def test_drift_missing_db_no_crash(tmp_path):
    r = compute_resolution_drift(tmp_path / "absent.db")
    assert r.drift_pct is None
    assert r.alert_level == "none"
