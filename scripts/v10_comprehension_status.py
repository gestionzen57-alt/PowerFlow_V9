"""V10 Comprehension Status — rapport d'état de la compréhension continue (Phase 9, Cognitive Continuum).

Agrège l'état de l'architecture de compréhension continue :
  - Registre d'interprétation (v10_behaviors) : n comportements, par qualification
  - Mémoire inter-cycles (v9_cycle_memory) : n patterns, par régime
  - Auto-cohérence : orphelins, modules connectés, verdict
  - Apprentissage : n behaviors résolus, WR par contexte

R9 : chaque chiffre sourcé d'un module/DB. R10 : compute only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)


def build() -> dict:
    from core.v10.v10_behavior_registry import registry_summary
    from core.v10.v10_memory_bridge import memory_summary
    from core.v10.v10_coherence_audit import audit_orphans

    reg = registry_summary()
    mem = memory_summary()
    coh = audit_orphans()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registre_interp": {
            "n_behaviors": reg.get("n_behaviors", 0),
            "n_resolved": reg.get("n_resolved", 0),
            "top_qualifications": dict(list(reg.get("by_qualification", {}).items())[:6]),
        },
        "memoire_intercycles": {
            "n_patterns": mem.get("n_patterns", 0),
            "by_regime": mem.get("by_regime", {}),
            "status": mem.get("status", "no_db"),
        },
        "auto_coherence": {
            "n_orphans": coh.get("n_orphans", 0),
            "n_connected": coh.get("n_connected", 0),
            "verdict": coh.get("verdict", "?"),
        },
        "audit": {"r10": "compute only, zero order real"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    report = build()
    if args.output:
        Path(args.output).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Rapport écrit: {args.output}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
