#!/usr/bin/env python3
"""signal_open_tracker — Agent dédié V9 #1/4.

Subscribe : event_type=signal_open (100x/24h)
Poll : 60s
Action : log TOUS les signaux directionnels (decision_id, direction,
         confiance, symbole, TF) + alerte Telegram si confiance >= 90
         ET direction = baissiere (tendance baissière confirmée).

R25' : log + alerte Telegram. Aucune modif YAML/seuil.
R8 : 0 modif core/v9/* (consomme agent_bus API).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.dedicated_agent_base import DedicatedAgent


class SignalOpenTracker(DedicatedAgent):
    agent_name = "signal_open_tracker"
    event_type = "signal_open"
    poll_interval_s = 60

    def on_event(self, event: dict) -> None:
        payload = event.get("payload", {})
        decision_id = payload.get("decision_id", "?")
        direction = payload.get("direction", "?")
        confiance = payload.get("confiance", 0)
        symbol = payload.get("symbol", "?")
        timeframe = payload.get("timeframe", "?")
        timestamp = payload.get("timestamp", "?")

        self.logger.info(
            "[%s] %s %s conf=%s %s/%s",
            decision_id, symbol, direction, confiance, timeframe, timestamp,
        )

        # Alerte Telegram si confiance >= 90 + direction baissière
        if confiance >= 90 and direction == "baissiere":
            self._send_telegram_alert(
                f"🔴 Signal baissier fort\n"
                f"  {symbol} {timeframe} conf={confiance}%\n"
                f"  decision_id: {decision_id}\n"
                f"  timestamp: {timestamp}"
            )

    def _send_telegram_alert(self, text: str) -> None:
        """Envoie via MCP telegram server (subprocess)."""
        try:
            payload = (json.dumps({
                "tool": "send_message",
                "args": {"text": f"🟠 signal_open_tracker\n\n{text}"}
            }) + "\n").encode("utf-8")
            import os
            import subprocess
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
    p = argparse.ArgumentParser(description="V9 signal_open_tracker agent.")
    p.add_argument("--once", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=None)
    args = p.parse_args()

    agent = SignalOpenTracker()
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