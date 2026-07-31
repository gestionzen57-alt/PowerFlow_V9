"""tests/test_v9_pre_live_check.py — Phase 14 motion CEO « EDGE FUND MAX »."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest


@pytest.fixture
def workspace_ok(tmp_path, monkeypatch):
    """Workspace avec DB OK, bridge OK, mirror 25 trades, heartbeat recent."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    db = workspace / "v9.db"

    # DB avec tables minimales
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE forces_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE v9_human_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, symbol TEXT, direction TEXT
            )
        """)
        conn.execute("""
            INSERT INTO forces_snapshots VALUES (1, 'v9-test',
                ?)
        """, (datetime.utcnow().isoformat(),))
        for i in range(25):
            conn.execute("""
                INSERT INTO v9_human_trades (timestamp, symbol, direction)
                VALUES (?, 'GBPUSD', 'haussiere')
            """, (datetime.utcnow().isoformat(),))
        conn.commit()

    # Bridge MT4 minimal
    (workspace / "mt4_bridge").mkdir()
    (workspace / "mt4_bridge" / "V9_OrderBridge.mq4").write_text("""
extern string  OrderQueuePath = "test";
extern string  ProcessedPath  = "test/p";
extern string  FailedPath     = "test/f";
extern int     PollSeconds    = 5;
extern int     Slippage       = 3;
extern int     MagicNumber    = 90900001;
extern bool    DryRun         = true;
""", encoding="utf-8")

    # Force DB_PATH du workspace
    monkeypatch.setattr("core.v9.config.DB_PATH", db)
    monkeypatch.setenv("V9_BOOT_CONTEXT", "pytest")  # silence BUG-P1
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "1")
    monkeypatch.setenv("V9_DRM_HUMAN_PROFILE_ENABLED", "0")
    monkeypatch.setenv("V9_HUMAN_MIRROR_BLOCKING", "0")

    return workspace, db


def test_run_all_checks_workspace_ok(workspace_ok):
    """Tous checks OK en workspace_ok."""
    from scripts.v9_pre_live_check import run_all_checks
    workspace, db = workspace_ok
    result = run_all_checks(workspace)
    assert "orderbridge" in result["checks"]
    assert "heartbeat" in result["checks"]
    assert "boot_alerts" in result["checks"]
    assert "mirror" in result["checks"]


def test_pre_live_check_json_output(workspace_ok, capsys):
    """main() retourne JSON valide."""
    from scripts.v9_pre_live_check import main
    workspace, db = workspace_ok
    exit_code = main([str(workspace)])
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert "checks" in out
    assert "recommendation" in out


def test_pre_live_check_blocking_human_actions_listed():
    """Le rapport liste les 3 actions bloquantes humaines."""
    from scripts.v9_pre_live_check import run_all_checks
    result = run_all_checks()
    assert "blocking_human_actions" in result
    assert len(result["blocking_human_actions"]) == 3
    assert any("Telegram" in a for a in result["blocking_human_actions"])
    assert any("expectancy" in a for a in result["blocking_human_actions"])
    assert any("MD5" in a for a in result["blocking_human_actions"])