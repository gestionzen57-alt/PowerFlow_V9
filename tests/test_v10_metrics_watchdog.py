"""V10 Metrics Watchdog — tests (P3, ZCode audit).

Vérifie que le watchdog détecte :
  1. PnL absurde par trade (facteur pip cassé).
  2. Doublons dans le journal.
  3. Facteur JPY incohérent (100×).
  4. DB saine → healthy=True.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v10_metrics_watchdog import check_metrics, MAX_PIPS_BY_TF


def _make_db(path: Path, rows: list) -> Path:
    db = sqlite3.connect(str(path))
    db.execute("""CREATE TABLE v10_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pair TEXT NOT NULL, timeframe TEXT, timestamp TEXT, action TEXT,
        signal_level TEXT, filtered_level TEXT, lot_size REAL,
        pnl_pips REAL, is_win INTEGER, audit_json TEXT)""")
    for r in rows:
        db.execute(
            "INSERT INTO v10_decisions (pair,timeframe,timestamp,action,pnl_pips,is_win) "
            "VALUES (?,?,?,?,?,?)", r)
    db.commit()
    db.close()
    return path


def test_healthy_db(tmp_path):
    db = _make_db(tmp_path / "t.db", [
        ("EURUSD", "H1", "2026-08-05T10:00:00Z", "BUY", 5.0, 1),
        ("GBPUSD", "H1", "2026-08-05T10:00:00Z", "SELL", -3.0, 0),
        ("USDJPY", "H1", "2026-08-05T10:00:00Z", "SELL", -2.5, 0),
    ])
    r = check_metrics(db)
    assert r["healthy"] is True
    assert r["anomalies"] == []


def test_detects_absurd_pnl(tmp_path):
    db = _make_db(tmp_path / "t.db", [
        ("EURUSD", "H1", "2026-08-05T10:00:00Z", "BUY", 500.0, 1),
    ])
    r = check_metrics(db)
    assert r["healthy"] is False
    types = [a["type"] for a in r["anomalies"]]
    assert "absurd_pnl" in types


def test_detects_duplicates(tmp_path):
    db = _make_db(tmp_path / "t.db", [
        ("EURUSD", "H1", "2026-08-05T10:00:00Z", "BUY", 5.0, 1),
        ("EURUSD", "H1", "2026-08-05T10:00:00Z", "BUY", 5.0, 1),
    ])
    r = check_metrics(db)
    assert r["healthy"] is False
    types = [a["type"] for a in r["anomalies"]]
    assert "duplicates" in types


def test_detects_jpy_factor(tmp_path):
    db = _make_db(tmp_path / "t.db", [
        ("USDJPY", "H1", "2026-08-05T10:00:00Z", "SELL", -250.0, 0),
    ])
    r = check_metrics(db)
    assert r["healthy"] is False
    types = [a["type"] for a in r["anomalies"]]
    assert "jpy_pip_factor" in types


def test_missing_db_fail_open(tmp_path):
    r = check_metrics(tmp_path / "absent.db")
    assert r["healthy"] is True
    assert r["reason"] == "db_missing"
