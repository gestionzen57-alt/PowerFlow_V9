#!/usr/bin/env python3
"""high_resolution_win_analyzer — Agent dédié V9 #4/4.

Subscribe : event_type=high_resolution_win (33x/24h)
Poll : 15 min
Action : agrège les WIN résolus significatifs (pips > 20) par
         (symbol, TF, direction). Détecte les configs les plus rentables.
         Stat rollup tous les 25 events.

R25' : log seul. Aucune modif YAML/seuil.
R8 : 0 modif core/v9/* (consomme agent_bus API).
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.dedicated_agent_base import DedicatedAgent


class HighResolutionWinAnalyzer(DedicatedAgent):
    agent_name = "high_resolution_win_analyzer"
    event_type = "high_resolution_win"
    poll_interval_s = 900  # 15 min

    def __init__(self) -> None:
        super().__init__()
        # Stats par (symbol, timeframe, direction)
        self._by_config: dict[tuple[str, str, str], dict] = defaultdict(
            lambda: {"count": 0, "total_pips": 0.0, "max_pips": 0.0}
        )
        self._total_events = 0
        self._total_pips = 0.0

    def on_event(self, event: dict) -> None:
        payload = event.get("payload", {})
        symbol = payload.get("symbol", "?")
        timeframe = payload.get("timeframe", "?")
        direction = payload.get("direction", "?")
        pips = float(payload.get("pips", 0))
        decision_id = payload.get("decision_id", "?")

        self._total_events += 1
        self._total_pips += pips

        key = (symbol, timeframe, direction)
        s = self._by_config[key]
        s["count"] += 1
        s["total_pips"] += pips
        s["max_pips"] = max(s["max_pips"], pips)

        self.logger.info(
            "[%s] %s %s %s +%.1fp (config_total=%d, sum_pips=%.1f)",
            decision_id, symbol, timeframe, direction, pips,
            s["count"], s["total_pips"],
        )

        # Stats rollup tous les 25 events
        if self._total_events % 25 == 0:
            self._log_stats_rollup()

    def _log_stats_rollup(self) -> None:
        """Log les top configs par (symbol, TF, direction)."""
        sorted_configs = sorted(
            self._by_config.items(),
            key=lambda x: x[1]["total_pips"],
            reverse=True,
        )[:5]
        self.logger.info(
            "STATS [%d events, sum_pips=%.1f] top_configs:",
            self._total_events, self._total_pips,
        )
        for (sym, tf, dirn), s in sorted_configs:
            avg = s["total_pips"] / s["count"]
            self.logger.info(
                "  %s %s %s : %d wins, avg=%.1fp, max=%.1fp",
                sym, tf, dirn, s["count"], avg, s["max_pips"],
            )


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="V9 high_resolution_win_analyzer agent.")
    p.add_argument("--once", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=None)
    args = p.parse_args()

    agent = HighResolutionWinAnalyzer()
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