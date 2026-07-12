#!/usr/bin/env python3
"""v9_regenerate_principle_scores.py — (Re)génère `principle_scores` (Brief O1).

La table `principle_scores` (core/v9/principle_scorer.py) n'existe pas
encore en production — jamais peuplée avant ce brief. Ce script la
crée/vide puis la reconstruit intégralement à partir des décisions
`preparer_entree` résolues (is_win NOT NULL), sur les labels DYNAMIC/
SKIPPED fraîchement appliqués par `v9_batch_resolve_dynamic_full.py`
(au lieu des anciens labels TP_SL obsolètes).

Doctrine :
- Lecture/écriture déterministe uniquement, zéro LLM (R18).
- --dry-run par défaut ; --apply requis pour écrire.
- Idempotent au sens "régénération" : repart toujours de zéro
  (DELETE FROM principle_scores) pour éviter tout double comptage —
  ce n'est PAS un append incrémental.

Usage :
    python scripts/v9_regenerate_principle_scores.py --dry-run
    python scripts/v9_regenerate_principle_scores.py --apply
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.principle_scorer import PrincipleScorer  # noqa: E402

DEFAULT_REPORT_PATH = ROOT_DIR / "docs" / "reports" / "PRINCIPLE_SCORES_REGEN_20260712.json"


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _fetch_resolved_with_principles(conn: sqlite3.Connection) -> list[str]:
    """decision_id des décisions preparer_entree résolues avec principes_json
    non vide, triées par resolved_at (déterministe)."""
    rows = conn.execute(
        "SELECT decision_id FROM decisions "
        "WHERE action = 'preparer_entree' AND is_win IS NOT NULL "
        "AND principes_json IS NOT NULL AND principes_json != '' "
        "AND principes_json != '[]' "
        "ORDER BY resolved_at ASC, timestamp ASC"
    ).fetchall()
    return [r[0] for r in rows]


def regenerate(db_path: Path, apply: bool) -> dict[str, Any]:
    scorer = PrincipleScorer(db_path=db_path)  # crée le schéma si absent
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        target_ids = _fetch_resolved_with_principles(conn)
        n_before = conn.execute("SELECT COUNT(*) FROM principle_scores").fetchone()[0]

        if not apply:
            return {
                "dry_run": True,
                "n_target_decisions": len(target_ids),
                "n_principle_scores_before": n_before,
            }

        conn.execute("DELETE FROM principle_scores")
        conn.commit()

        n_updated = 0
        for did in target_ids:
            if scorer.update_from_decision(did, conn=conn):
                n_updated += 1

        n_after = conn.execute("SELECT COUNT(*) FROM principle_scores").fetchone()[0]
        top = scorer.get_top_combinations(limit=10, min_trades=5)

        return {
            "dry_run": False,
            "n_target_decisions": len(target_ids),
            "n_decisions_scored": n_updated,
            "n_principle_scores_before": n_before,
            "n_principle_scores_after": n_after,
            "top_combinations": top,
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="(Re)génère principle_scores sur les labels DYNAMIC/SKIPPED (Brief O1)"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args(argv)

    if not args.apply:
        print("[.. ] Mode : DRY-RUN (lecture seule)")

    result = regenerate(args.db, apply=args.apply)

    print(f"[.. ] Décisions cibles (résolues, avec principes) : {result['n_target_decisions']}")
    print(f"[.. ] principle_scores avant : {result['n_principle_scores_before']}")
    if args.apply:
        print(f"[OK ] principle_scores régénérée : {result['n_principle_scores_after']} lignes "
              f"({result['n_decisions_scored']} décisions scorées)")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[OK ] Rapport écrit : {args.report}")
    else:
        print("Aucun changement appliqué (dry-run). Relancer avec --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
