"""tests/test_v9_mirror_check.py — Phase 14 motion CEO « EDGE FUND MAX »."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest


def _create_db_with_human_trades(db, n):
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_human_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                direction TEXT
            )
        """)
        for i in range(n):
            conn.execute("""
                INSERT INTO v9_human_trades (timestamp, symbol, direction)
                VALUES (?, 'GBPUSD', 'haussiere')
            """, (datetime.utcnow().isoformat(),))
        conn.commit()


def test_count_human_trades_empty(tmp_path):
    """count_human_trades = 0 si table absente."""
    from scripts.v9_mirror_check import count_human_trades
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE other (x INTEGER)")
        conn.commit()
    assert count_human_trades(db) == 0


def test_count_human_trades_present(tmp_path):
    """count_human_trades = N si N trades en DB."""
    from scripts.v9_mirror_check import count_human_trades
    db = tmp_path / "v9.db"
    _create_db_with_human_trades(db, 25)
    assert count_human_trades(db) == 25


def test_count_human_trades_missing_db(tmp_path):
    """count_human_trades = 0 si DB absente."""
    from scripts.v9_mirror_check import count_human_trades
    assert count_human_trades(tmp_path / "absent.db") == 0


def test_check_mirror_blocking_disabled(tmp_path):
    """BLOCKING désactivé → pas d'alerte."""
    db = tmp_path / "v9.db"
    monkeypatch_test = pytest.MonkeyPatch()
    monkeypatch_test.setenv("V9_HUMAN_MIRROR_BLOCKING", "0")
    from scripts.v9_mirror_check import check_mirror_readiness
    res = check_mirror_readiness(db)
    monkeypatch_test.undo()
    assert res["alert"] is False
    assert res["blocking_enabled"] is False
    assert res["recommendation"] == "blocking_disabled_no_action"


def test_check_mirror_blocking_no_data(tmp_path, monkeypatch):
    """BLOCKING ON mais 0 trades → ALERT log_human_trades_first."""
    db = tmp_path / "v9.db"
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "1")
    from scripts.v9_mirror_check import check_mirror_readiness
    res = check_mirror_readiness(db)
    assert res["alert"] is True
    assert res["recommendation"] == "log_human_trades_first"


def test_check_mirror_blocking_insufficient(tmp_path, monkeypatch):
    """BLOCKING ON mais 10 trades (< 20) → ALERT."""
    db = tmp_path / "v9.db"
    _create_db_with_human_trades(db, 10)
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "1")
    from scripts.v9_mirror_check import check_mirror_readiness
    res = check_mirror_readiness(db)
    assert res["alert"] is True
    assert res["n_human_trades"] == 10


def test_check_mirror_blocking_sufficient(tmp_path, monkeypatch):
    """BLOCKING ON avec 25 trades → OK pas d'alerte."""
    db = tmp_path / "v9.db"
    _create_db_with_human_trades(db, 25)
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "1")
    from scripts.v9_mirror_check import check_mirror_readiness
    res = check_mirror_readiness(db)
    assert res["alert"] is False
    assert res["recommendation"] == "ok_blocking_active"


def test_check_mirror_threshold_exactly_20(tmp_path, monkeypatch):
    """Seuil exact 20 trades → OK (>=)."""
    db = tmp_path / "v9.db"
    _create_db_with_human_trades(db, 20)
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "1")
    from scripts.v9_mirror_check import check_mirror_readiness
    res = check_mirror_readiness(db)
    assert res["alert"] is False


def test_main_cli_blocking_disabled(tmp_path, monkeypatch, capsys):
    """CLI exit 0 si pas d'alerte."""
    db = tmp_path / "v9.db"
    _create_db_with_human_trades(db, 25)
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "0")
    monkeypatch.setattr("core.v9.config.DB_PATH", db)
    monkeypatch.setattr("sys.argv", ["v9_mirror_check.py"])

    from scripts.v9_mirror_check import main
    exit_code = main([])
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert exit_code == 0
    assert out["alert"] is False


def test_main_cli_blocking_alert(tmp_path, monkeypatch, capsys):
    """CLI exit 1 si alerte."""
    db = tmp_path / "v9.db"
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "1")
    monkeypatch.setattr("core.v9.config.DB_PATH", db)
    monkeypatch.setattr("sys.argv", ["v9_mirror_check.py"])

    from scripts.v9_mirror_check import main
    exit_code = main([])
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert exit_code == 1
    assert out["alert"] is True