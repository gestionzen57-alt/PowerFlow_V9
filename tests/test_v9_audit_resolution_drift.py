"""Tests audit rétrospectif de divergence de résolution (réconciliation 2026-07-20)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import scripts.v9_audit_resolution_drift as audit


def _seed(db_path: Path, paper, decisions):
    """paper/decisions = list[(snapshot_id, symbol, tf, direction, regime, is_win, pips)]."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE paper_trades (snapshot_id TEXT, direction TEXT, "
        "closed_at TEXT, is_win INTEGER, pips_simulated REAL)"
    )
    conn.execute(
        "CREATE TABLE decisions (snapshot_id TEXT, symbol TEXT, timeframe TEXT, "
        "direction TEXT, regime_type TEXT, resolved_at TEXT, is_win INTEGER, "
        "resolution_pips REAL)"
    )
    # decisions : porte le contexte (symbol/tf/regime).
    for snap, sym, tf, direction, regime, win, pips in decisions:
        conn.execute(
            "INSERT INTO decisions (snapshot_id, symbol, timeframe, direction, "
            "regime_type, resolved_at, is_win, resolution_pips) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?)",
            (snap, sym, tf, direction, regime, win, pips),
        )
    for snap, sym, tf, direction, regime, win, pips in paper:
        conn.execute(
            "INSERT INTO paper_trades (snapshot_id, direction, closed_at, is_win, "
            "pips_simulated) VALUES (?, ?, datetime('now'), ?, ?)",
            (snap, direction, win, pips),
        )
    conn.commit()
    conn.close()


def test_audit_generates_report_file(tmp_path, monkeypatch):
    db = tmp_path / "f.db"
    _seed(db,
          paper=[("s1", "GBPUSD", "M1", "haussiere", "range", 1, 10.0)],
          decisions=[("s1", "GBPUSD", "M1", "haussiere", "range", 1, 10.0)])
    monkeypatch.setattr(audit, "AUDIT_DIR", tmp_path / "audits")
    rc = audit.run_audit(db, days=30, dry_run=False)
    files = list((tmp_path / "audits").glob("RESOLUTION_DRIFT_AUDIT_*.md"))
    assert len(files) == 1
    assert rc == 0


def test_audit_groups_by_context(tmp_path):
    db = tmp_path / "f.db"
    # 3 contextes distincts.
    paper = [
        ("s1", "GBPUSD", "M1", "haussiere", "range", 1, 10.0),
        ("s2", "EURUSD", "M5", "baissiere", "expansion", 0, -10.0),
        ("s3", "GBPUSD", "H1", "haussiere", "calme", 1, 10.0),
    ]
    _seed(db, paper=paper, decisions=paper)
    conn = audit._connect_ro(db)
    groups = audit.collect_groups(conn, 30)
    conn.close()
    assert len(groups) == 3


def test_audit_exits_zero_on_low_drift(tmp_path):
    db = tmp_path / "f.db"
    # WR identiques → drift 0.
    paper = [("s1", "GBPUSD", "M1", "haussiere", "range", 1, 10.0)]
    _seed(db, paper=paper, decisions=paper)
    rc = audit.run_audit(db, days=30, dry_run=True)
    assert rc == 0


def test_audit_exits_two_on_critical(tmp_path):
    db = tmp_path / "f.db"
    # Même contexte, WR paper 0% vs decision 100% → drift 100 → exit 2.
    paper = [
        ("s1", "GBPUSD", "M1", "haussiere", "range", 0, -10.0),
        ("s2", "GBPUSD", "M1", "haussiere", "range", 0, -10.0),
    ]
    decisions = [
        ("s1", "GBPUSD", "M1", "haussiere", "range", 1, 10.0),
        ("s2", "GBPUSD", "M1", "haussiere", "range", 1, 10.0),
    ]
    _seed(db, paper=paper, decisions=decisions)
    rc = audit.run_audit(db, days=30, dry_run=True)
    assert rc == 2


def test_audit_report_contains_top5(tmp_path):
    db = tmp_path / "f.db"
    paper = [("s1", "GBPUSD", "M1", "haussiere", "range", 1, 10.0)]
    _seed(db, paper=paper, decisions=paper)
    conn = audit._connect_ro(db)
    groups = audit.collect_groups(conn, 30)
    conn.close()
    report, _ = audit.build_report(groups, 30)
    assert "Top 5 divergences" in report
