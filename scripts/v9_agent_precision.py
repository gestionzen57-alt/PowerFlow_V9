#!/usr/bin/env python3
"""v9_agent_precision.py — Rapport de précision par agent (Mode A).

Affiche la table `v_agent_precision_report` pour la fenêtre demandée.

Usage:
    python scripts/v9_agent_precision.py                  # 7 derniers jours
    python scripts/v9_agent_precision.py --window 30      # 30 derniers jours
    python scripts/v9_agent_precision.py --json           # sortie JSON
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.agent_telemetry import init_telemetry_db, report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Rapport précision agents V9")
    parser.add_argument("--window", type=int, default=7, help="Fenêtre en jours (défaut 7)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    init_telemetry_db()
    rows = report(window_days=args.window)

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    if not rows:
        print(f"Aucune télémétrie enregistrée sur les {args.window} derniers jours.")
        return 0

    print(f"\nAGENT                | HITS    | ERRORS | LATENCE_AVG_MS | LATENCE_MAX_MS | DRIFT")
    print("-" * 80)
    for r in rows:
        name = (r.get("agent_name") or "?")[:19]
        hits = r.get("total_hits") or 0
        errors = r.get("total_errors") or 0
        avg = r.get("avg_latency_ms") or 0.0
        mx = r.get("max_latency_ms") or 0.0
        drift = r.get("avg_drift") or 0.0
        print(f"{name:20s} | {hits:7d} | {errors:7d} | {avg:14.2f} | {mx:15.2f} | {drift:.2f}")
    print(f"\nFenêtre : {args.window} jours — Sprint V9 mode autonome Søn 2026-07-07.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
