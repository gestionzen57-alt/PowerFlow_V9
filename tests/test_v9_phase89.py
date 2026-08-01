"""tests/test_v9_phase89.py — Phase 89 motion CEO 48H (post-Plan C).

Tests pour webhook_notifier.
"""
import pytest


def test_format_payload_basic():
    from scripts.v9_webhook_notifier import format_payload
    payload = format_payload("test_event", {"key": "value"})
    assert payload["event"] == "test_event"
    assert payload["data"]["key"] == "value"
    assert "timestamp" in payload


def test_format_payload_with_severity():
    from scripts.v9_webhook_notifier import format_payload
    payload = format_payload("alert", {"wr": 0.45}, severity="HIGH")
    assert payload["severity"] == "HIGH"


def test_format_payload_default_severity():
    from scripts.v9_webhook_notifier import format_payload
    payload = format_payload("test", {})
    assert payload["severity"] == "INFO"


def test_sign_payload():
    from scripts.v9_webhook_notifier import sign_payload
    sig = sign_payload({"a": "b"}, secret="secret123")
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA-256 hex


def test_sign_payload_deterministic():
    from scripts.v9_webhook_notifier import sign_payload
    p = {"a": "b"}
    s1 = sign_payload(p, secret="secret")
    s2 = sign_payload(p, secret="secret")
    assert s1 == s2


def test_sign_payload_different_secrets():
    from scripts.v9_webhook_notifier import sign_payload
    p = {"a": "b"}
    s1 = sign_payload(p, secret="secret1")
    s2 = sign_payload(p, secret="secret2")
    assert s1 != s2


def test_validate_signature():
    from scripts.v9_webhook_notifier import (
        sign_payload, validate_signature,
    )
    p = {"a": "b"}
    sig = sign_payload(p, secret="s3cr3t")
    assert validate_signature(p, sig, secret="s3cr3t") is True
    assert validate_signature(p, sig, secret="wrong") is False


def test_get_retry_count():
    from scripts.v9_webhook_notifier import (
        compute_retry_delay, MAX_RETRIES,
    )
    assert MAX_RETRIES >= 1
    assert compute_retry_delay(0) >= 0


def test_compute_retry_delay_exponential():
    from scripts.v9_webhook_notifier import compute_retry_delay
    # Exponential backoff : delay grows with attempt
    d0 = compute_retry_delay(0)
    d1 = compute_retry_delay(1)
    d2 = compute_retry_delay(2)
    assert d1 > d0
    assert d2 > d1


def test_dispatch_no_url():
    """Si pas de WEBHOOK_URL, dispatch doit retourner sent=False."""
    import os
    from scripts.v9_webhook_notifier import dispatch_webhook
    old = os.environ.get("V9_ALERT_WEBHOOK_URL")
    try:
        os.environ.pop("V9_ALERT_WEBHOOK_URL", None)
        res = dispatch_webhook("test", {"k": "v"})
        assert res["sent"] is False
    finally:
        if old:
            os.environ["V9_ALERT_WEBHOOK_URL"] = old


def test_dispatch_with_url():
    """Si URL configuree, dispatch tente (mais pas d'envoi reel)."""
    import os
    from scripts.v9_webhook_notifier import dispatch_webhook
    old = os.environ.get("V9_ALERT_WEBHOOK_URL")
    try:
        os.environ["V9_ALERT_WEBHOOK_URL"] = "https://example.com/webhook"
        res = dispatch_webhook("test", {"k": "v"})
        # Pas de requete reelle, mais le dict doit avoir les bons champs
        assert "event" in res or "sent" in res
    finally:
        if old:
            os.environ["V9_ALERT_WEBHOOK_URL"] = old
        else:
            os.environ.pop("V9_ALERT_WEBHOOK_URL", None)


def test_main_demo(capsys):
    from scripts.v9_webhook_notifier import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "WEBHOOK" in captured.out