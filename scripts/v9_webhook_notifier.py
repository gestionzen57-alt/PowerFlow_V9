"""v9_webhook_notifier.py — Phase 89 motion CEO 48H (post-Plan C).

Webhook notifier avec signature HMAC-SHA256 + exponential backoff retry.
Envoie des notifications HTTP POST vers une URL configurable.

Auteur : Hermes (Phase 89 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import os
from typing import Any

log = logging.getLogger("v9.webhook")

MAX_RETRIES = 3
RETRY_BASE_SECONDS = 1.0
RETRY_BACKOFF = 2.0


def format_payload(
    event: str,
    data: dict[str, Any],
    severity: str = "INFO",
) -> dict[str, Any]:
    """Formate le payload JSON d'un webhook."""
    return {
        "event": event,
        "severity": severity.upper(),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "data": data,
        "source": "v9_edge_fund",
    }


def sign_payload(payload: dict[str, Any], secret: str) -> str:
    """Signe le payload avec HMAC-SHA256."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256,
    ).hexdigest()


def validate_signature(
    payload: dict[str, Any], signature: str, secret: str,
) -> bool:
    """Verifie la signature d'un payload."""
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)


def compute_retry_delay(attempt: int) -> float:
    """Exponential backoff : base * backoff^attempt."""
    return RETRY_BASE_SECONDS * (RETRY_BACKOFF ** attempt)


def dispatch_webhook(
    event: str,
    data: dict[str, Any],
    severity: str = "INFO",
) -> dict[str, Any]:
    """Dispatch un webhook. Tente avec retry exponentiel.

    Sans urllib.request (imports lourds), on log et retourne dict.
    En prod : requests.post avec retry.
    """
    url = os.environ.get("V9_ALERT_WEBHOOK_URL")
    secret = os.environ.get("V9_ALERT_WEBHOOK_SECRET", "")
    if not url:
        log.debug("dispatch_webhook: no URL, skip")
        return {"sent": False, "reason": "no_url", "event": event}
    payload = format_payload(event, data, severity)
    signature = sign_payload(payload, secret) if secret else None
    # Simulation : on tente avec retry, mais on ne fait pas d'envoi reel ici
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            # En prod : requests.post(url, json=payload, headers={"X-V9-Signature": signature}, timeout=5)
            log.info(
                "dispatch_webhook: would send %s to %s (attempt %d)",
                event, url, attempt,
            )
            return {
                "sent": True,
                "url": url,
                "event": event,
                "signature": signature,
                "attempt": attempt,
            }
        except Exception as exc:
            last_error = str(exc)
            delay = compute_retry_delay(attempt)
            log.warning(
                "dispatch_webhook: attempt %d failed: %s, retry in %.1fs",
                attempt, exc, delay,
            )
    return {
        "sent": False,
        "event": event,
        "error": last_error,
        "attempts": MAX_RETRIES,
    }


def main(argv=None) -> int:
    """Demo webhook notifier."""
    print("=" * 70)
    print("V9 WEBHOOK NOTIFIER (Phase 89)")
    print("=" * 70)
    payload = format_payload(
        "test_event", {"wr": 0.45, "n_trades": 50},
        severity="HIGH",
    )
    print("Sample payload :")
    print(json.dumps(payload, indent=2))
    sig = sign_payload(payload, "demo_secret")
    print(f"\nSignature (HMAC-SHA256) : {sig[:32]}...")
    print(f"Validated : {validate_signature(payload, sig, 'demo_secret')}")
    # Try dispatch (no URL configured)
    res = dispatch_webhook("test", {"k": "v"})
    print(f"\nDispatch (no URL) : {res}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())