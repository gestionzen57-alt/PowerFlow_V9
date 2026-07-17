"""v9_telegram_alerts.py — Système d'alertes Telegram intelligent V9.

2026-07-17 motion CEO « orchestre et optimise au max, hedge fund mondial ».

Envoie des alertes contextuelles sur les événements importants du système :

  1. alert_dd_protection() : changement de palier du DrawdownProtector
     (normal -> reduce_50 -> halt_24h -> halt_forever).
  2. alert_trade_milestone() : paliers 100, 500, 1000, 5000, 10000 trades.
  3. alert_drawdown() : drawdown courant vs peak (alerte si > seuil).

Implémentation :
  - httpx / urllib (stdlib) ; pas de SDK Telegram tiers.
  - Mode mock (par défaut) : on logge et on accumule dans une deque interne,
    AUCUN appel réseau réel n'est émis.
  - Mode live (--live) : on construit l'URL
    https://api.telegram.org/bot<token>/sendMessage et on envoie.
  - Cooldown global pour ne pas spammer.
  - R6 : try/except sur chaque appel.
  - R18 : pas de LLM. Templates de messages statiques.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

TELEGRAM_ALERTER_VERSION = "1.0"

# Milestones (paliers de notification de trades clôturés)
TRADE_MILESTONES: tuple[int, ...] = (100, 500, 1000, 5000, 10000, 25000, 50000)

# Seuils d'alerte drawdown (en pips ou % d'equity)
DD_ALERT_THRESHOLDS: tuple[float, ...] = (50.0, 100.0, 200.0, 500.0)

# Taille max de l'historique in-memory (mode mock)
MAX_HISTORY = 500


@dataclass
class AlertRecord:
    """Une alerte envoyée (ou mockée)."""

    kind: str
    title: str
    message: str
    sent_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    delivered: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TelegramAlerter:
    """Système d'alertes Telegram avec cooldown et mode mock.

    Modes :
      - mock (par défaut) : aucune requête réseau ; les alertes sont
        stockées dans `self.history` et loggées via le logger 'v9'.
      - live : POST JSON vers https://api.telegram.org/bot<token>/sendMessage.
        Nécessite un token/chat_id réels et la connectivité sortante.

    Cooldown : si deux alertes du même kind sont envoyées à moins de
    `cooldown_seconds` d'intervalle, la seconde est silenciée (mais
    tout de même loggée).
    """

    def __init__(
        self,
        token: str = "",
        chat_id: str = "",
        *,
        cooldown_seconds: int = 300,
        live_mode: bool = False,
        timeout: float = 5.0,
    ) -> None:
        self.token = token
        self.chat_id = chat_id
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self.live_mode = bool(live_mode)
        self.timeout = float(timeout)
        self._last_sent: dict[str, float] = {}  # kind -> monotonic_ts
        self.history: deque[AlertRecord] = deque(maxlen=MAX_HISTORY)
        self._dry = not (self.live_mode and self.token and self.chat_id)

    # ── Cooldown ────────────────────────────────────────────────────

    def _cooldown_ok(self, kind: str) -> bool:
        now = time.monotonic()
        last = self._last_sent.get(kind, 0.0)
        if now - last < self.cooldown_seconds:
            return False
        self._last_sent[kind] = now
        return True

    # ── Envoi (mock ou live) ────────────────────────────────────────

    def _send(self, kind: str, title: str, message: str) -> AlertRecord:
        rec = AlertRecord(kind=kind, title=title, message=message)
        if self._dry:
            log.info(
                "[telegram:mock] %s — %s\n%s", kind, title, message
            )
            rec.delivered = True
            rec.error = "mock_mode"
            self.history.append(rec)
            return rec

        # Live : POST Telegram
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = urllib.parse.urlencode({
                "chat_id": self.chat_id,
                "text": f"*{title}*\n\n{message}",
                "parse_mode": "Markdown",
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                body = resp.read().decode("utf-8", errors="replace")
                rec.delivered = True
                log.info("[telegram:live] %s delivered (HTTP %s)", kind, resp.status)
                if len(body) > 200:
                    log.debug("[telegram:live] body=%s...", body[:200])
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            rec.error = f"{type(exc).__name__}: {exc}"
            log.error("[telegram:live] %s a échoué: %s", kind, rec.error)
        except Exception as exc:  # R6
            rec.error = f"unexpected: {exc}"
            log.error("[telegram:live] %s unexpected: %s", kind, rec.error)
        finally:
            self.history.append(rec)
        return rec

    # ── API publique ────────────────────────────────────────────────

    def _is_milestone(self, n_trades: int) -> int | None:
        """Retourne le palier atteint si n_trades correspond exactement, sinon None."""
        for m in TRADE_MILESTONES:
            if n_trades == m:
                return m
        return None

    def alert_dd_protection(self, action: str, dd_pct: float) -> bool:
        """Alerte quand le DrawdownProtector change de palier.

        Args:
            action : 'normal' | 'reduce_50' | 'halt_24h' | 'halt_forever'
            dd_pct : drawdown courant (float, ex 7.5 pour 7.5%)

        Returns True si l'alerte a été envoyée (ou mockée).
        """
        try:
            if action not in ("normal", "reduce_50", "halt_24h", "halt_forever"):
                log.warning("[telegram] action DD inconnue: %s", action)
                return False
            title = f"🛡️ DD Protector → {action}"
            message = (
                f"*Action* : `{action}`\n"
                f"*Drawdown* : `{dd_pct:.2f}%`\n"
                f"*Seuil atteint* : palier de protection actif."
            )
            if not self._cooldown_ok("dd_protection"):
                log.debug("[telegram] cooldown dd_protection, skip")
                return False
            rec = self._send("dd_protection", title, message)
            return rec.delivered
        except Exception as exc:  # R6
            log.error("[telegram] alert_dd_protection: %s", exc)
            return False

    def alert_trade_milestone(self, n_trades: int, pnl: float) -> bool:
        """Alerte milestone (100, 500, 1000, 5000 trades).

        Ne déclenche QUE si n_trades correspond exactement à un palier.
        Args:
            n_trades : nombre cumulé de trades clôturés.
            pnl : PnL cumulé (en pips).
        """
        try:
            milestone = self._is_milestone(int(n_trades))
            if milestone is None:
                log.debug(
                    "[telegram] n_trades=%s n'est pas un milestone (paliers=%s)",
                    n_trades,
                    TRADE_MILESTONES,
                )
                return False
            title = f"🎯 Milestone : {milestone} trades"
            message = (
                f"*Trade #{milestone} clôturé.*\n"
                f"*PnL cumulé* : `{pnl:+.1f}` pips"
            )
            if not self._cooldown_ok("milestone"):
                log.debug("[telegram] cooldown milestone, skip")
                return False
            rec = self._send("milestone", title, message)
            return rec.delivered
        except Exception as exc:  # R6
            log.error("[telegram] alert_trade_milestone: %s", exc)
            return False

    def alert_drawdown(self, current_dd: float, peak_dd: float) -> bool:
        """Alerte drawdown anormal.

        Déclenche si current_dd >= un seuil de DD_ALERT_THRESHOLDS.
        Ne re-déclenche pas tant qu'on n'a pas franchi un palier supérieur
        (logique 'seuils croissants').
        """
        try:
            if current_dd <= 0:
                return False
            triggered = None
            for t in DD_ALERT_THRESHOLDS:
                if current_dd >= t:
                    triggered = t
            if triggered is None:
                return False
            # Pas de re-alerte pour le même palier (cooldown implicite par kind)
            kind = f"drawdown_{int(triggered)}"
            if not self._cooldown_ok(kind):
                return False
            title = f"⚠️ Drawdown {triggered:g}+ atteint"
            message = (
                f"*Drawdown courant* : `{current_dd:.1f}` pips\n"
                f"*Peak DD* : `{peak_dd:.1f}` pips\n"
                f"*Seuil* : `{triggered:g}` pips"
            )
            rec = self._send(kind, title, message)
            return rec.delivered
        except Exception as exc:  # R6
            log.error("[telegram] alert_drawdown: %s", exc)
            return False

    # ── Utilitaires ─────────────────────────────────────────────────

    def get_history(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.history]

    def clear_history(self) -> None:
        self.history.clear()
        self._last_sent.clear()


# ── CLI entry point ────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram Alerter V9")
    parser.add_argument("--test", action="store_true", help="Envoie un message test (mock)")
    parser.add_argument("--token", default="", help="Bot Telegram token (vide = mock)")
    parser.add_argument("--chat-id", default="", help="Chat ID Telegram")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Mode live (envoi réel via Telegram API)",
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=0,
        help="Cooldown en secondes (0 = pas de cooldown)",
    )
    args = parser.parse_args()

    alerter = TelegramAlerter(
        token=args.token,
        chat_id=args.chat_id,
        cooldown_seconds=args.cooldown,
        live_mode=args.live,
    )

    if args.test:
        # Envoie 3 alertes représentatives
        alerter.alert_dd_protection("reduce_50", dd_pct=7.2)
        alerter.alert_trade_milestone(100, pnl=572.3)
        alerter.alert_drawdown(current_dd=120.0, peak_dd=180.0)
        print(json.dumps({
            "version": TELEGRAM_ALERTER_VERSION,
            "dry_mode": alerter._dry,
            "history": alerter.get_history(),
        }, indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())