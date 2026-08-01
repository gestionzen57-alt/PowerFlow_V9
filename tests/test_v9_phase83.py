"""tests/test_v9_phase83.py — Phase 83 motion CEO 48H (post-Plan C).

Tests pour alert_channel.
"""
import pytest


def test_default_channels():
    from scripts.v9_alert_channel import SUPPORTED_CHANNELS
    assert "telegram" in SUPPORTED_CHANNELS
    assert "slack" in SUPPORTED_CHANNELS
    assert "discord" in SUPPORTED_CHANNELS
    assert "webhook" in SUPPORTED_CHANNELS


def test_severity_emoji_telegram():
    from scripts.v9_alert_channel import severity_emoji
    assert severity_emoji("telegram", "CRITICAL") == "🔴"
    assert severity_emoji("telegram", "INFO") == "⚪"


def test_severity_emoji_slack():
    from scripts.v9_alert_channel import severity_emoji
    assert severity_emoji("slack", "CRITICAL") == ":red_circle:"
    assert severity_emoji("slack", "HIGH") == ":large_orange_diamond:"


def test_severity_emoji_discord():
    from scripts.v9_alert_channel import severity_emoji
    assert severity_emoji("discord", "CRITICAL") == "🛑"
    assert severity_emoji("discord", "LOW") == "✅"


def test_format_message_telegram():
    from scripts.v9_alert_channel import format_message
    msg = format_message("telegram", "WR Drop", "WR < 60%", "HIGH",
                         {"wr": 0.45})
    assert "WR Drop" in msg
    assert "WR < 60%" in msg
    assert "HIGH" in msg
    assert "0.45" in msg


def test_format_message_slack_blocks():
    from scripts.v9_alert_channel import format_message
    msg = format_message("slack", "Test", "Body", "LOW", {"k": "v"})
    # Slack format : blocks
    assert "blocks" in msg or "text" in msg


def test_format_message_unknown_channel():
    from scripts.v9_alert_channel import format_message
    # Fallback to plain text
    msg = format_message("unknown", "T", "B", "INFO")
    assert "T" in msg
    assert "B" in msg


def test_dispatch_alert_returns_ok():
    """dispatch_alert doit retourner False si channel inconnu."""
    from scripts.v9_alert_channel import dispatch_alert
    res = dispatch_alert("unknown", "T", "B")
    # Ne doit pas lever, retourne False ou dict avec sent=False
    assert res is False or res.get("sent") is False


def test_dispatch_telegram_no_token():
    """Si pas de token Telegram, dispatch doit retourner sent=False."""
    from scripts.v9_alert_channel import dispatch_alert
    import os
    old = os.environ.get("V9_TELEGRAM_BOT_TOKEN")
    try:
        os.environ.pop("V9_TELEGRAM_BOT_TOKEN", None)
        res = dispatch_alert("telegram", "T", "B")
        # Soit False, soit sent=False
        assert res is False or res.get("sent") is False
    finally:
        if old:
            os.environ["V9_TELEGRAM_BOT_TOKEN"] = old


def test_format_message_with_recommendation():
    from scripts.v9_alert_channel import format_message
    msg = format_message(
        "telegram", "Audit Alert", "BUG-01 detecte",
        "CRITICAL", {}, recommendation="Run auto_rollback.py",
    )
    assert "Run auto_rollback" in msg or "action" in msg.lower()


def test_format_message_no_context():
    from scripts.v9_alert_channel import format_message
    msg = format_message("telegram", "Title", "Body", "INFO")
    assert "Title" in msg
    assert "Body" in msg


def test_main_demo(capsys):
    from scripts.v9_alert_channel import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ALERT CHANNEL" in captured.out