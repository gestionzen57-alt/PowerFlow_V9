#!/usr/bin/env python3
"""principle_cluster_logger — Agent dédié V9 #3/4.

Subscribe : event_type=principle_cluster (50x/24h)
Poll : 10 min
Action : log les snapshots avec ≥3 principes triggered (= "confluence forte"
         = moment V9). Distribution par TF, par heure, par nombre de principes.

R25' : log seul. Aucune modif YAML/seuil.
R8 : 0 modif core/v9/* (consomme agent_bus API).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.dedicated_agent_base import DedicatedAgent


class PrincipleClusterLogger(DedicatedAgent):
    agent_name = "principle_cluster_logger"
    event_type = "principle_cluster"
    poll_interval_s = 600  # 10 min

    def __init__(self) -> None:
        super().__init__()
        # Stats cumulatives
        self._by_hour: Counter = Counter()
        self._by_n: Counter = Counter()
        self._total_events = 0

    def on_event(self, event: dict) -> None:
        payload = event.get("payload", {})
        snapshot_id = payload.get("snapshot_id", "?")
        n_triggered = payload.get("n_triggered", 0)
        timestamp = event.get("created_at", "")
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            hour_key = dt.strftime("%H:00")
        except Exception:
            hour_key = "?"

        self._by_hour[hour_key] += 1
        self._by_n[n_triggered] += 1
        self._total_events += 1

        self.logger.info(
            "[%s] n_triggered=%d hour=%s (total=%d)",
            snapshot_id, n_triggered, hour_key, self._total_events,
        )

        # Stats rollup tous les 10 events
        if self._total_events % 10 == 0:
            top_hours = self._by_hour.most_common(3)
            top_n = self._by_n.most_common(3)
            self.logger.info(
                "STATS [%d events] top_hours=%s top_n_triggered=%s",
                self._total_events, top_hours, top_n,
            )


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="V9 principle_cluster_logger agent.")
    p.add_argument("--once", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=None)
    args = p.parse_args()

    agent = PrincipleClusterLogger()
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