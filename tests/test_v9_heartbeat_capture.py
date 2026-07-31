"""tests/test_v9_heartbeat_capture.py — Phase 13 motion CEO « EDGE FUND MAX ».

R3 Perplexity : MT4 capture_server heartbeat absent.
"""
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest


def _build_db_with_snapshot(db, ts_iso):
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE forces_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, timestamp TEXT
            )
        """)
        conn.execute(
            "INSERT INTO forces_snapshots (snapshot_id, timestamp) VALUES (?, ?)",
            ("v9-test-snap", ts_iso),
        )
        conn.commit()


def test_get_age_missing_db(tmp_path):
    """DB absente → None."""
    from scripts.v9_heartbeat_capture import get_last_snapshot_age_minutes
    res = get_last_snapshot_age_minutes(tmp_path / "absent.db")
    assert res is None


def test_get_age_empty_table(tmp_path):
    """Table vide → None."""
    from scripts.v9_heartbeat_capture import get_last_snapshot_age_minutes
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (timestamp TEXT)")
        conn.commit()
    res = get_last_snapshot_age_minutes(db)
    assert res is None


def test_get_age_recent_snapshot(tmp_path):
    """Snapshot recent → age faible."""
    from scripts.v9_heartbeat_capture import get_last_snapshot_age_minutes
    db = tmp_path / "v9.db"
    recent = datetime.utcnow() - timedelta(minutes=1)
    _build_db_with_snapshot(db, recent.isoformat())
    res = get_last_snapshot_age_minutes(db)
    assert res is not None
    assert res < 2.0  # < 2 minutes


def test_get_age_old_snapshot(tmp_path):
    """Snapshot vieux → age eleve."""
    from scripts.v9_heartbeat_capture import get_last_snapshot_age_minutes
    db = tmp_path / "v9.db"
    old = datetime.utcnow() - timedelta(hours=2)
    _build_db_with_snapshot(db, old.isoformat())
    res = get_last_snapshot_age_minutes(db)
    assert res is not None
    assert res > 100  # > 100 minutes


def test_check_heartbeat_ok(tmp_path, monkeypatch):
    """Snapshot recent → ok=True, no alert."""
    db = tmp_path / "v9.db"
    recent = datetime.utcnow() - timedelta(seconds=30)
    _build_db_with_snapshot(db, recent.isoformat())

    from scripts.v9_heartbeat_capture import check_heartbeat
    res = check_heartbeat(db, max_age_minutes=5.0)
    assert res["ok"] is True
    assert res["alert"] is False


def test_check_heartbeat_alert_silence(tmp_path):
    """Snapshot > 5min → alert capture_silence."""
    db = tmp_path / "v9.db"
    old = datetime.utcnow() - timedelta(minutes=10)
    _build_db_with_snapshot(db, old.isoformat())

    from scripts.v9_heartbeat_capture import check_heartbeat
    res = check_heartbeat(db, max_age_minutes=5.0)
    assert res["ok"] is False
    assert res["alert"] is True
    assert res["reason"] == "capture_silence"


def test_check_heartbeat_alert_no_ever(tmp_path):
    """Table vide → alert no_snapshot_ever."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE forces_snapshots (timestamp TEXT)")
        conn.commit()

    from scripts.v9_heartbeat_capture import check_heartbeat
    res = check_heartbeat(db)
    assert res["ok"] is False
    assert res["reason"] == "no_snapshot_ever"


def test_check_heartbeat_env_threshold(monkeypatch, tmp_path):
    """V9_HEARTBEAT_MAX_AGE_MINUTES=2 → seuil custom."""
    db = tmp_path / "v9.db"
    recent = datetime.utcnow() - timedelta(seconds=180)  # 3 min
    _build_db_with_snapshot(db, recent.isoformat())
    monkeypatch.setenv("V9_HEARTBEAT_MAX_AGE_MINUTES", "2")

    from scripts.v9_heartbeat_capture import check_heartbeat
    res = check_heartbeat(db)
    assert res["alert"] is True
    assert res["max_age_minutes"] == 2.0


def test_main_returns_exit_code_alert(tmp_path, monkeypatch, capsys):
    """CLI main() retourne 1 si alert, 0 si ok."""
    db = tmp_path / "v9.db"
    recent = datetime.utcnow() - timedelta(minutes=10)  # > seuil
    _build_db_with_snapshot(db, recent.isoformat())

    monkeypatch.setattr("core.v9.config.DB_PATH", db)
    monkeypatch.setattr("sys.argv", ["v9_heartbeat_capture.py"])

    from scripts.v9_heartbeat_capture import main
    exit_code = main([])
    captured = capsys.readouterr()
    out = json.loads(captured.out)

    assert exit_code == 1
    assert out["alert"] is True


def test_main_returns_exit_code_ok(tmp_path, monkeypatch, capsys):
    """CLI main() retourne 0 si heartbeat ok."""
    db = tmp_path / "v9.db"
    recent = datetime.utcnow() - timedelta(seconds=10)
    _build_db_with_snapshot(db, recent.isoformat())

    monkeypatch.setattr("core.v9.config.DB_PATH", db)
    monkeypatch.setattr("sys.argv", ["v9_heartbeat_capture.py"])

    from scripts.v9_heartbeat_capture import main
    exit_code = main([])
    captured = capsys.readouterr()
    out = json.loads(captured.out)

    assert exit_code == 0
    assert out["ok"] is True