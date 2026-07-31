"""tests/test_v9_cron_pipeline.py — Phase 7 motion CEO « EDGE FUND MAX »."""
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setenv("V9_MEGA_EDGE_ENABLED", "1")
    monkeypatch.setenv("V9_AUTO_PROMOTE_STARS_ENABLED", "1")
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "1")
    yield
    for k in ("V9_MEGA_EDGE_ENABLED", "V9_AUTO_PROMOTE_STARS_ENABLED",
              "V9_TIME_EXIT_ENABLED"):
        monkeypatch.delenv(k, raising=False)


def test_cron_pipeline_runs_end_to_end(tmp_path, monkeypatch):
    """Pipeline complet execute walk_forward + auto_promote + time_exit."""
    # Override DB_PATH pour pointer sur tmp
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE paper_trades ("
            "trade_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "snapshot_id TEXT, symbol TEXT, direction TEXT, "
            "opened_at TEXT, closed_at TEXT, is_win INTEGER, pips_simulated REAL)"
        )
        conn.execute(
            "CREATE TABLE forces_snapshots ("
            "snapshot_id TEXT PRIMARY KEY, timestamp TEXT)"
        )
        # Seed 5 trades GBPUSD haussiere 12h UTC recents
        base = datetime.utcnow() - timedelta(days=10)
        base = base.replace(hour=12, minute=0, second=0, microsecond=0)
        for i in range(5):
            ts = base + timedelta(minutes=i * 10)
            snap = f"v9-GBPUSD-M5-test-{i}"
            conn.execute(
                "INSERT INTO forces_snapshots VALUES (?, ?)",
                (snap, ts.isoformat()),
            )
            conn.execute(
                "INSERT INTO paper_trades (snapshot_id, symbol, direction, "
                "opened_at, closed_at, is_win, pips_simulated) VALUES "
                "(?, 'GBPUSD', 'haussiere', ?, ?, 1, 10.0)",
                (snap, ts.isoformat(), ts.isoformat()),
            )
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", db)

    from scripts.v9_cron_pipeline import run_pipeline
    monkeypatch.setattr("scripts.v9_walk_forward.DB_PATH", db)
    monkeypatch.setattr("scripts.v9_close_time_exit.DB_PATH", db)
    monkeypatch.setattr("core.v9.config.DB_PATH", db)
    res = run_pipeline()
    assert "walk_forward" in res
    assert "auto_promote" in res
    assert "time_exit" in res
    assert res["ok"] is True


def test_cron_pipeline_alert_on_low_wr(tmp_path, monkeypatch):
    """Si WR < 60% et n_total > 20 → alert wr_below_threshold."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE paper_trades ("
            "trade_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "snapshot_id TEXT, symbol TEXT, direction TEXT, "
            "opened_at TEXT, closed_at TEXT, is_win INTEGER, pips_simulated REAL)"
        )
        conn.execute(
            "CREATE TABLE forces_snapshots ("
            "snapshot_id TEXT PRIMARY KEY, timestamp TEXT)"
        )
        # Seed 25 trades GBPUSD haussier 12h UTC, tous perdants (WR 0%)
        base = datetime.utcnow() - timedelta(days=10)
        base = base.replace(hour=12, minute=0, second=0, microsecond=0)
        for i in range(25):
            ts = base + timedelta(minutes=i * 5)
            snap = f"v9-GBPUSD-M5-bad-{i}"
            conn.execute(
                "INSERT INTO forces_snapshots VALUES (?, ?)",
                (snap, ts.isoformat()),
            )
            conn.execute(
                "INSERT INTO paper_trades (snapshot_id, symbol, direction, "
                "opened_at, closed_at, is_win, pips_simulated) VALUES "
                "(?, 'GBPUSD', 'haussiere', ?, ?, 0, -10.0)",
                (snap, ts.isoformat(), ts.isoformat()),
            )
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", db)

    from scripts.v9_cron_pipeline import run_pipeline
    # Patch DB_PATH dans les 3 sous-scripts (import est figé au chargement)
    monkeypatch.setattr("scripts.v9_walk_forward.DB_PATH", db)
    monkeypatch.setattr("scripts.v9_close_time_exit.DB_PATH", db)
    monkeypatch.setattr("core.v9.config.DB_PATH", db)
    res = run_pipeline()
    # Walk-forward doit retourner WR < 60% → alert
    assert res.get("alert") == "wr_below_threshold"


def test_cron_pipeline_log_path():
    """Le logger pointe vers data/v9_cron_pipeline.log."""
    from scripts.v9_cron_pipeline import LOG_PATH
    assert str(LOG_PATH).endswith("v9_cron_pipeline.log")