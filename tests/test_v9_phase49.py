"""tests/test_v9_phase49.py — Phase 49 motion CEO autopilote.

Tests pour telegram_alerts + alert_dispatcher.
"""
import json
import os
import pytest
import sqlite3


# === Severity / classify ===

def test_severity_enum():
    from scripts.v9_telegram_alerts import Severity
    assert Severity.CRITICAL.value == "CRITICAL"
    assert Severity.HIGH.value == "HIGH"
    assert Severity.MEDIUM.value == "MEDIUM"


def test_classify_known_event():
    from scripts.v9_telegram_alerts import classify_event, Severity
    assert classify_event("ROLLBACK_REQUIRED") == Severity.CRITICAL
    assert classify_event("WR_DROP_BELOW_60") == Severity.HIGH
    assert classify_event("LOSS_STREAK_3") == Severity.MEDIUM
    assert classify_event("DAILY_AUDIT_OK") == Severity.LOW


def test_classify_unknown_event():
    from scripts.v9_telegram_alerts import classify_event, Severity
    assert classify_event("UNKNOWN_EVENT") == Severity.INFO


def test_severity_emoji():
    from scripts.v9_telegram_alerts import SEVERITY_EMOJI
    assert SEVERITY_EMOJI["CRITICAL"] == "🔴"
    assert SEVERITY_EMOJI["HIGH"] == "🟠"
    assert SEVERITY_EMOJI["MEDIUM"] == "🟡"
    assert SEVERITY_EMOJI["LOW"] == "🟢"
    assert SEVERITY_EMOJI["INFO"] == "⚪"


# === build_alert_message ===

def test_build_alert_message_basic():
    from scripts.v9_telegram_alerts import build_alert_message
    msg = build_alert_message("WR_DROP_BELOW_60", {"wr": 0.55, "n": 20})
    assert msg["severity"] == "HIGH"
    assert "🔴" not in msg["emoji"]
    assert "🟠" == msg["emoji"]
    # .title() lowercases after first char
    assert "Wr Drop Below 60" in msg["title"]
    assert "0.55" in msg["text"]
    assert msg["n_actions"] >= 1


def test_build_alert_message_no_actions():
    from scripts.v9_telegram_alerts import build_alert_message
    msg = build_alert_message("DAILY_AUDIT_OK", {})
    assert msg["n_actions"] == 0


def test_build_alert_message_unknown():
    from scripts.v9_telegram_alerts import build_alert_message
    msg = build_alert_message("UNKNOWN_EVENT_XYZ", {})
    assert msg["severity"] == "INFO"


def test_build_alert_message_override_severity():
    from scripts.v9_telegram_alerts import build_alert_message, Severity
    msg = build_alert_message("DAILY_AUDIT_OK", {},
                                severity=Severity.CRITICAL)
    assert msg["severity"] == "CRITICAL"


def test_get_recommended_actions_rollback():
    from scripts.v9_telegram_alerts import _get_recommended_actions
    actions = _get_recommended_actions("ROLLBACK_REQUIRED", {})
    assert len(actions) >= 1


def test_get_recommended_actions_unknown():
    from scripts.v9_telegram_alerts import _get_recommended_actions
    assert _get_recommended_actions("UNKNOWN_EVENT", {}) == []


# === send_telegram_message ===

def test_send_telegram_dry_run():
    from scripts.v9_telegram_alerts import send_telegram_message
    res = send_telegram_message("test", dry_run=True)
    assert res["sent"] is False
    assert res["reason"] == "dry_run"
    assert res["text_length"] == 4


def test_send_telegram_missing_credentials():
    from scripts.v9_telegram_alerts import send_telegram_message
    # Sans env vars et sans dry_run
    old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    old_chat = os.environ.pop("TELEGRAM_CHAT_ID", None)
    try:
        res = send_telegram_message("test", dry_run=False)
        assert res["sent"] is False
        assert res["reason"] == "missing_credentials"
    finally:
        if old_token:
            os.environ["TELEGRAM_BOT_TOKEN"] = old_token
        if old_chat:
            os.environ["TELEGRAM_CHAT_ID"] = old_chat


# === emit_alert ===

def test_emit_alert_basic():
    from scripts.v9_telegram_alerts import emit_alert
    result = emit_alert("WR_DROP_BELOW_60", {"wr": 0.5})
    assert "alert" in result
    assert "send" in result
    assert result["alert"]["severity"] == "HIGH"
    assert result["send"]["sent"] is False


# === dispatcher ===

def test_get_paper_summary_db_missing():
    from scripts.v9_alert_dispatcher import _get_paper_summary
    from pathlib import Path as _P
    s = _get_paper_summary(_P("/nonexistent/path.db"))
    assert s["n_open"] == 0


def test_get_paper_summary_with_db(tmp_path):
    from scripts.v9_alert_dispatcher import _get_paper_summary
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, direction TEXT,
                opened_at TEXT, closed_at TEXT, pips_net REAL
            )
        """)
        # 5 wins + 8 losses (WR 38% < 60%)
        # Date recente : maintenant
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()[:10]
        for p in [25.0] * 5 + [-8.0] * 8:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES
                (NULL, 'haussiere', ?, ?, ?)
            """, (now, now, p))
        conn.commit()
    s = _get_paper_summary(db)
    assert s["n_wins"] == 5
    assert s["n_losses"] == 8
    assert s["n_closed"] == 13


def test_compute_wr():
    from scripts.v9_alert_dispatcher import _compute_wr
    assert _compute_wr({"n_wins": 5, "n_losses": 5}) == 0.5
    assert _compute_wr({"n_wins": 0, "n_losses": 0}) == 0.0


def test_detect_and_dispatch_dry_run(tmp_path):
    from scripts.v9_alert_dispatcher import detect_and_dispatch
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, direction TEXT,
                opened_at TEXT, closed_at TEXT, pips_net REAL
            )
        """)
        # 2 wins + 8 losses (WR 20% < 60%)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()[:10]
        for p in [25.0] * 2 + [-8.0] * 8:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES
                (NULL, 'haussiere', ?, ?, ?)
            """, (now, now, p))
        conn.commit()
    result = detect_and_dispatch(db, telegram_dry_run=True)
    assert result["n_events_dispatched"] >= 1
    # WR_DROP_BELOW_60 doit etre detecte
    event_types = [e["type"] for e in result["events"]]
    assert "WR_DROP_BELOW_60" in event_types


def test_detect_and_dispatch_no_event(tmp_path):
    from scripts.v9_alert_dispatcher import detect_and_dispatch
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, direction TEXT,
                opened_at TEXT, closed_at TEXT, pips_net REAL
            )
        """)
        # Aucun trade
        conn.commit()
    result = detect_and_dispatch(db, telegram_dry_run=True)
    assert result["n_events_dispatched"] == 0


def test_main_list_events(capsys):
    from scripts.v9_telegram_alerts import main
    exit_code = main(["--list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Evenements connus" in captured.out


def test_main_emit_event(capsys):
    from scripts.v9_telegram_alerts import main
    exit_code = main(["--event", "WR_DROP_BELOW_60",
                        "--context", '{"wr": 0.5}'])
    captured = capsys.readouterr()
    assert exit_code == 0
    # .title() lowercases
    assert "Wr Drop Below 60" in captured.out


def test_main_dispatcher(monkeypatch, capsys):
    from scripts.v9_alert_dispatcher import main
    import sqlite3
    import tempfile
    from pathlib import Path
    from datetime import datetime, timezone
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, direction TEXT,
                opened_at TEXT, closed_at TEXT, pips_net REAL
            )
        """)
        now = datetime.now(timezone.utc).isoformat()[:10]
        for p in [25.0] * 2 + [-8.0] * 8:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES
                (NULL, 'haussiere', ?, ?, ?)
            """, (now, now, p))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DISPATCHER" in captured.out