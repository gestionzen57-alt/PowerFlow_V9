"""tests/test_trade_engine_l3_time_exit_wired.py — Phase 4 motion CEO.

Vérifie que trade_engine.close_open_trades() force closure artifact pour
les paper_trades > 5min AVANT le cycle ExitSimulator.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _enable_l3(monkeypatch):
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "1")
    yield
    monkeypatch.delenv("V9_TIME_EXIT_ENABLED", raising=False)


@pytest.fixture
def tmp_db_with_paper_trades(tmp_path):
    """DB minimale + 2 paper_trades : un jeune (2min), un aged (10min)."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE paper_trades ("
            "trade_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "snapshot_id TEXT, direction TEXT, "
            "opened_at TEXT, closed_at TEXT, "
            "is_win INTEGER, pips_simulated REAL)"
        )
        conn.execute(
            "CREATE TABLE decisions ("
            "snapshot_id TEXT PRIMARY KEY, "
            "is_win INTEGER, decision_id TEXT, "
            "timestamp TEXT, symbol TEXT, timeframe TEXT, regime_type TEXT)"
        )
        conn.execute(
            "CREATE TABLE signals ("
            "snapshot_id TEXT, "
            "tp_pips_recommended REAL, sl_pips_recommended REAL, "
            "exit_strategy_recommended TEXT)"
        )
        now = datetime.utcnow()
        # Trade jeune (2min)
        conn.execute(
            "INSERT INTO paper_trades (snapshot_id, direction, opened_at, "
            "closed_at, is_win, pips_simulated) VALUES "
            "('s1', 'haussiere', ?, NULL, NULL, 0)",
            ((now - timedelta(minutes=2)).isoformat(),),
        )
        conn.execute(
            "INSERT INTO decisions VALUES ('s1', 1, 'd1', ?, 'GBPUSD', 'M5', 'TREND')",
            (now.isoformat(),),
        )
        conn.execute(
            "INSERT INTO signals VALUES ('s1', 25.0, 8.0, 'TRAILING')"
        )
        # Trade aged (10min)
        conn.execute(
            "INSERT INTO paper_trades (snapshot_id, direction, opened_at, "
            "closed_at, is_win, pips_simulated) VALUES "
            "('s2', 'haussiere', ?, NULL, NULL, 0)",
            ((now - timedelta(minutes=10)).isoformat(),),
        )
        conn.execute(
            "INSERT INTO decisions VALUES ('s2', 1, 'd2', ?, 'GBPUSD', 'M5', 'TREND')",
            ((now - timedelta(minutes=10)).isoformat(),),
        )
        conn.execute(
            "INSERT INTO signals VALUES ('s2', 25.0, 8.0, 'TRAILING')"
        )
        conn.commit()
    return db


def test_time_exit_force_close_aged_in_db(tmp_db_with_paper_trades):
    """time_exit_force_close ferme le aged, laisse le jeune."""
    from core.v9.v9_mega_edge_filter import time_exit_force_close
    res = time_exit_force_close(db_path=tmp_db_with_paper_trades)
    assert res["forced"] == 1
    assert res["skipped"] == 1
    assert res["artifact"] == 1

    with sqlite3.connect(str(tmp_db_with_paper_trades)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT trade_id, closed_at, is_win, pips_simulated "
            "FROM paper_trades ORDER BY trade_id"
        ).fetchall()
    # s1 = young → closed_at NULL
    assert rows[0]["closed_at"] is None
    # s2 = aged → closed_at set, is_win=0, pips=0
    assert rows[1]["closed_at"] is not None
    assert rows[1]["is_win"] == 0
    assert rows[1]["pips_simulated"] == 0.0


def test_time_exit_force_close_no_db(tmp_path):
    """DB absente → no-op, zeros."""
    from core.v9.v9_mega_edge_filter import time_exit_force_close
    res = time_exit_force_close(db_path=tmp_path / "absent.db")
    assert res == {"forced": 0, "skipped": 0, "artifact": 0}


def test_time_exit_force_close_idempotent(tmp_db_with_paper_trades):
    """2 appels consecutifs → 2e ne fait rien (aged deja ferme)."""
    from core.v9.v9_mega_edge_filter import time_exit_force_close
    res1 = time_exit_force_close(db_path=tmp_db_with_paper_trades)
    res2 = time_exit_force_close(db_path=tmp_db_with_paper_trades)
    assert res1["forced"] == 1
    assert res2["forced"] == 0


def test_time_exit_kill_switch_off_returns_zero(
    tmp_db_with_paper_trades, monkeypatch
):
    """V9_TIME_EXIT_ENABLED=0 + V9_MEGA_EDGE_ENABLED=0 → no-op."""
    from core.v9.v9_mega_edge_filter import time_exit_force_close
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "0")
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "0")
    res = time_exit_force_close(db_path=tmp_db_with_paper_trades)
    assert res == {"forced": 0, "skipped": 0, "artifact": 0}
    # Le aged n'est pas ferme
    with sqlite3.connect(str(tmp_db_with_paper_trades)) as conn:
        rows = conn.execute(
            "SELECT closed_at FROM paper_trades WHERE trade_id = 2"
        ).fetchall()
    assert rows[0][0] is None