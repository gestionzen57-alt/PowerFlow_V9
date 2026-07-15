"""v9_apply_approved_offsets.py — CLI dry-run / apply des weight_offset APPROVED.

Phase 14 (CEO autopilot 2026-07-15) — ferme la boucle R30 apprentissage.

Usage :
    python scripts/v9_apply_approved_offsets.py             # dry-run (défaut)
    python scripts/v9_apply_approved_offsets.py --apply     # apply (équivaut
                                                             # set V9_LEARNING_OFFSET_ENABLED=1
                                                             # + forcer lecture)
    python scripts/v9_apply_approved_offsets.py --status    # état par direction

Le module `core/v9/learning_offset_applier.py` est conçu pour fonctionner
en mode lecture seule : le kill switch `V9_LEARNING_OFFSET_ENABLED`
contrôle si la pondération est effectivement appliquée par `arbiter.consolidate()`.
Ce script est un outil d'INSPECTION (dry-run) / de visualisation (--status)
qui ne mute rien. Pour activer réellement le mécanisme, ajouter
`V9_LEARNING_OFFSET_ENABLED=1` dans `config/v9_kill_switches.env` (motion
CEO explicite requise, R25' strict).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.learning_offset_applier import (
    LEARNING_OFFSET_BOUNDS_BY_DIRECTION,
    LEARNING_OFFSET_BOUNDS_FALLBACK,
    LEARNING_OFFSET_ENABLED_ENV,
    LEARNING_OFFSET_MULT_NEUTRAL,
    LEARNING_OFFSET_WR_BASELINE,
    LearningOffsetApplier,
    _compute_multiplier_from_wr,
    learning_offset_enabled,
)


def _format_offsets(offsets: dict[str, dict]) -> str:
    if not offsets:
        return "  (aucune proposition APPROVED)"
    lines = []
    for direction in sorted(offsets.keys()):
        e = offsets[direction]
        sign = "↑ boost" if e["multiplier"] > 1.0 else (
            "↓ reduce" if e["multiplier"] < 1.0 else "= neutre"
        )
        lines.append(
            f"  {direction:<12s} multiplier={e['multiplier']:.3f}  {sign}  "
            f"WR={e['observed_wr']:.1%}  n={e['observed_n']}  "
            f"score={e['score']:.2f}  proposal={e['proposal_id']}"
        )
    return "\n".join(lines)


def cmd_dry_run() -> int:
    applier = LearningOffsetApplier()
    import sqlite3

    from core.v9.db_schema import get_connection
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    try:
        offsets = applier._load_approved_offsets(conn)
    finally:
        conn.close()

    print(f"--- DRY-RUN learning_offset (kill switch V9_LEARNING_OFFSET_ENABLED) ---")
    print(f"Switch status : {'ON' if learning_offset_enabled() else 'OFF (kill switch forcé OFF)'}")
    print(f"Environnement : {LEARNING_OFFSET_ENABLED_ENV} (défaut ON Phase 14.2, mettre à '0' pour désactiver)")
    print(f"Multiplicateur neutre : {LEARNING_OFFSET_MULT_NEUTRAL}")
    print(f"Multiplicateur bornes : fallback={LEARNING_OFFSET_BOUNDS_FALLBACK}")
    print(f"  haussiere={LEARNING_OFFSET_BOUNDS_BY_DIRECTION['haussiere']}  "
          f"baissiere={LEARNING_OFFSET_BOUNDS_BY_DIRECTION['baissiere']}")
    print(f"WR baseline (neutre)  : {LEARNING_OFFSET_WR_BASELINE:.0%}")
    print()
    print("Propositions APPROVED (par direction, garder meilleure WR) :")
    print(_format_offsets(offsets))
    print()
    print(
        "Note : ce dry-run ne mute rien. Le kill switch est ON par défaut\n"
        "(motion CEO §3.6 §1, 15/07). Pour forcer OFF (debug live) :\n"
        f"  export {LEARNING_OFFSET_ENABLED_ENV}=0\n"
        "  (R25 strict : activation = motion CEO implicite par le default ON,\n"
        "   désactivation = geste explicite CEO)."
    )
    return 0


def cmd_status() -> int:
    """État détaillé par direction (multiplicateur appliqué si actif)."""
    import sqlite3 as _sqlite3

    applier = LearningOffsetApplier()
    from core.v9.db_schema import get_connection

    conn = get_connection()
    conn.row_factory = _sqlite3.Row
    try:
        offsets = applier._load_approved_offsets(conn)
    finally:
        conn.close()

    out = {
        "kill_switch": LEARNING_OFFSET_ENABLED_ENV,
        "switch_on": learning_offset_enabled(),
        "neutral": LEARNING_OFFSET_MULT_NEUTRAL,
        "bounds": list(LEARNING_OFFSET_BOUNDS_FALLBACK),
        "bounds_by_direction": {
            k: list(v) for k, v in LEARNING_OFFSET_BOUNDS_BY_DIRECTION.items()
        },
        "wr_baseline": LEARNING_OFFSET_WR_BASELINE,
        "approved_by_direction": offsets,
        "n_directions": len(offsets),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_apply() -> int:
    """Note : depuis Phase 14.2 le switch est ON par défaut.

    Pour le désactiver : exporter `V9_LEARNING_OFFSET_ENABLED=0` avant
    de lancer le pipeline / l'orchestrateur.
    """
    print(
        f"Phase 14.2 : le kill switch est ON par défaut (motion CEO §3.6 §1).\n"
        f"  Pour désactiver : export {LEARNING_OFFSET_ENABLED_ENV}=0\n"
        f"  (R25 strict : activation = default ON, désactivation = geste explicite CEO)."
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Phase 14 — CLI dry-run/apply des weight_offset APPROVED (R30)",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--apply", action="store_true",
        help="Trace explicite de la procédure d'activation (pas de mutation auto).",
    )
    g.add_argument(
        "--status", action="store_true",
        help="État JSON détaillé par direction.",
    )
    g.add_argument(
        "--wr-test", type=float, default=None,
        help="Teste le mapping WR -> multiplicateur (sanity check).",
    )
    args = p.parse_args()

    if args.wr_test is not None:
        mult = _compute_multiplier_from_wr(args.wr_test)
        print(f"WR={args.wr_test:.0%} -> mult={mult:.3f} "
              f"(bornes fallback={LEARNING_OFFSET_BOUNDS_FALLBACK}, "
              f"par direction={LEARNING_OFFSET_BOUNDS_BY_DIRECTION})")
        return 0

    if args.status:
        return cmd_status()
    if args.apply:
        return cmd_apply()
    return cmd_dry_run()


if __name__ == "__main__":
    sys.exit(main())
