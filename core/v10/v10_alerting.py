"""
v10_alerting.py — C11-OPT4 : Alerting Telegram / Webhook sur LiveGate OPEN

Envoie une notification quand LiveGate passe OPEN.
Fail-open R6 : toute erreur réseau est avalée avec warn.
R10 : aucun ordre — uniquement des notifications.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from typing import Any


@dataclass
class AlertConfig:
    webhook_url: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""
    enabled: bool = False


class AlertingService:
    """C11-OPT4 — Service d'alerting LiveGate OPEN."""

    def __init__(self, config: AlertConfig | None = None) -> None:
        self._cfg = config or AlertConfig()

    def notify_live_gate_open(self, report: dict[str, Any]) -> bool:
        """Déclenche une alerte quand live_ready=True."""
        if not self._cfg.enabled:
            return False
        msg = self._format_message(report)
        ok = False
        if self._cfg.webhook_url:
            ok = ok or self._send_webhook(msg)
        if self._cfg.telegram_token and self._cfg.telegram_chat_id:
            ok = ok or self._send_telegram(msg)
        return ok

    def _format_message(self, report: dict[str, Any]) -> str:
        wr = report.get("win_rate", 0.0)
        pnl = report.get("total_pnl", 0.0)
        sharpe = report.get("sharpe", 0.0)
        return (
            f"🟢 PowerFlow V10 — LiveGate OPEN\n"
            f"WR={wr:.1%} PnL={pnl:+.0f} Sharpe={sharpe:.2f}\n"
            f"Reason: {report.get('live_ready_reason', '')}"
        )

    def _send_webhook(self, message: str) -> bool:
        try:
            import urllib.request
            payload = json.dumps({"text": message}).encode()
            req = urllib.request.Request(
                self._cfg.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status < 300
        except Exception as e:
            warnings.warn(f"[C11-OPT4] Webhook error (fail-open): {e}")
            return False

    def _send_telegram(self, message: str) -> bool:
        try:
            import urllib.request
            url = (f"https://api.telegram.org/bot{self._cfg.telegram_token}"
                   f"/sendMessage?chat_id={self._cfg.telegram_chat_id}"
                   f"&text={urllib.request.quote(message)}")
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            warnings.warn(f"[C11-OPT4] Telegram error (fail-open): {e}")
            return False
