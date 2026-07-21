"""tests/test_v9_telegram_signal_alert.py — Tests du script d'alertes Telegram signaux.

Doctrine : R7 (tests verts avant commit), R8 (traçabilité), R22 (script CLI
non-promotionnel, lecture seule).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.v9_telegram_signal_alert import (  # noqa: E402
    KILL_SWITCH_NAME,
    _is_kill_switch_on,
    fetch_recent_signals,
    format_signal_message,
    load_telegram_config,
    send_telegram,
)


@pytest.fixture
def temp_db():
    """Crée une DB temporaire avec table decisions."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY,
            timestamp TEXT,
            symbol TEXT,
            timeframe TEXT,
            direction TEXT,
            confiance INTEGER,
            regime_type TEXT,
            principes_json TEXT,
            scene_id TEXT,
            action TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    yield Path(db_path)
    # Force GC pour libérer le fichier sur Windows
    import gc
    gc.collect()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_telegram_config():
    """Crée un config telegram temporaire valide."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"BOT_TOKEN": "TEST_TOKEN", "CHAT_ID": "12345"}, f)
        cfg_path = f.name
    yield Path(cfg_path)
    Path(cfg_path).unlink(missing_ok=True)


def test_kill_switch_name():
    """Le kill switch est bien nommé."""
    assert KILL_SWITCH_NAME == "V9_TELEGRAM_SIGNAL_ALERT_ENABLED"


def test_kill_switch_off_by_default(monkeypatch):
    """Kill switch OFF par défaut → False."""
    monkeypatch.delenv(KILL_SWITCH_NAME, raising=False)
    monkeypatch.setattr("core.v9.kill_switches.is_enabled", lambda n: False)
    assert _is_kill_switch_on() is False


def test_kill_switch_on_via_kill_switches(monkeypatch):
    """Kill switch ON via core.v9.kill_switches → True."""
    monkeypatch.setattr("core.v9.kill_switches.is_enabled", lambda n: True)
    assert _is_kill_switch_on() is True


def test_kill_switch_on_via_env_fallback(monkeypatch):
    """Kill switch ON via os.environ (fallback) → True."""
    def raise_(*_):
        raise ImportError("no core")
    monkeypatch.setattr("core.v9.kill_switches.is_enabled", raise_)
    monkeypatch.setenv(KILL_SWITCH_NAME, "1")
    assert _is_kill_switch_on() is True


def test_load_telegram_config_ok(temp_telegram_config, monkeypatch):
    """Lecture config telegram valide."""
    monkeypatch.setattr(
        "scripts.v9_telegram_signal_alert.TELEGRAM_CONFIG", temp_telegram_config
    )
    token, chat_id = load_telegram_config()
    assert token == "TEST_TOKEN"
    assert chat_id == "12345"


def test_load_telegram_config_missing(tmp_path, monkeypatch):
    """Config absente → FileNotFoundError."""
    monkeypatch.setattr(
        "scripts.v9_telegram_signal_alert.TELEGRAM_CONFIG", tmp_path / "absent.json"
    )
    with pytest.raises(FileNotFoundError):
        load_telegram_config()


def test_load_telegram_config_incomplete(tmp_path, monkeypatch):
    """Config incomplète → ValueError."""
    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps({"BOT_TOKEN": "X"}))
    monkeypatch.setattr("scripts.v9_telegram_signal_alert.TELEGRAM_CONFIG", cfg)
    with pytest.raises(ValueError):
        load_telegram_config()


def test_fetch_recent_signals_db_missing(tmp_path):
    """DB absente → FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        fetch_recent_signals(tmp_path / "absent.db", 5, 80, 3)


def test_fetch_recent_signals_filters(temp_db):
    """Filtre action=preparer_entree + confiance >= seuil + fenêtre temporelle."""
    conn = sqlite3.connect(str(temp_db))
    # 2 signaux exploitables
    conn.execute(
        "INSERT INTO decisions VALUES (1, '2026-07-21T08:00:00', 'EURUSD', 'M15', 'haussiere', 85, 'trending', '[\"PRICE_LAG\"]', 'sc1', 'preparer_entree')"
    )
    conn.execute(
        "INSERT INTO decisions VALUES (2, '2026-07-21T08:00:00', 'GBPUSD', 'M15', 'haussiere', 90, 'ranging', '[\"GRAVITY\"]', 'sc2', 'preparer_entree')"
    )
    # 1 signal sous seuil
    conn.execute(
        "INSERT INTO decisions VALUES (3, '2026-07-21T08:00:00', 'USDJPY', 'M15', 'baissiere', 70, 'volatile', '[\"X\"]', 'sc3', 'preparer_entree')"
    )
    # 1 signal autre action
    conn.execute(
        "INSERT INTO decisions VALUES (4, '2026-07-21T08:00:00', 'AUDUSD', 'M15', 'haussiere', 95, 'trending', '[\"Y\"]', 'sc4', 'aucune_action')"
    )
    conn.commit()
    conn.close()

    sigs = fetch_recent_signals(temp_db, 60, 80, 10)
    assert len(sigs) == 2
    assert sigs[0]["confiance"] == 90  # tri DESC
    assert sigs[1]["confiance"] == 85


def test_format_signal_message_buy():
    """Format alerte direction haussière."""
    sig = {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "direction": "haussiere",
        "confiance": 85,
        "timestamp": "2026-07-21T08:00:00",
        "regime_type": "trending",
        "principes_json": json.dumps(["PRICE_LAG", "GRAVITY"]),
        "scene_id": "sc-123",
    }
    msg = format_signal_message(sig)
    assert "EURUSD" in msg
    assert "HAUSSIERE" in msg
    assert "85%" in msg
    assert "PRICE_LAG" in msg
    assert "🔺" in msg


def test_format_signal_message_sell():
    """Format alerte direction baissière."""
    sig = {
        "symbol": "GBPUSD",
        "timeframe": "M5",
        "direction": "baissiere",
        "confiance": 90,
        "timestamp": "2026-07-21T08:00:00",
        "regime_type": "volatile",
        "principes_json": "[]",
        "scene_id": "sc-456",
    }
    msg = format_signal_message(sig)
    assert "GBPUSD" in msg
    assert "BAISSIERE" in msg
    assert "🔻" in msg


def test_format_signal_message_truncates_principles():
    """Liste de principes > 8 → truncation."""
    sig = {
        "symbol": "EURUSD",
        "timeframe": "M15",
        "direction": "haussiere",
        "confiance": 85,
        "timestamp": "2026-07-21T08:00:00",
        "regime_type": "trending",
        "principes_json": json.dumps([f"P{i}" for i in range(15)]),
        "scene_id": "sc-1",
    }
    msg = format_signal_message(sig)
    assert "+7" in msg  # 15 - 8 = 7


def test_send_telegram_network_error():
    """Envoi Telegram en erreur réseau → dict ok=False."""
    import urllib.error

    def raise_urlerror(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="http://x", code=400, msg="bad", hdrs={}, fp=None
        )

    with patch("urllib.request.urlopen", side_effect=raise_urlerror):
        res = send_telegram("T", "C", "msg")
    assert res["ok"] is False
    assert "HTTP 400" in res["error"]


def test_send_telegram_success():
    """Envoi Telegram OK → dict ok=True avec message_id."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"ok": true, "result": {"message_id": 42}}'
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = send_telegram("T", "C", "msg")
    assert res["ok"] is True
    assert res["result"]["message_id"] == 42
