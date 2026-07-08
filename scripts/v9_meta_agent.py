#!/usr/bin/env python3
"""v9_meta_agent.py — CLI META-AGENT V9 (Phase 15, apprentissage autonome).

Surveille le bus (agent_event_bus), détecte les patterns récurrents et
propose des actions — appuyé sur core/v9/meta_agent.py. Aucune écriture
sur le pipeline cognitif (couches 1-9), aucune promotion YAML automatique
(R25' : la décision reste à Søn).

Usage :
    python scripts/v9_meta_agent.py --scan        # scanne les patterns et affiche
    python scripts/v9_meta_agent.py --learn       # cycle d'apprentissage complet
    python scripts/v9_meta_agent.py --proposals   # propositions en attente
    python scripts/v9_meta_agent.py --watch       # scan/10min, learn/60min
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.meta_agent import get_proposals, learn_cycle, scan_patterns  # noqa: E402

SCAN_INTERVAL_SECONDS = 600     # 10 min
LEARN_INTERVAL_SECONDS = 3600   # 60 min


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def render_patterns(patterns: list[dict], hours: int) -> str:
    if not patterns:
        return f"Aucun pattern détecté sur les dernières {hours}h."
    lines = [f"── PATTERNS DÉTECTÉS (dernières {hours}h) ──────────────────"]
    for p in patterns:
        detail = p.get("event_type") or p.get("lesson", "")[:60]
        lines.append(
            f"  {p['pattern_type']:<20} {detail!s:<40} freq={p['frequency']}"
        )
    return "\n".join(lines)


def render_proposals(proposals: list[dict]) -> str:
    if not proposals:
        return "Aucune proposition en attente."
    lines = ["── PROPOSITIONS EN ATTENTE (validation Søn) ────────────────"]
    for p in proposals:
        lines.append(
            f"  [{p.get('confidence'):.2f}] {p.get('action_type')} -> "
            f"{p.get('target')}\n      {p.get('rationale')}"
        )
    return "\n".join(lines)


def run_scan(db_path: Path, hours: int) -> int:
    patterns = scan_patterns(hours=hours, db_path=db_path)
    print(render_patterns(patterns, hours))
    return 0


def run_learn(db_path: Path, hours: int) -> int:
    proposals = learn_cycle(hours=hours, db_path=db_path)
    print(f"Cycle d'apprentissage : {len(proposals)} proposition(s) publiée(s) sur le bus.")
    print(render_proposals(proposals))
    return 0


def run_proposals(db_path: Path, limit: int) -> int:
    proposals = get_proposals(limit=limit, db_path=db_path)
    print(render_proposals(proposals))
    return 0


def run_watch(db_path: Path) -> int:
    """Boucle : scan toutes les SCAN_INTERVAL_SECONDS, learn toutes les LEARN_INTERVAL_SECONDS."""
    elapsed = 0
    try:
        while True:
            run_scan(db_path, hours=24)
            if elapsed % LEARN_INTERVAL_SECONDS == 0:
                run_learn(db_path, hours=24)
            time.sleep(SCAN_INTERVAL_SECONDS)
            elapsed += SCAN_INTERVAL_SECONDS
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="META-AGENT V9 — bus → patterns → propositions")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--hours", type=int, default=24, help="Fenêtre de scan (heures)")
    parser.add_argument("--limit", type=int, default=5, help="Nombre de propositions affichées")
    parser.add_argument("--scan", action="store_true", help="Scanne les patterns et affiche")
    parser.add_argument("--learn", action="store_true", help="Cycle d'apprentissage complet")
    parser.add_argument("--proposals", action="store_true", help="Propositions en attente")
    parser.add_argument("--watch", action="store_true", help="Boucle scan/10min, learn/60min")
    args = parser.parse_args(argv)

    if args.watch:
        return run_watch(args.db)
    if args.learn:
        return run_learn(args.db, args.hours)
    if args.proposals:
        return run_proposals(args.db, args.limit)
    if args.scan:
        return run_scan(args.db, args.hours)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
