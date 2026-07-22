"""tests/test_v9_market_brief.py — Tests du brief marché Telegram.

Doctrine : R7 (tests verts), R22 (CLI lecture seule), R8 (traçabilité).
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_market_brief import (  # noqa: E402
    detect_alerts,
    fetch_stats,
    main,
    render_brief,
    send_telegram,
)
from core.v9._time_windows import get_session_now  # noqa: E402


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            confiance INTEGER,
            is_win INTEGER,
            resolution_pips REAL,
            resolution_strategy TEXT,
            regime_type TEXT
        );
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            cvd_delta INTEGER
        );
    """)
    conn.commit()
    conn.close()
    yield Path(db_path)
    import gc
    gc.collect()
    Path(db_path).unlink(missing_ok=True)


# ── Tests get_session_now (via _time_windows) ─────────────────────────

def test_current_session_asia():
    """00-07 UTC → ASIE."""
    dt = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)
    assert "ASIE" in get_session_now(dt)


def test_current_session_london():
    """07-12 UTC → LONDRES."""
    dt = datetime(2026, 7, 21, 9, 0, tzinfo=timezone.utc)
    assert "LONDRES" in get_session_now(dt)


def test_current_session_overlap():
    """12-16 UTC → OVERLAP."""
    dt = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    assert "OVERLAP" in get_session_now(dt)


def test_current_session_ny():
    """16-21 UTC → NEW YORK."""
    dt = datetime(2026, 7, 21, 18, 0, tzinfo=timezone.utc)
    assert "NEW_YORK" in get_session_now(dt)


def test_current_session_after_hours():
    """21-24 UTC → AFTER_HOURS."""
    dt = datetime(2026, 7, 21, 23, 0, tzinfo=timezone.utc)
    assert "AFTER_HOURS" in get_session_now(dt)


# ── Tests fetch_stats ──────────────────────────────────────────────────

def test_fetch_stats_no_db():
    """DB absente → error."""
    stats = fetch_stats(Path("/nonexistent.db"), 4)
    assert "error" in stats


def test_fetch_stats_empty_db(temp_db):
    """DB vide → stats rolling à 0."""
    stats = fetch_stats(temp_db, 4)
    assert "error" not in stats
    assert stats["24h_rolling"]["n"] == 0
    assert stats["by_symbol"] == {}


def test_fetch_stats_basic(temp_db):
    """Quelques décisions → stats correctes."""
    conn = sqlite3.connect(str(temp_db))
    now = datetime.now(timezone.utc)
    # 8 trades GBPUSD M15 dans fenêtre 4h (les 2 plus anciens > 4h)
    for i in range(8):
        ts = (now - timedelta(minutes=15 * i)).isoformat()  # 0, 15, 30, 45, 60, 75, 90, 105 min
        is_win = 1 if i < 5 else 0  # 5/8 = 62.5%
        pips = 5 if is_win else -8
        conn.execute(
            "INSERT INTO decisions (timestamp, symbol, timeframe, is_win, resolution_pips, resolution_strategy) "
            "VALUES (?, 'GBPUSD', 'M15', ?, ?, 'DYNAMIC')",
            (ts, is_win, pips),
        )
    # 5 trades USDJPY
    for i in range(5):
        ts = (now - timedelta(minutes=10 * i)).isoformat()
        is_win = 1 if i < 2 else 0
        pips = 3 if is_win else -6
        conn.execute(
            "INSERT INTO decisions (timestamp, symbol, timeframe, is_win, resolution_pips, resolution_strategy) "
            "VALUES (?, 'USDJPY', 'M15', ?, ?, 'DYNAMIC')",
            (ts, is_win, pips),
        )
    # 2 trades EURUSD (sous le seuil n>=3)
    for i in range(2):
        ts = (now - timedelta(minutes=5 * i)).isoformat()
        conn.execute(
            "INSERT INTO decisions (timestamp, symbol, timeframe, is_win, resolution_pips, resolution_strategy) "
            "VALUES (?, 'EURUSD', 'M15', 1, 3, 'DYNAMIC')",
            (ts,),
        )
    conn.commit()
    conn.close()

    stats = fetch_stats(temp_db, 4)
    assert stats["by_symbol"]["GBPUSD"]["n"] == 8
    assert stats["by_symbol"]["GBPUSD"]["wr_pct"] == 62.5
    assert stats["by_symbol"]["USDJPY"]["n"] == 5
    # EURUSD exclu car n<3
    assert "EURUSD" not in stats["by_symbol"]


def test_fetch_stats_brier(temp_db):
    """Brier calculé sur fenêtre 7j.

    Conf=50 + WR=50% → Brier ≈ 0 (parfait)
    Conf=100 + WR=50% → Brier ≈ 0.25 (aléatoire)
    Conf=50 + WR=100% → Brier ≈ 0.25 (aléatoire dans l'autre sens)
    """
    conn = sqlite3.connect(str(temp_db))
    now = datetime.now(timezone.utc)
    # 20 décisions avec conf=50 mais WR=100% → Brier = mean((0.5-1)^2) = 0.25
    for i in range(20):
        ts = (now - timedelta(days=i % 5)).isoformat()
        conn.execute(
            "INSERT INTO decisions (timestamp, symbol, timeframe, confiance, is_win, resolution_strategy) "
            "VALUES (?, 'GBPUSD', 'M15', 50, 1, 'DYNAMIC')",
            (ts,),
        )
    conn.commit()
    conn.close()

    stats = fetch_stats(temp_db, 4)
    assert stats["brier_7j"] is not None
    # Brier = 20 × 0.25 / 20 = 0.25
    assert abs(stats["brier_7j"] - 0.25) < 0.05


def test_fetch_stats_cvd_alive(temp_db):
    """CVD alive détecté par paire."""
    conn = sqlite3.connect(str(temp_db))
    now = datetime.now(timezone.utc)
    for sym in ["EURUSD", "GBPUSD", "USDJPY"]:
        for i in range(5):
            ts = (now - timedelta(minutes=i)).isoformat()
            conn.execute(
                "INSERT INTO forces_snapshots (timestamp, symbol, timeframe, cvd_delta) "
                "VALUES (?, ?, 'M1', 100)",
                (ts, sym),
            )
    conn.commit()
    conn.close()

    stats = fetch_stats(temp_db, 4)
    assert set(stats["cvd_alive"]) == {"EURUSD", "GBPUSD", "USDJPY"}


# ── Tests detect_alerts ───────────────────────────────────────────────

def test_detect_alerts_no_db():
    """DB absente → 1 alerte warning."""
    stats = {"error": "DB absente"}
    alerts = detect_alerts(stats, 4)
    assert len(alerts) == 1
    assert "DB inaccessible" in alerts[0]


def test_detect_alerts_low_wr():
    """WR < 30% sur n>=5 → alerte DANGER."""
    stats = {
        "by_symbol": {
            "GBPUSD": {"n": 10, "wr_pct": 25.0, "avg_pips": -2.0, "total_pips": -20.0},
        },
        "24h_rolling": {"n": 100, "wr_pct": 50.0, "pips": 100.0},
        "cvd_alive": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"],
        "cvd_total_pairs": 6,
        "brier_7j": 0.25,
    }
    alerts = detect_alerts(stats, 4)
    assert any("DANGER" in a for a in alerts)


def test_detect_alerts_strong_edge():
    """Expectancy > 5 pips → alerte MOMENTUM."""
    stats = {
        "by_symbol": {
            "GBPUSD": {"n": 10, "wr_pct": 70.0, "avg_pips": 8.0, "total_pips": 80.0},
        },
        "24h_rolling": {"n": 100, "wr_pct": 50.0, "pips": 100.0},
        "cvd_alive": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"],
        "cvd_total_pairs": 6,
        "brier_7j": 0.25,
    }
    alerts = detect_alerts(stats, 4)
    assert any("momentum" in a for a in alerts)


def test_detect_alerts_cvd_ko():
    """CVD KO sur certaines paires → alerte CVD."""
    stats = {
        "by_symbol": {},
        "24h_rolling": {"n": 0, "wr_pct": 0, "pips": 0},
        "cvd_alive": ["EURUSD", "GBPUSD"],  # 4 KO
        "cvd_total_pairs": 6,
        "brier_7j": 0.25,
    }
    alerts = detect_alerts(stats, 4)
    assert any("CVD KO" in a for a in alerts)


def test_detect_alerts_brier_critical():
    """Brier > 0.40 → alerte ANTI-CALIBRÉ."""
    stats = {
        "by_symbol": {},
        "24h_rolling": {"n": 0, "wr_pct": 0, "pips": 0},
        "cvd_alive": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"],
        "cvd_total_pairs": 6,
        "brier_7j": 0.4467,
    }
    alerts = detect_alerts(stats, 4)
    assert any("anti-calibré" in a for a in alerts)


def test_detect_alerts_negative_day():
    """24h rolling < -100 pips → alerte PERTES."""
    stats = {
        "by_symbol": {},
        "24h_rolling": {"n": 50, "wr_pct": 30.0, "pips": -150.0},
        "cvd_alive": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"],
        "cvd_total_pairs": 6,
        "brier_7j": 0.25,
    }
    alerts = detect_alerts(stats, 4)
    assert any("Pertes 24h" in a for a in alerts)


def test_detect_alerts_no_alerts():
    """Aucune condition d'alerte → liste vide."""
    stats = {
        "by_symbol": {
            "GBPUSD": {"n": 10, "wr_pct": 60.0, "avg_pips": 2.0, "total_pips": 20.0},
        },
        "24h_rolling": {"n": 100, "wr_pct": 55.0, "pips": 150.0},
        "cvd_alive": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"],
        "cvd_total_pairs": 6,
        "brier_7j": 0.20,
    }
    alerts = detect_alerts(stats, 4)
    assert alerts == []


# ── Tests render_brief ─────────────────────────────────────────────────

def test_render_brief_basic(temp_db):
    """Brief rendu avec sections attendues (DB vide → sans Brier)."""
    conn = sqlite3.connect(str(temp_db))
    # 1 décision pour que Brier soit calculable
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO decisions (timestamp, symbol, timeframe, confiance, is_win, resolution_strategy) "
        "VALUES (?, 'GBPUSD', 'M15', 50, 1, 'DYNAMIC')",
        (now.isoformat(),),
    )
    conn.commit()
    conn.close()

    stats = fetch_stats(temp_db, 4)
    text = render_brief(stats, 4)
    assert "BRIEF MARCHÉ V9" in text
    assert "Session" in text
    assert "AUJOURD'HUI" in text or "pas encore actif" in text
    assert "CVD live" in text
    assert "Source" in text


def test_render_brief_with_alerts(temp_db):
    """Brief avec alertes → section ALERTES présente."""
    stats = {
        "by_symbol": {
            "GBPUSD": {"n": 10, "wr_pct": 25.0, "avg_pips": -3.0, "total_pips": -30.0},
        },
        "today": {"date": "2026-07-22", "n": 10, "wr_pct": 30.0, "pips": -20.0, "session_now": "LONDRES"},
        "yesterday": {"date": "2026-07-21", "n": 5, "wr_pct": 40.0, "pips": -10.0},
        "24h_rolling": {"n": 10, "wr_pct": 30.0, "pips": -20.0},
        "cvd_alive": ["EURUSD", "GBPUSD"],
        "cvd_total_pairs": 6,
        "brier_7j": 0.4467,
    }
    text = render_brief(stats, 4)
    assert "ALERTES MOMENTS MAJEURS" in text
    assert "DANGER" in text
    assert "CVD KO" in text
    assert "anti-calibré" in text


# ── Tests send_telegram ───────────────────────────────────────────────

def test_send_telegram_dry_run():
    """Mode dry-run → pas d'envoi réel."""
    # Pas de subprocess réel, on mock
    with patch("scripts.v9_market_brief.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        ok = send_telegram("test")
    assert ok is True
    assert mock_run.called


def test_send_telegram_failure():
    """Échec subprocess → False."""
    with patch("scripts.v9_market_brief.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        ok = send_telegram("test")
    assert ok is False


# ── Tests main CLI ────────────────────────────────────────────────────

def test_main_dry_run(temp_db, capsys):
    """CLI --dry-run → pas d'envoi."""
    with patch("scripts.v9_market_brief.DB_PATH", temp_db):
        with patch.object(sys, "argv", ["prog", "--dry-run"]):
            rc = main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "BRIEF MARCHÉ V9" in captured.out
    assert "DRY-RUN" in captured.out


def test_main_json_output(temp_db, capsys):
    """CLI --json → JSON parsable."""
    with patch("scripts.v9_market_brief.DB_PATH", temp_db):
        with patch.object(sys, "argv", ["prog", "--json"]):
            rc = main()
    assert rc == 0
    import json
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "session" in data
    assert "stats" in data
    assert "alerts" in data
