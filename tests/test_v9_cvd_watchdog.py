"""tests/test_v9_cvd_watchdog.py — Tests du watchdog CVD.

Doctrine : R7 (tests verts), R22 (CLI lecture seule), R8 (traçabilité).
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_cvd_watchdog import (  # noqa: E402
    ALERT_COOLDOWN_SEC,
    EXPECTED_PAIRS,
    _fetch_cvd_state,
    _fetch_oldest_cvd_age,
    _last_alert_file,
    _mark_alerted,
    _should_alert,
    check_once,
    main,
    render_text,
)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            cvd_delta INTEGER
        )
        """
    )
    conn.commit()
    conn.close()
    yield Path(db_path)
    import gc
    gc.collect()
    Path(db_path).unlink(missing_ok=True)


# ── Tests _fetch_cvd_state ──────────────────────────────────────────

def test_fetch_cvd_state_no_db():
    """DB absente → error."""
    result = _fetch_cvd_state(Path("/nonexistent.db"))
    assert "error" in result


def test_fetch_cvd_state_all_alive(temp_db):
    """6 paires vivantes → all_alive=True."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for sym in EXPECTED_PAIRS:
        for i in range(3):
            ts = (now - timedelta(seconds=10 * i)).isoformat()
            conn.execute(
                "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
                "VALUES (?, ?, 'M1', 100)",
                (ts, sym),
            )
    conn.commit()
    conn.close()

    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        result = _fetch_cvd_state(temp_db)
    assert result["all_alive"] is True
    assert result["alive_count"] == 6
    assert result["missing"] == []


def test_fetch_cvd_state_missing_audusd(temp_db):
    """AUDUSD absent → all_alive=False, missing=['AUDUSD']."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF"]:
        for i in range(3):
            ts = (now - timedelta(seconds=10 * i)).isoformat()
            conn.execute(
                "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
                "VALUES (?, ?, 'M1', 100)",
                (ts, sym),
            )
    conn.commit()
    conn.close()

    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        result = _fetch_cvd_state(temp_db)
    assert result["all_alive"] is False
    assert "AUDUSD" in result["missing"]


# ── Tests _fetch_oldest_cvd_age ────────────────────────────────────

def test_fetch_oldest_cvd_age_fresh(temp_db):
    """CVD frais (< 60s) → age_sec petit."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for sym in EXPECTED_PAIRS:
        ts = (now - timedelta(seconds=10)).isoformat()
        conn.execute(
            "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
            "VALUES (?, ?, 'M1', 100)",
            (ts, sym),
        )
    conn.commit()
    conn.close()

    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        result = _fetch_oldest_cvd_age(temp_db)
    assert result["age_sec"] < 60
    assert result["oldest_pair"] in EXPECTED_PAIRS


def test_fetch_oldest_cvd_age_stale(temp_db):
    """CVD stale (> 1h) → age_sec > 3600."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for sym in EXPECTED_PAIRS:
        ts = (now - timedelta(hours=2)).isoformat()
        conn.execute(
            "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
            "VALUES (?, ?, 'M1', 100)",
            (ts, sym),
        )
    conn.commit()
    conn.close()

    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        result = _fetch_oldest_cvd_age(temp_db)
    assert result["age_sec"] > 3600


def test_fetch_oldest_cvd_age_empty(temp_db):
    """DB vide → age_sec=None."""
    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        result = _fetch_oldest_cvd_age(temp_db)
    assert result["age_sec"] is None


# ── Tests anti-spam alertes ─────────────────────────────────────────

def test_should_alert_no_file(tmp_path):
    """Pas de fichier → peut alerter."""
    with patch("scripts.v9_cvd_watchdog._last_alert_file", return_value=tmp_path / "absent"):
        assert _should_alert() is True


def test_should_alert_recent(tmp_path):
    """Fichier récent → ne peut PAS alerter (cooldown)."""
    f = tmp_path / "alert_ts"
    f.write_text(str(time.time()))
    with patch("scripts.v9_cvd_watchdog._last_alert_file", return_value=f):
        assert _should_alert() is False


def test_should_alert_old(tmp_path):
    """Fichier vieux (> cooldown) → peut alerter."""
    f = tmp_path / "alert_ts"
    f.write_text(str(time.time() - ALERT_COOLDOWN_SEC - 1))
    with patch("scripts.v9_cvd_watchdog._last_alert_file", return_value=f):
        assert _should_alert() is True


def test_mark_alerted(tmp_path):
    """Marquer une alerte écrit le timestamp."""
    f = tmp_path / "alert_ts"
    with patch("scripts.v9_cvd_watchdog._last_alert_file", return_value=f):
        _mark_alerted()
    assert f.exists()
    assert float(f.read_text()) > time.time() - 5


# ── Tests check_once ───────────────────────────────────────────────

def test_check_once_all_ok(temp_db):
    """CVD frais + 6 paires vivantes → verdict OK."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for sym in EXPECTED_PAIRS:
        for i in range(3):
            ts = (now - timedelta(seconds=10 * i)).isoformat()
            conn.execute(
                "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
                "VALUES (?, ?, 'M1', 100)",
                (ts, sym),
            )
    conn.commit()
    conn.close()

    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        report = check_once(threshold_sec=120, alert=False)
    assert report["level"] == "info"
    assert report["verdict"] == "✅ CVD OK"
    assert report["stale"] is False


def test_check_once_stale(temp_db):
    """CVD stale (> 120s) → verdict critical."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for sym in EXPECTED_PAIRS:
        ts = (now - timedelta(hours=2)).isoformat()
        conn.execute(
            "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
            "VALUES (?, ?, 'M1', 100)",
            (ts, sym),
        )
    conn.commit()
    conn.close()

    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        report = check_once(threshold_sec=120, alert=False)
    assert report["level"] == "critical"
    assert "STALE" in report["verdict"]
    assert report["stale"] is True
    assert report["cvd_age_sec"] > 120


def test_check_once_missing(temp_db):
    """AUDUSD KO → verdict warn."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF"]:
        for i in range(3):
            ts = (now - timedelta(seconds=10 * i)).isoformat()
            conn.execute(
                "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
                "VALUES (?, ?, 'M1', 100)",
                (ts, sym),
            )
    conn.commit()
    conn.close()

    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        report = check_once(threshold_sec=120, alert=False)
    assert report["level"] == "warn"
    assert "MISSING" in report["verdict"]


# ── Tests render_text ──────────────────────────────────────────────

def test_render_text_includes_verdict():
    """Le rendu texte contient le verdict."""
    report = {
        "checked_at": "2026-07-22T00:50:00+00:00",
        "verdict": "✅ CVD OK",
        "level": "info",
        "threshold_sec": 120,
        "state": {"expected_count": 6, "alive_count": 6, "missing": []},
        "oldest": {"age_sec": 30, "oldest_pair": "EURUSD", "oldest_ts": "2026-07-22T00:49:30Z"},
        "cvd_age_sec": 30,
        "stale": False,
        "missing": [],
    }
    text = render_text(report)
    assert "✅ CVD OK" in text
    assert "CVD Watchdog" in text


# ── Tests main ──────────────────────────────────────────────────────

def test_main_json_output(temp_db, capsys):
    """CLI --json produit JSON valide."""
    conn = sqlite3.connect(str(temp_db))
    conn.commit()
    conn.close()

    with patch("scripts.v9_cvd_watchdog.DB_PATH", temp_db):
        with patch.object(sys, "argv", ["prog", "--json"]):
            rc = main()
    assert rc in (0, 1)
    captured = capsys.readouterr()
    import json
    data = json.loads(captured.out)
    assert "verdict" in data
    assert "level" in data
