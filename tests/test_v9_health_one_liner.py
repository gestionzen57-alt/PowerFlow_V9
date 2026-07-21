"""tests/test_v9_health_one_liner.py — Tests du health one-liner.

Doctrine : R7 (tests verts), R8 (traçabilité), R22 (CLI lecture seule).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_health_one_liner import (  # noqa: E402
    SNAPSHOT_FRESH_SEC,
    collect_health,
    main,
    render_one_liner,
    _check_port,
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
    conn.execute(
        """
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY,
            opened_at TEXT,
            is_win INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            confiance INTEGER,
            is_win INTEGER,
            resolution_strategy TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    yield Path(db_path)
    import gc
    gc.collect()
    Path(db_path).unlink(missing_ok=True)


def test_check_port_open():
    """Port ouvert → True."""
    import socket
    # Crée un socket serveur temporaire
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(1)
    try:
        assert _check_port(port) is True
    finally:
        server.close()


def test_check_port_closed():
    """Port fermé → False."""
    assert _check_port(1) is False  # port 1 quasi jamais utilisé


def test_render_one_liner_includes_emoji():
    """Le rendu contient les emojis attendus."""
    health = {
        "all_ok": True,
        "pipeline": {"port": 31685, "active": True},
        "snapshot": {"age_sec": 30},
        "snapshot_fresh": True,
        "cvd": {"n_alive": 6, "n_total": 6},
        "cvd_full": True,
        "crons": {"ready": 20},
        "git": {"local": "abc12345", "aligned": True},
        "paper_trades_wr": {"wr": 64.0},
        "brier_7j": {"brier": 0.45},
        "brier_ok": True,
    }
    line = render_one_liner(health)
    assert "V9 ✅ OK" in line
    assert "🟢" in line
    assert "abc12345" in line
    assert "64.0%" in line


def test_render_one_liner_degraded():
    """Système dégradé → ligne contient ⚠️."""
    health = {
        "all_ok": False,
        "pipeline": {"port": 31685, "active": False},
        "snapshot": {"age_sec": 600},
        "snapshot_fresh": False,
        "cvd": {"n_alive": 3, "n_total": 6},
        "cvd_full": False,
        "crons": {"ready": 18},
        "git": {"local": "abc12345", "aligned": False},
        "paper_trades_wr": {"wr": 33.0},
        "brier_7j": {"brier": 0.50},
        "brier_ok": False,
    }
    line = render_one_liner(health)
    assert "⚠️ DEGRADED" in line
    assert "🔴" in line


def test_collect_health_no_db():
    """Sans DB → snapshot.exists=False, pas de crash."""
    with patch("scripts.v9_health_one_liner.DB_PATH", Path("/nonexistent.db")):
        health = collect_health()
    assert health["snapshot"]["exists"] is False
    assert health["all_ok"] is False  # pipe aussi KO


def test_collect_health_with_data(temp_db):
    """Avec DB peuplée → health complet."""
    conn = sqlite3.connect(str(temp_db))
    # Snapshot frais
    conn.execute(
        "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
        "VALUES (datetime('now', '-1 minute'), 'EURUSD', 'M1', 100)"
    )
    # CVD 6/6
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]:
        conn.execute(
            "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
            "VALUES (datetime('now', '-1 minute'), ?, 'M1', 100)",
            (sym,),
        )
    # 10 paper trades, 6 wins
    for i in range(10):
        conn.execute(
            "INSERT INTO paper_trades (opened_at, is_win) "
            "VALUES ('2026-07-20', ?)",
            (1 if i < 6 else 0,),
        )
    # 50 décisions DYNAMIC
    for i in range(50):
        conn.execute(
            "INSERT INTO decisions (timestamp, confiance, is_win, resolution_strategy) "
            "VALUES (datetime('now', '-1 day'), ?, ?, 'DYNAMIC')",
            (80, 1 if i % 2 == 0 else 0),
        )
    conn.commit()
    conn.close()

    # Mock _check_crons pour éviter le BOM Windows (encodage cp1252 sur FR)
    with patch("scripts.v9_health_one_liner.DB_PATH", temp_db):
        with patch.object(sys.modules["scripts.v9_health_one_liner"], "_check_crons", return_value={"ready": 20}):
            health = collect_health()

    assert health["snapshot"]["exists"] is True
    assert health["snapshot_fresh"] is True
    assert health["cvd"]["n_alive"] == 6
    assert health["cvd_full"] is True
    assert health["paper_trades_wr"]["n"] == 10
    assert health["paper_trades_wr"]["wr"] == 60.0


def test_main_json_output(temp_db, capsys):
    """CLI --json produit un JSON parsable."""
    conn = sqlite3.connect(str(temp_db))
    conn.commit()
    conn.close()

    with patch("scripts.v9_health_one_liner.DB_PATH", temp_db):
        with patch.object(sys, "argv", ["prog", "--json"]):
            rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "all_ok" in data
    assert "pipeline" in data


def test_main_one_liner_output(capsys):
    """CLI sans args → 1 ligne ASCII."""
    with patch.object(sys, "argv", ["prog"]):
        rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "V9" in captured.out
    assert "|" in captured.out


def test_main_exit_code_degraded(capsys):
    """CLI --exit-code + système dégradé → exit 1."""
    with patch("scripts.v9_health_one_liner.DB_PATH", Path("/nonexistent.db")):
        with patch.object(sys, "argv", ["prog", "--exit-code"]):
            rc = main()
    assert rc == 1
