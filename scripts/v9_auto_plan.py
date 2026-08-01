"""v9_auto_plan.py — Phase 61.2 motion CEO 48H non-stop.

Generateur automatique de la prochaine phase.
Trie les pending par score stat (impact + tests + simplicite + dependance).

Auteur : Hermes (Phase 61.2 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.auto_plan")

PHASE_SCORES = {
    "Phase 62 — Pipeline orchestrator": {
        "impact": 0.85, "tests": 0.7, "simple": 0.6, "depend": 0.7,
    },
    "Phase 63 — FTMO compliance": {
        "impact": 0.95, "tests": 0.8, "simple": 0.7, "depend": 0.8,
    },
    "Phase 64 — Real money preflight": {
        "impact": 0.90, "tests": 0.8, "simple": 0.8, "depend": 0.6,
    },
    "Phase 65 — Smart order router": {
        "impact": 0.75, "tests": 0.7, "simple": 0.5, "depend": 0.5,
    },
    "Phase 66 — Live metrics dashboard": {
        "impact": 0.70, "tests": 0.7, "simple": 0.6, "depend": 0.6,
    },
    "Phase 67 — ML forecaster": {
        "impact": 0.85, "tests": 0.6, "simple": 0.4, "depend": 0.5,
    },
    "Phase 68 — Performance persistence": {
        "impact": 0.65, "tests": 0.7, "simple": 0.7, "depend": 0.6,
    },
    "Phase 69 — Cross-pair correlation live": {
        "impact": 0.60, "tests": 0.7, "simple": 0.6, "depend": 0.7,
    },
    "Phase 70 — Chaos engineering advanced": {
        "impact": 0.75, "tests": 0.8, "simple": 0.5, "depend": 0.6,
    },
    "Phase 71 — Adversarial testing": {
        "impact": 0.65, "tests": 0.7, "simple": 0.5, "depend": 0.5,
    },
    "Phase 72 — E2E pipeline test": {
        "impact": 0.85, "tests": 0.9, "simple": 0.5, "depend": 0.8,
    },
    "Phase 73 — Docs coherence auto-sync": {
        "impact": 0.70, "tests": 0.7, "simple": 0.7, "depend": 0.5,
    },
    "Phase 74 — User guide enrichi": {
        "impact": 0.60, "tests": 0.6, "simple": 0.8, "depend": 0.5,
    },
    "Phase 75 — Auto-pr + merge": {
        "impact": 0.70, "tests": 0.6, "simple": 0.7, "depend": 0.6,
    },
    "Phase 76 — Advanced backtest": {
        "impact": 0.75, "tests": 0.7, "simple": 0.5, "depend": 0.6,
    },
    "Phase 77 — Risk parity": {
        "impact": 0.80, "tests": 0.7, "simple": 0.5, "depend": 0.6,
    },
    "Phase 78 — Drawdown protector": {
        "impact": 0.85, "tests": 0.7, "simple": 0.6, "depend": 0.7,
    },
    "Phase 79 — Final bilan 48h": {
        "impact": 0.60, "tests": 0.5, "simple": 0.9, "depend": 0.4,
    },
    "Phase 80 — Auto-pr + tag release": {
        "impact": 0.65, "tests": 0.5, "simple": 0.8, "depend": 0.3,
    },
}


def compute_score(phase: str) -> float:
    """Calcule score 0-1 pour une phase."""
    scores = PHASE_SCORES.get(phase, {
        "impact": 0.5, "tests": 0.5, "simple": 0.5, "depend": 0.5,
    })
    return round(
        0.30 * scores["impact"]
        + 0.30 * scores["tests"]
        + 0.20 * scores["simple"]
        + 0.20 * scores["depend"],
        3,
    )


def rank_phases(phases: list[str]) -> list[dict]:
    """Trie phases par score DESC."""
    return sorted(
        [{"name": p, "score": compute_score(p)} for p in phases],
        key=lambda x: x["score"],
        reverse=True,
    )


def next_phase(pending: list[str]) -> Optional[dict]:
    """Retourne la prochaine phase (la plus prioritaire)."""
    if not pending:
        return None
    ranked = rank_phases(pending)
    return ranked[0]


def generate_emergent() -> dict:
    """Genere une phase emergente (roadmap finie)."""
    return {
        "name": "Phase 81 — Emergent (system improvement)",
        "score": 0.5,
        "emergent": True,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 auto plan (Phase 61.2)",
    )
    parser.add_argument("--next", action="store_true",
                        help="Affiche prochaine phase")
    parser.add_argument("--rank", action="store_true",
                        help="Affiche ranking complet")
    args = parser.parse_args(argv)

    from scripts.v9_phase_tracker import load_state

    state = load_state()
    pending = state.get("phases_pending", [])

    if args.rank:
        ranked = rank_phases(pending)
        print("=" * 70)
        print("V9 AUTO PLAN — RANKING")
        print("=" * 70)
        for p in ranked:
            print(f"  {p['score']:.3f}  {p['name']}")
        print("=" * 70)
        return 0

    if args.next:
        nxt = next_phase(pending)
        if nxt is None:
            nxt = generate_emergent()
        print(json.dumps(nxt, indent=2, ensure_ascii=False))
        return 0

    # Default : next
    nxt = next_phase(pending)
    if nxt is None:
        nxt = generate_emergent()
    print(json.dumps(nxt, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())