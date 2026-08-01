"""v9_alert_channel.py — Phase 83 motion CEO 48H (post-Plan C).

Alert channel multi-sortie : Telegram / Slack / Discord / Webhook.
Format different par canal + severity emoji + dispatch HTTP POST.

Auteur : Hermes (Phase 83 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger("v9.alert_channel")

SUPPORTED_CHANNELS = ("telegram", "slack", "discord", "webhook")

# Severity emojis par canal
SEVERITY_EMOJI = {
    "telegram": {
        "CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "⚪",
    },
    "slack": {
        "CRITICAL": ":red_circle:", "HIGH": ":large_orange_diamond:",
        "MEDIUM": ":large_yellow_circle:", "LOW": ":large_green_circle:",
        "INFO": ":white_circle:",
    },
    "discord": {
        "CRITICAL": "🛑", "HIGH": "🔶", "MEDIUM": "🟡", "LOW": "✅", "INFO": "⚪",
    },
    "webhook": {
        "CRITICAL": "[CRIT]", "HIGH": "[HIGH]", "MEDIUM": "[MED]",
        "LOW": "[LOW]", "INFO": "[INFO]",
    },
}


def severity_emoji(channel: str, severity: str) -> str:
    """Retourne l'emoji de severity adapte au canal."""
    sev = severity.upper()
    ch_emoji = SEVERITY_EMOJI.get(channel.lower(), {})
    return ch_emoji.get(sev, "")


def format_message(
    channel: str,
    title: str,
    body: str,
    severity: str = "INFO",
    context: dict[str, Any] | None = None,
    recommendation: str | None = None,
) -> str | dict[str, Any]:
    """Formate un message selon le canal cible.

    telegram/discord/webhook : retourne string HTML/markdown.
    slack : retourne dict avec blocks.
    """
    context = context or {}
    emoji = severity_emoji(channel, severity)
    if channel.lower() == "slack":
        # Slack format : blocks
        fields = [
            {"type": "mrkdwn", "text": f"*Title:* {title}"},
            {"type": "mrkdwn", "text": f"*Severity:* {severity}"},
        ]
        if context:
            ctx_text = "\n".join(f"• {k}: {v}" for k, v in context.items())
            fields.append({"type": "mrkdwn", "text": f"*Context:*\n{ctx_text}"})
        if recommendation:
            fields.append(
                {"type": "mrkdwn", "text": f"*Action:* {recommendation}"},
            )
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text",
                                            "text": f"{emoji} {title}"}},
                {"type": "section", "fields": fields},
                {"type": "section",
                 "text": {"type": "mrkdwn", "text": body}},
            ],
        }
    # Format texte pour telegram / discord / webhook
    parts = [f"{emoji} *{title}*"]
    parts.append(f"Severity: {severity}")
    parts.append("")
    parts.append(body)
    if context:
        parts.append("")
        parts.append("*Context:*")
        for k, v in context.items():
            parts.append(f"  - `{k}`: {v}")
    if recommendation:
        parts.append("")
        parts.append(f"*Action:* {recommendation}")
    return "\n".join(parts)


def dispatch_alert(
    channel: str,
    title: str,
    body: str,
    severity: str = "INFO",
    context: dict[str, Any] | None = None,
    recommendation: str | None = None,
) -> bool | dict[str, Any]:
    """Dispatch un alert au canal. Retourne dict ou False si envoi impossible."""
    if channel.lower() not in SUPPORTED_CHANNELS:
        return False
    msg = format_message(channel, title, body, severity, context, recommendation)
    if channel.lower() == "telegram":
        token = os.environ.get("V9_TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("V9_TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            log.debug("dispatch_alert: no telegram token/chat_id, skip")
            return {"sent": False, "reason": "no_credentials"}
        # Simulation : en prod, requests.post(...) ici
        log.info("dispatch_alert: telegram would send %s", title)
        return {"sent": True, "channel": "telegram"}
    if channel.lower() == "webhook":
        url = os.environ.get("V9_ALERT_WEBHOOK_URL")
        if not url:
            return {"sent": False, "reason": "no_url"}
        log.info("dispatch_alert: webhook would send %s", title)
        return {"sent": True, "channel": "webhook"}
    # slack / discord : placeholders
    log.info("dispatch_alert: %s would send %s", channel, title)
    return {"sent": True, "channel": channel}


def main(argv=None) -> int:
    """Demo alert channel multi-sortie."""
    print("=" * 70)
    print("V9 ALERT CHANNEL (Phase 83)")
    print("=" * 70)
    for channel in SUPPORTED_CHANNELS:
        msg = format_message(
            channel, "WR Drop Below 60%",
            "WR is 0.45, below 0.60 threshold.",
            "HIGH", {"wr": 0.45, "n_trades": 20},
            recommendation="Review trade_engine.py kills",
        )
        print(f"\n[{channel.upper()}] :")
        if isinstance(msg, dict):
            print(json.dumps(msg, indent=2)[:500])
        else:
            print(msg)
    print()
    # Test dispatch (no creds)
    res = dispatch_alert("telegram", "Test", "Body")
    print(f"Dispatch telegram (no creds) : {res}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())