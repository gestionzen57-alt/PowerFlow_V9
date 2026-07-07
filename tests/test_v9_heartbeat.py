"""Tests — scripts/v9_heartbeat.py (watchdog + heartbeat Telegram V9).

Couvre :
- check_server_alive (port libre vs occupé via socket réel, monkeypatché)
- check_db_fresh (DB vide, snapshot frais, snapshot stale)
- run_full_check (agrégation)
- load_state / save_state (persistance JSON, corruption tolérée)
- compteur d'échecs consécutifs (3 = alerte)
- maybe_send_alive / maybe_send_alert (anti-doublon 1/h, env .env)
- CLI --check / --heartbeat / --reset (exit codes)

Aucun test ne touche `data/v9_forces.db` ni `logs/` réels (tmp_path/monkeypatch).
"""

from __future__ import annotations

import json
import socket
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import v9_heartbeat  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────
@pytest.fixture
def tmp_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige .heartbeat_state.json vers tmp_path."""
    p = tmp_path / ".heartbeat_state.json"
    monkeypatch.setattr(v9_heartbeat, "HEARTBEAT_STATE_PATH", p)
    return p


@pytest.fixture
def fake_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Crée une DB SQLite avec table snapshots, sans toucher data/v9_forces.db."""
    db_path = tmp_path / "fake_v9.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE snapshots (bar_time INTEGER)")
    monkeypatch.setattr(v9_heartbeat, "DB_PATH", db_path)
    return db_path


def _insert_snapshot(db_path: Path, age_minutes: float) -> None:
    epoch = int(datetime.now(timezone.utc).timestamp() - age_minutes * 60)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO snapshots VALUES (?)", (epoch,))
        conn.commit()


# ── check_server_alive ──────────────────────────────────────
def test_check_server_alive_port_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_heartbeat, "is_port_available", lambda *a, **k: True)
    ok, msg = v9_heartbeat.check_server_alive()
    assert ok is False
    assert "libre" in msg


def test_check_server_alive_port_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_heartbeat, "is_port_available", lambda *a, **k: False)
    ok, msg = v9_heartbeat.check_server_alive()
    assert ok is True
    assert "occupé" in msg or "actif" in msg


# ── check_db_fresh ──────────────────────────────────────────
def test_check_db_fresh_no_snapshot(fake_db: Path) -> None:
    ok, msg = v9_heartbeat.check_db_fresh()
    assert ok is False
    assert "Aucun snapshot" in msg


def test_check_db_fresh_recent_snapshot(fake_db: Path) -> None:
    _insert_snapshot(fake_db, age_minutes=2.0)
    ok, msg = v9_heartbeat.check_db_fresh()
    assert ok is True
    assert "2.0" in msg or "1." in msg or "3." in msg  # tolérance arrondi


def test_check_db_fresh_stale_snapshot(fake_db: Path) -> None:
    _insert_snapshot(fake_db, age_minutes=120.0)
    ok, msg = v9_heartbeat.check_db_fresh()
    assert ok is False
    assert "seuil" in msg


def test_check_db_fresh_db_inaccessible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Chemin inexistant + check_db() False simule DB corrompue.
    monkeypatch.setattr(v9_heartbeat, "DB_PATH", tmp_path / "ghost.db")
    monkeypatch.setattr(v9_heartbeat, "check_db", lambda: False)
    ok, msg = v9_heartbeat.check_db_fresh()
    assert ok is False
    assert "DB" in msg or "schéma" in msg


# ── run_full_check ──────────────────────────────────────────
def test_run_full_check_both_ok(monkeypatch: pytest.MonkeyPatch, fake_db: Path) -> None:
    _insert_snapshot(fake_db, age_minutes=1.0)
    monkeypatch.setattr(v9_heartbeat, "is_port_available", lambda *a, **k: False)
    ok, msgs = v9_heartbeat.run_full_check()
    assert ok is True
    assert any("Serveur" in m for m in msgs)
    assert any("DB" in m for m in msgs)


def test_run_full_check_server_down(monkeypatch: pytest.MonkeyPatch, fake_db: Path) -> None:
    _insert_snapshot(fake_db, age_minutes=1.0)
    monkeypatch.setattr(v9_heartbeat, "is_port_available", lambda *a, **k: True)
    ok, _ = v9_heartbeat.run_full_check()
    assert ok is False


# ── load_state / save_state ─────────────────────────────────
def test_load_state_missing_returns_default(tmp_state_path: Path) -> None:
    state = v9_heartbeat.load_state()
    assert state["consecutive_failures"] == 0
    assert state["last_alive_utc"] is None


def test_save_and_load_state_roundtrip(tmp_state_path: Path) -> None:
    state = {"consecutive_failures": 2, "last_alive_utc": "2026-07-07T10:00:00+00:00",
             "last_check_utc": None, "last_alert_utc": None}
    v9_heartbeat.save_state(state)
    loaded = v9_heartbeat.load_state()
    assert loaded["consecutive_failures"] == 2
    assert loaded["last_alive_utc"] == "2026-07-07T10:00:00+00:00"


def test_load_state_corrupted_resets(tmp_state_path: Path) -> None:
    tmp_state_path.write_text("{not valid json", encoding="utf-8")
    state = v9_heartbeat.load_state()
    assert state["consecutive_failures"] == 0


# ── Compteur échecs + alertes ───────────────────────────────
def test_three_failures_trigger_alert(tmp_state_path: Path, monkeypatch: pytest.MonkeyPatch, fake_db: Path) -> None:
    """3 checks KO consécutifs → alerte Telegram (1 fois, anti-doublon 1/h)."""
    monkeypatch.setattr(v9_heartbeat, "is_port_available", lambda *a, **k: True)
    cfg = {"token": "fake", "chat_id": "123"}
    sent = []
    monkeypatch.setattr(v9_heartbeat, "send_telegram",
                        lambda text, c: sent.append(text) or True)
    # 3 itérations manuelles (simule 3 cron jobs ratés)
    state = v9_heartbeat.load_state()
    for _ in range(3):
        ok, msgs = v9_heartbeat.run_full_check()
        state["last_check_utc"] = datetime.now(timezone.utc).isoformat()
        if ok:
            state["consecutive_failures"] = 0
        else:
            state["consecutive_failures"] += 1
            if state["consecutive_failures"] >= v9_heartbeat.MAX_CONSECUTIVE_FAILURES:
                v9_heartbeat.maybe_send_alert(state, "; ".join(msgs), cfg)
    v9_heartbeat.save_state(state)
    assert state["consecutive_failures"] == 3
    assert len(sent) == 1
    assert "PIPELINE DOWN" in sent[0]


def test_alert_anti_doublon_1h(tmp_state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """2e alerte < 1h après la 1re ne doit pas être envoyée."""
    cfg = {"token": "fake", "chat_id": "123"}
    sent = []
    monkeypatch.setattr(v9_heartbeat, "send_telegram",
                        lambda text, c: sent.append(text) or True)
    state = v9_heartbeat.load_state()
    state["consecutive_failures"] = 3
    state["last_alert_utc"] = datetime.now(timezone.utc).isoformat()
    v9_heartbeat.maybe_send_alert(state, "test", cfg)
    assert sent == []  # anti-doublon


# ── maybe_send_alive ────────────────────────────────────────
def test_send_alive_first_call(tmp_state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = {"token": "fake", "chat_id": "123"}
    sent = []
    monkeypatch.setattr(v9_heartbeat, "send_telegram",
                        lambda text, c: sent.append(text) or True)
    state = v9_heartbeat.load_state()
    v9_heartbeat.maybe_send_alive(state, cfg)
    assert len(sent) == 1
    assert "alive" in sent[0].lower()
    assert state["last_alive_utc"] is not None


def test_send_alive_throttled(tmp_state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si last_alive < HEARTBEAT_INTERVAL_MIN → pas de renvoi."""
    cfg = {"token": "fake", "chat_id": "123"}
    sent = []
    monkeypatch.setattr(v9_heartbeat, "send_telegram",
                        lambda text, c: sent.append(text) or True)
    state = v9_heartbeat.load_state()
    state["last_alive_utc"] = datetime.now(timezone.utc).isoformat()
    v9_heartbeat.maybe_send_alive(state, cfg)
    assert sent == []


# ── load_telegram_config ────────────────────────────────────
def test_load_telegram_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_heartbeat, "ROOT_DIR", Path("/tmp/nonexistent"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    cfg = v9_heartbeat.load_telegram_config()
    assert cfg == {"token": "tok123", "chat_id": "999"}


def test_load_telegram_config_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_heartbeat, "ROOT_DIR", Path("/tmp/nonexistent"))
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert v9_heartbeat.load_telegram_config() is None


# ── CLI ─────────────────────────────────────────────────────
def test_cli_check_exit_ok(monkeypatch: pytest.MonkeyPatch, tmp_state_path: Path, fake_db: Path) -> None:
    _insert_snapshot(fake_db, age_minutes=1.0)
    monkeypatch.setattr(v9_heartbeat, "is_port_available", lambda *a, **k: False)
    monkeypatch.setattr(v9_heartbeat, "load_telegram_config", lambda: None)
    monkeypatch.setattr("sys.argv", ["v9_heartbeat.py", "--check"])
    rc = v9_heartbeat.main()
    assert rc == 0


def test_cli_check_exit_ko(monkeypatch: pytest.MonkeyPatch, tmp_state_path: Path, fake_db: Path) -> None:
    monkeypatch.setattr(v9_heartbeat, "is_port_available", lambda *a, **k: True)
    monkeypatch.setattr(v9_heartbeat, "load_telegram_config", lambda: None)
    monkeypatch.setattr("sys.argv", ["v9_heartbeat.py", "--check"])
    rc = v9_heartbeat.main()
    assert rc == 1


def test_cli_reset_clears_counter(monkeypatch: pytest.MonkeyPatch, tmp_state_path: Path) -> None:
    v9_heartbeat.save_state({"consecutive_failures": 5, "last_alert_utc": "x"})
    monkeypatch.setattr("sys.argv", ["v9_heartbeat.py", "--reset"])
    rc = v9_heartbeat.main()
    assert rc == 0
    state = v9_heartbeat.load_state()
    assert state["consecutive_failures"] == 0
    assert state["last_alert_utc"] is None