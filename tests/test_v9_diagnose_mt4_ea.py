"""tests/test_v9_diagnose_mt4_ea.py — Tests du diagnostic MT4/EA.

Doctrine : R7 (tests verts), R22 (CLI lecture seule), R8 (traçabilité).
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_diagnose_mt4_ea import (  # noqa: E402
    PIPELINE_PORT,
    SNAPSHOT_FRESH_SEC,
    _check_active_connections,
    _check_brier_wr,
    _check_capture_server_process,
    _check_cvd_live,
    _check_decisions_recent,
    _check_port_listening,
    _check_snapshot_freshness,
    diagnose,
    main,
    render_text,
)


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            cvd_delta INTEGER
        );
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            confiance INTEGER,
            is_win INTEGER,
            resolution_pips REAL,
            resolution_strategy TEXT
        );
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY,
            opened_at TEXT,
            is_win INTEGER
        );
    """)
    conn.commit()
    conn.close()
    yield Path(db_path)
    import gc
    gc.collect()
    Path(db_path).unlink(missing_ok=True)


# ── Tests _check_port_listening ──────────────────────────────────────

def test_check_port_listening_open():
    """Port ouvert → listening=True."""
    import socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(1)
    try:
        result = _check_port_listening(port)
        assert result["listening"] is True
    finally:
        server.close()


def test_check_port_listening_closed():
    """Port fermé → listening=False."""
    result = _check_port_listening(1)  # Port 1 quasi jamais utilisé
    assert result["listening"] is False


# ── Tests _check_snapshot_freshness ─────────────────────────────────

def test_check_snapshot_freshness_no_db():
    """DB absente → error."""
    result = _check_snapshot_freshness()
    # Ne crash pas, retourne un dict
    assert "last_ts" in result or "error" in result


def test_check_snapshot_freshness_fresh(temp_db):
    """Snapshot < 5min → fresh=True."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    ts = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    conn.execute(
        "INSERT INTO forces_snapshots (timestamp, symbol, timeframe) VALUES (?, 'EURUSD', 'M1')",
        (ts,),
    )
    conn.commit()
    conn.close()

    with patch("scripts.v9_diagnose_mt4_ea.DB_PATH", temp_db):
        result = _check_snapshot_freshness()
    assert result["fresh"] is True
    assert result["age_sec"] < SNAPSHOT_FRESH_SEC


def test_check_snapshot_freshness_stale(temp_db):
    """Snapshot > 5min → fresh=False."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    conn.execute(
        "INSERT INTO forces_snapshots (timestamp, symbol, timeframe) VALUES (?, 'EURUSD', 'M1')",
        (ts,),
    )
    conn.commit()
    conn.close()

    with patch("scripts.v9_diagnose_mt4_ea.DB_PATH", temp_db):
        result = _check_snapshot_freshness()
    assert result["fresh"] is False
    assert result["age_sec"] > 3600


# ── Tests _check_cvd_live ──────────────────────────────────────────

def test_check_cvd_live_all_alive(temp_db):
    """CVD 6/6 → all_alive=True."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    pairs = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]
    for sym in pairs:
        for i in range(5):
            ts = (now - timedelta(minutes=i)).isoformat()
            conn.execute(
                "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
                "VALUES (?, ?, 'M1', 100)",
                (ts, sym),
            )
    conn.commit()
    conn.close()

    with patch("scripts.v9_diagnose_mt4_ea.DB_PATH", temp_db):
        result = _check_cvd_live()
    assert result["all_alive"] is True
    assert result["alive_count"] == 6
    assert result["missing"] == []


def test_check_cvd_live_missing_audusd(temp_db):
    """AUDUSD KO → all_alive=False, missing=['AUDUSD']."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    pairs = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF"]  # AUDUSD absent
    for sym in pairs:
        for i in range(5):
            ts = (now - timedelta(minutes=i)).isoformat()
            conn.execute(
                "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
                "VALUES (?, ?, 'M1', 100)",
                (ts, sym),
            )
    conn.commit()
    conn.close()

    with patch("scripts.v9_diagnose_mt4_ea.DB_PATH", temp_db):
        result = _check_cvd_live()
    assert result["all_alive"] is False
    assert result["alive_count"] == 5
    assert "AUDUSD" in result["missing"]


# ── Tests _check_decisions_recent ──────────────────────────────────

def test_check_decisions_recent_empty(temp_db):
    """DB vide → by_day vide."""
    with patch("scripts.v9_diagnose_mt4_ea.DB_PATH", temp_db):
        result = _check_decisions_recent()
    assert result["by_day"] == []


def test_check_decisions_recent_basic(temp_db):
    """3 jours de décisions → 3 entrées."""
    conn = sqlite3.connect(str(temp_db))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    for d in range(3):
        ts = (now - timedelta(days=d)).isoformat()
        conn.execute(
            "INSERT INTO decisions (timestamp, symbol, timeframe, is_win, resolution_pips, resolution_strategy) "
            "VALUES (?, 'GBPUSD', 'M15', ?, ?, 'DYNAMIC')",
            (ts, 1 if d % 2 == 0 else 0, 5.0 if d % 2 == 0 else -3.0),
        )
    conn.commit()
    conn.close()

    with patch("scripts.v9_diagnose_mt4_ea.DB_PATH", temp_db):
        result = _check_decisions_recent()
    assert len(result["by_day"]) == 3


# ── Tests _check_brier_wr ──────────────────────────────────────────

def test_check_brier_wr_empty(temp_db):
    """DB vide → brier=None, wr=None."""
    with patch("scripts.v9_diagnose_mt4_ea.DB_PATH", temp_db):
        result = _check_brier_wr()
    assert result["brier_7j"] is None


def test_check_brier_wr_basic(temp_db):
    """10 décisions DYNAMIC → brier + wr calculés."""
    conn = sqlite3.connect(str(temp_db))
    # 10 décisions : conf=50 + WR=100% → Brier = mean((0.5-1)^2) = 0.25
    for i in range(10):
        conn.execute(
            "INSERT INTO decisions (timestamp, symbol, timeframe, confiance, is_win, resolution_strategy) "
            "VALUES (datetime('now', '-1 day'), 'GBPUSD', 'M15', 50, 1, 'DYNAMIC')"
        )
    # 10 paper trades après 2026-07-18 : 6 wins / 10 = 60% WR
    for i in range(10):
        conn.execute(
            "INSERT INTO paper_trades (opened_at, is_win) VALUES ('2026-07-19', ?)",
            (1 if i < 6 else 0,),
        )
    conn.commit()
    conn.close()

    with patch("scripts.v9_diagnose_mt4_ea.DB_PATH", temp_db):
        result = _check_brier_wr()
    assert result["brier_7j"] is not None
    # conf=50 + WR=100% → 10 × (0.5-1)^2 / 10 = 0.25
    assert abs(result["brier_7j"] - 0.25) < 0.01
    assert result["wr_7j_pct"] == 60.0  # 6/10 = 60%
    assert result["n_paper_7j"] == 10


# ── Tests diagnose ──────────────────────────────────────────────────

def test_diagnose_structure():
    """diagnose() retourne un dict structuré."""
    report = diagnose()
    assert "generated_at" in report
    assert "pipeline" in report
    assert "cvd" in report
    assert "snapshot" in report
    assert "decisions" in report
    assert "metrics" in report
    assert "verdict" in report
    assert "n_issues" in report


def test_diagnose_live():
    """Diagnostic live sur la DB réelle."""
    report = diagnose()
    # Verdict peut être OK ou KO selon l'état live
    assert "verdict" in report
    assert report["n_issues"] >= 0


# ── Tests render_text ───────────────────────────────────────────────

def test_render_text_includes_sections():
    """Le rendu texte contient les sections attendues."""
    report = diagnose()
    text = render_text(report)
    assert "Diagnostic MT4/EA" in text
    assert "PIPELINE" in text
    assert "CVD LIVE" in text
    assert "SNAPSHOT" in text
    assert "DÉCISIONS" in text
    assert "MÉTRIQUES" in text


# ── Tests main ──────────────────────────────────────────────────────

def test_main_json_output(capsys):
    """CLI --json produit JSON valide."""
    with patch.object(sys, "argv", ["prog", "--json"]):
        rc = main()
    assert rc in (0, 1)
    captured = capsys.readouterr()
    import json
    data = json.loads(captured.out)
    assert "pipeline" in data
    assert "cvd" in data
    assert "verdict" in data
