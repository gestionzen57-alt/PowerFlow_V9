"""v9_telegram_alerts.py — Phase 49 motion CEO autopilote.

Telegram alert engine v2 : emission d'alertes precises et pertinentes
avec severite + contexte + actions recommandees.

Auteur : Hermes (Phase 49 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.telegram")


# === SEVERITY ===

class Severity(Enum):
    CRITICAL = "CRITICAL"   # Action immediate requise
    HIGH = "HIGH"           # Action dans l'heure
    MEDIUM = "MEDIUM"       # A surveiller
    LOW = "LOW"             # Informationnel
    INFO = "INFO"           # Debug / trace


SEVERITY_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
    "INFO": "⚪",
}


# === EVENT CLASSIFIER ===

# Importance des evenements V9
EVENT_IMPORTANCE = {
    # CRITICAL
    "ROLLBACK_REQUIRED": Severity.CRITICAL,
    "LIVE_DISABLED": Severity.CRITICAL,
    "DAILY_DD_BREACH": Severity.CRITICAL,
    "BROKER_DISCONNECT": Severity.CRITICAL,
    # HIGH
    "WR_DROP_BELOW_60": Severity.HIGH,
    "EXPECTANCY_NEGATIVE": Severity.HIGH,
    "DRAWDOWN_OVER_50P": Severity.HIGH,
    "KILL_SWITCH_TRIPPED": Severity.HIGH,
    "MIRROR_DATA_STALE": Severity.HIGH,
    "TOKEN_EXPIRED": Severity.HIGH,
    # MEDIUM
    "WR_DROP_BELOW_70": Severity.MEDIUM,
    "WIN_STREAK_5": Severity.MEDIUM,
    "LOSS_STREAK_3": Severity.MEDIUM,
    "REGIME_CHANGE": Severity.MEDIUM,
    "VOL_SPIKE": Severity.MEDIUM,
    "SENTIMENT_FLIP": Severity.MEDIUM,
    # LOW
    "DAILY_AUDIT_OK": Severity.LOW,
    "NEW_TRADE_OPENED": Severity.LOW,
    "POST_MORTEM_DONE": Severity.LOW,
    # INFO
    "HEARTBEAT_OK": Severity.INFO,
    "TEST_PASSED": Severity.INFO,
}


def classify_event(event_type: str) -> Severity:
    """Classifie un evenement selon importance."""
    return EVENT_IMPORTANCE.get(event_type, Severity.INFO)


# === ALERT MESSAGE BUILDER ===

def build_alert_message(event_type: str, context: dict,
                          severity: Optional[Severity] = None) -> dict:
    """Construit un message Telegram structure.

    Format : emoji + title + context lines + recommended actions
    """
    if severity is None:
        severity = classify_event(event_type)
    emoji = SEVERITY_EMOJI[severity.value]
    title = event_type.replace("_", " ").title()
    lines = []
    lines.append(f"{emoji} <b>[{severity.value}] {title}</b>")
    lines.append("")
    # Context lines
    if context:
        lines.append("<b>Context:</b>")
        for k, v in context.items():
            if isinstance(v, float):
                v = round(v, 3)
            lines.append(f"  - {k}: <code>{v}</code>")
        lines.append("")
    # Recommended actions based on event type
    actions = _get_recommended_actions(event_type, context)
    if actions:
        lines.append("<b>Recommended actions:</b>")
        for action in actions:
            lines.append(f"  - {action}")
        lines.append("")
    lines.append(f"<i>{datetime.now(timezone.utc).isoformat()[:19]} UTC</i>")
    return {
        "severity": severity.value,
        "emoji": emoji,
        "title": title,
        "text": "\n".join(lines),
        "event_type": event_type,
        "n_actions": len(actions),
    }


def _get_recommended_actions(event_type: str, context: dict) -> list[str]:
    """Retourne les actions recommandees selon event_type."""
    actions_map = {
        "ROLLBACK_REQUIRED": [
            "Verifier v9_auto_rollback --check",
            "Confirmer V9_MT4_BRIDGE_ENABLED=0 dans .env",
            "Inspecter data/v9_forces.db pour drift",
        ],
        "WR_DROP_BELOW_60": [
            "Verifier L1-L15 actifs dans config",
            "Auditer paper trades recents",
            "Considerer reduction sizing Kelly",
        ],
        "DRAWDOWN_OVER_50P": [
            "STOP nouvelles positions",
            "Verifier hedge / risk parity",
            "Re-evaluer L7 (blacklist paires)",
        ],
        "KILL_SWITCH_TRIPPED": [
            "Identifier quel kill switch",
            "Verifier conditions declenchement",
            "Re-activer manuellement apres audit",
        ],
        "TOKEN_EXPIRED": [
            "Lancer @BotFather /revoke",
            "Update config/v9_tokens.env",
            "Run python scripts/v9_token_rotation.py --history",
        ],
        "LOSS_STREAK_3": [
            "Reduire sizing 50%",
            "Verifier conditions marche (sentiment, regime)",
            "Considerer pause 1h",
        ],
        "REGIME_CHANGE": [
            "Re-evaluer position_size_factor",
            "Verifier L8 (regime NEUTRE)",
            "Ajuster expectations",
        ],
        "DAILY_AUDIT_OK": [],
    }
    return actions_map.get(event_type, [])


# === SENDER ===

def send_telegram_message(text: str, bot_token: str = None,
                            chat_id: str = None,
                            dry_run: bool = True) -> dict:
    """Envoie un message Telegram (HTTP API).

    Si dry_run=True, log uniquement sans envoyer.
    """
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if dry_run or not bot_token or not chat_id:
        log.info("DRY_RUN telegram message: %s", text[:80])
        return {
            "sent": False,
            "reason": "dry_run" if dry_run else "missing_credentials",
            "text_length": len(text),
        }
    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {
                "sent": True,
                "status_code": resp.status,
                "text_length": len(text),
            }
    except Exception as e:
        return {
            "sent": False,
            "reason": str(e),
            "text_length": len(text),
        }


# === MAIN ===

def emit_alert(event_type: str, context: dict = None,
                 dry_run: bool = True) -> dict:
    """Point d'entree principal : emet une alerte Telegram."""
    msg = build_alert_message(event_type, context or {})
    result = send_telegram_message(msg["text"], dry_run=dry_run)
    return {
        "alert": msg,
        "send": result,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 Telegram alerts (Phase 49)",
    )
    parser.add_argument("--event", default="DAILY_AUDIT_OK",
                        help="Type d'evenement")
    parser.add_argument("--context", default="{}",
                        help="Context JSON")
    parser.add_argument("--live", action="store_true",
                        help="Live send (sinon dry_run)")
    parser.add_argument("--list", action="store_true",
                        help="Liste tous les events")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("PHASE 49 — TELEGRAM ALERTS V2")
    print("=" * 70)
    if args.list:
        print("Evenements connus :")
        for evt, sev in EVENT_IMPORTANCE.items():
            print(f"  {sev.value:9s} {SEVERITY_EMOJI[sev.value]} {evt}")
        return 0
    try:
        context = json.loads(args.context)
    except json.JSONDecodeError as e:
        print(f"Erreur JSON : {e}")
        return 1
    result = emit_alert(args.event, context, dry_run=not args.live)
    print(f"Severity   : {result['alert']['severity']}")
    print(f"Emoji      : {result['alert']['emoji']}")
    print(f"Title      : {result['alert']['title']}")
    print(f"Sent       : {result['send']['sent']}")
    print(f"Reason     : {result['send'].get('reason', 'ok')}")
    print(f"Length     : {result['send']['text_length']}")
    print()
    print("Message preview :")
    print(result["alert"]["text"])
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())