#!/usr/bin/env python3
"""regime_change_monitor — Agent dédié V9 #2/4.

Subscribe : event_type=regime_change (41x/24h)
Poll : 5 min
Action : à chaque transition de régime (PALIER → EXTENSION etc.),
         alerte Telegram UNIQUEMENT si nouveau régime ≠ NEUTRE
         (silence si transition NEUTRE → NEUTRE).

R25' : log + alerte Telegram. Aucune modif YAML/seuil.
R8 : 0 modif core/v9/* (consomme agent_bus API).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.dedicated_agent_base import DedicatedAgent


class RegimeChangeMonitor(DedicatedAgent):
    agent_name = "regime_change_monitor"
    event_type = "regime_change"
    poll_interval_s = 300  # 5 min

    def on_event(self, event: dict) -> None:
        payload = event.get("payload", {})
        symbol = payload.get("symbol", "?")
        timeframe = payload.get("timeframe", "?")
        regime_new = payload.get("regime_new", "?")
        regime_prev = payload.get("regime_prev", "?")
        timestamp = payload.get("timestamp", "?")

        self.logger.info(
            "[%s/%s] %s → %s (timestamp=%s)",
            symbol, timeframe, regime_prev, regime_new, timestamp,
        )

        # Alerte Telegram UNIQUEMENT si nouveau régime ≠ NEUTRE
        if regime_new == "NEUTRE":
            return  # Silence (transition non-trading)

        emoji = {
            "PALIER": "🟡", "EXTENSION": "🟢", "ACCUMULATION": "🟠",
            "DISTRIBUTION": "🔴", "REJET": "🔵", "COMPRESSION": "🟣",
        }.get(regime_new, "⚪")

        self._send_telegram_alert(
            f"{emoji} Régime changé\n"
            f"  {symbol} {timeframe}\n"
            f"  {regime_prev} → {regime_new}\n"
            f"  {timestamp}"
        )

    def _send_telegram_alert(self, text: str) -> None:
        try:
            payload = (json.dumps({
                "tool": "send_message",
                "args": {"text": f"🔄 regime_change_monitor\n\n{text}"}
            }) + "\n").encode("utf-8")
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(
                [sys.executable, "mcp_servers/telegram_server.py"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, cwd=str(ROOT),
            )
            proc.communicate(input=payload, timeout=15)
        except Exception as e:
            self.logger.warning("Telegram send failed: %s", e)


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="V9 regime_change_monitor agent.")
    p.add_argument("--once", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=None)
    args = p.parse_args()

    agent = RegimeChangeMonitor()
    if args.interval:
        agent.poll_interval_s = args.interval

    if args.once:
        return 0 if agent.run_once() >= 0 else 1
    if args.watch:
        agent.run_forever()
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())