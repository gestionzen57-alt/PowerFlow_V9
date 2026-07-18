"""Tests - interactivite bot Telegram V9 (2026-07-18).

Couvre scripts/v9_telegram_notifier.py :
  - send_telegram inclut reply_markup dans le payload (clavier inline).
  - _fetch_commands parse un callback_query en message texte (/command).
  - _dispatch_command retourne (texte, markup|None) avec clavier sur /status.
  - _build_kill_response / _build_dd_response / _build_context_response
    retournent du texte non-vide (lecture DB reelle, read-only).
  - _run_script_capture tolerre un stdout en encodage Windows (cp1252).

Securite : aucun envoi reseau reel - urlopen est monkeypatche.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.v9_telegram_notifier as t  # noqa: E402


class _FakeResp:
    """Reponse urllib factice supportant le context manager."""

    def __init__(self, body: bytes = b'{"ok":true}'):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _patch_urlopen(monkeypatch: pytest.MonkeyPatch, capture: dict | None = None):
    """Monkeypatch urlopen pour ne jamais toucher au reseau."""

    def _fake(req, timeout=0, context=None):
        if capture is not None:
            try:
                capture["payload"] = json.loads(req.data.decode())
                capture["url"] = req.full_url
            except Exception:
                pass
        return _FakeResp()

    monkeypatch.setattr(t.urllib.request, "urlopen", _fake)


def test_send_telegram_includes_reply_markup(monkeypatch: pytest.MonkeyPatch):
    cap: dict = {}
    _patch_urlopen(monkeypatch, cap)
    ok = t.send_telegram(
        "hello", {"token": "X", "chat_id": "1"}, reply_markup=t._main_keyboard(),
    )
    assert ok is True
    assert "reply_markup" in cap["payload"]
    kb = cap["payload"]["reply_markup"]
    assert "inline_keyboard" in kb
    assert kb["inline_keyboard"][0][0]["callback_data"] == "/status"


def test_send_telegram_without_markup_has_no_reply_markup(monkeypatch: pytest.MonkeyPatch):
    cap: dict = {}
    _patch_urlopen(monkeypatch, cap)
    t.send_telegram("hello", {"token": "X", "chat_id": "1"})
    assert "reply_markup" not in cap["payload"]


def test_fetch_commands_parses_callback_query(monkeypatch: pytest.MonkeyPatch):
    updates = {"ok": True, "result": [
        {"update_id": 7, "callback_query": {
            "id": "cb1", "data": "/status",
            "message": {"chat": {"id": 1}},
        }},
    ]}
    monkeypatch.setattr(t.urllib.request, "urlopen",
                        lambda req, timeout=0, context=None: _FakeResp(
                            json.dumps(updates).encode()))
    msgs = t._fetch_commands({"token": "X", "chat_id": "1"})
    assert len(msgs) == 1
    assert msgs[0]["text"] == "/status"
    assert msgs[0]["chat_id"] == "1"


def test_fetch_commands_ignores_unrelated_update_types(monkeypatch: pytest.MonkeyPatch):
    updates = {"ok": True, "result": [
        {"update_id": 3, "edited_message": {"text": "x", "chat": {"id": 1}}},
    ]}
    monkeypatch.setattr(t.urllib.request, "urlopen",
                        lambda req, timeout=0, context=None: _FakeResp(
                            json.dumps(updates).encode()))
    msgs = t._fetch_commands({"token": "X", "chat_id": "1"})
    assert msgs == []


def test_dispatch_command_returns_tuple_with_markup(monkeypatch: pytest.MonkeyPatch):
    import sqlite3
    from core.v9.config import DB_PATH

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        text, markup = t._dispatch_command("/status", {"token": "X", "chat_id": "1"}, cur, None)
        assert isinstance(text, str) and text
        assert markup is not None
        assert "inline_keyboard" in markup
    finally:
        conn.close()


def test_dispatch_command_no_markup_for_action(monkeypatch: pytest.MonkeyPatch):
    import sqlite3
    from core.v9.config import DB_PATH

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        text, markup = t._dispatch_command("/pause", {"token": "X", "chat_id": "1"}, cur, None)
        assert text
        assert markup is None
    finally:
        conn.close()


def test_new_commands_return_non_empty(monkeypatch: pytest.MonkeyPatch):
    import sqlite3
    from core.v9.config import DB_PATH

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        assert t._build_kill_response()
        assert t._build_dd_response(cur)
        assert t._build_context_response()
    finally:
        conn.close()


def test_run_script_capture_tolerates_cp1252_stdout(monkeypatch: pytest.MonkeyPatch):
    import subprocess as _sp

    class _FakeResult:
        stdout = "test euro sign alpha".encode("cp1252")
        returncode = 0

    monkeypatch.setattr(_sp, "run", lambda *a, **kw: _FakeResult())
    out = t._run_script_capture("dummy --stats", max_lines=5)
    assert "test" in out
    assert "alpha" in out


def test_system_state_prompt_is_dynamic():
    prompt = t._format_system_state_prompt()
    assert "EXECUTION=0 (gele)" not in prompt
    assert "HEAD b2a6842" not in prompt
    assert "REEL DU SYSTEME" in prompt


def test_new_commands_top_learn_scene_non_empty(monkeypatch: pytest.MonkeyPatch):
    import sqlite3
    from core.v9.config import DB_PATH

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        assert t._build_top_response(cur)
        assert t._build_learn_response(cur)
        assert t._build_scene_response(cur)
    finally:
        conn.close()


def test_route_data_intent_maps_keywords():
    assert t._route_data_intent("quel est le drawdown actuel ?") == "/dd"
    assert t._route_data_intent("montre moi le top des principes") == "/top"
    assert t._route_data_intent("etat des kill switches") == "/kill"
    assert t._route_data_intent("derniere scene de marche") == "/scene"
    assert t._route_data_intent("raconte une blague") is None


def test_dispatch_includes_new_commands_in_keyboard(monkeypatch: pytest.MonkeyPatch):
    import sqlite3
    from core.v9.config import DB_PATH

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        for cmd in ("/top", "/learn", "/scene"):
            text, markup = t._dispatch_command(cmd, {"token": "X", "chat_id": "1"}, cur, None)
            assert text
            assert markup is not None
    finally:
        conn.close()
