#!/usr/bin/env python3
"""v9_scoring.py — Hit rate / win rate par principe V9 (Phase 13 amorce).

Doctrine : lecture seule. Calcule les statistiques de WIN/LOSS par
principe à partir des décisions résolues (is_win NOT NULL). Aucune
logique d'exécution — pur outil de calibration post-trade.

Win rate par principe = (nb décisions où ce principe est déclenché ET
is_win=1) / (nb décisions où ce principe est déclenché ET is_win != NULL).
Ne compte PAS les décisions non résolues (is_win IS NULL).

Les principes listés sont :
  - Tous les principes présents dans principles.v9_status='ACTIVE'
  - Plus les principes observés dans les décisions résolues (pour ne
    pas louper un principe ACTIVE qui aurait été retiré du catalogue).

Usage :
    python scripts/v9_scoring.py
    python scripts/v9_scoring.py --min-samples 5    # filtre N < 5
    python scripts/v9_scoring.py --json             # sortie JSON
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.db_schema import get_connection  # noqa: E402


def _ensure_utf8_stdout() -> None:
    """Reconfigure stdout/stderr en UTF-8. Sans ceci, les caractères de
    dessin de boîte (═/─) du format console font planter le script sous
    console Windows cp1252 (même bug que v9_paper_trade_run.py, cf.
    DECISIONS_LOG 2026-07-08)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


# ---------- Helpers ----------


def _load_principes_catalogue(conn: sqlite3.Connection) -> list[str]:
    """Liste les principes ACTIVE connus du catalogue (v9_status='ACTIVE')."""
    try:
        rows = conn.execute(
            "SELECT DISTINCT principle_id FROM principles "
            "WHERE v9_status = 'ACTIVE' ORDER BY principle_id"
        ).fetchall()
        return [r[0] for r in rows]
    except sqlite3.OperationalError:
        # Table principles absente — fallback vide
        return []


def _compute_scoring(
    conn: sqlite3.Connection, min_samples: int = 0
) -> list[dict[str, Any]]:
    """Calcule le scoring par principe.

    Approche SQL pure (pas d'agrégation en Python) :
    - On extrait `principes_json` de chaque décision résolue (is_win NOT NULL).
    - json_each() déballe le tableau JSON en lignes.
    - GROUP BY principle_id compte nb, wins (is_win=1), win_rate.
    - On unionne avec le catalogue ACTIVE pour avoir 0 ligne sur les
      principes jamais résolus.

    Retourne une liste triée par win_rate DESC, puis nb DESC.
    """
    conn.row_factory = sqlite3.Row

    # 1. Stats par principe observé dans décisions résolues.
    try:
        observed_rows = conn.execute(
            """
            SELECT
                je.value AS principle_id,
                COUNT(*) AS nb,
                SUM(CASE WHEN d.is_win = 1 THEN 1 ELSE 0 END) AS wins
            FROM decisions d, json_each(d.principes_json) je
            WHERE d.is_win IS NOT NULL
              AND je.value IS NOT NULL AND je.value != ''
            GROUP BY je.value
            """,
        ).fetchall()
    except sqlite3.OperationalError:
        observed_rows = []

    observed_stats: dict[str, dict[str, int]] = {
        r["principle_id"]: {"nb": int(r["nb"]), "wins": int(r["wins"])}
        for r in observed_rows
    }

    # 2. Catalogue ACTIVE — garantit une ligne par principe connu.
    catalogue = _load_principes_catalogue(conn)

    # 3. Fusion : tous les principes vus OU tous les principes catalogue.
    all_principes = sorted(set(catalogue) | set(observed_stats.keys()))

    scoring: list[dict[str, Any]] = []
    for pid in all_principes:
        stats = observed_stats.get(pid, {"nb": 0, "wins": 0})
        nb = stats["nb"]
        wins = stats["wins"]
        win_rate = (wins / nb) if nb > 0 else None
        scoring.append({
            "principle_id": pid,
            "nb": nb,
            "wins": wins,
            "win_rate": win_rate,
            "in_catalogue": pid in catalogue,
        })

    # Tri : win_rate DESC (None en dernier), puis nb DESC
    scoring.sort(
        key=lambda r: (
            -(r["win_rate"] if r["win_rate"] is not None else -1.0),
            -r["nb"],
            r["principle_id"],
        )
    )

    # Filtre min_samples
    if min_samples > 0:
        scoring = [r for r in scoring if r["nb"] >= min_samples]

    return scoring


def _total_resolved(conn: sqlite3.Connection) -> int:
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT COUNT(*) AS n FROM decisions WHERE is_win IS NOT NULL"
        ).fetchone()
        return int(r["n"]) if r else 0
    except sqlite3.OperationalError:
        return 0


# ---------- Format ----------


def _format_console(scoring: list[dict], total_resolved: int) -> str:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "═" * 50,
        f"  Scoring principes V9 — {now_iso}",
        "═" * 50,
        f"  {'Principe':<32} | {'N':>4} | {'Win':>4} | {'WinRate':>8}",
        "  " + "─" * 56,
    ]
    if not scoring:
        lines.append("  (aucun principe connu — base vide)")
    else:
        for r in scoring:
            pid_short = r["principle_id"][:32]
            wr_str = f"{r['win_rate']*100:>6.1f}%" if r["win_rate"] is not None else "    —   "
            lines.append(
                f"  {pid_short:<32} | {r['nb']:>4} | {r['wins']:>4} | {wr_str:>8}"
            )
    lines.append("  " + "─" * 56)
    lines.append(f"  Total décisions résolues : {total_resolved}")
    if total_resolved == 0:
        lines.append("")
        lines.append("  Aucune décision résolue — lancer")
        lines.append("  v9_resolve_decision.py après chaque trade")
    return "\n".join(lines)


# ---------- CLI ----------


def main() -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Scoring hit rate / win rate par principe V9 (lecture seule).",
    )
    parser.add_argument(
        "--min-samples", type=int, default=0,
        help="Filtre les principes avec nb < N (défaut 0 = tout afficher).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Sortie JSON structurée.",
    )
    args = parser.parse_args()

    conn = get_connection()
    try:
        scoring = _compute_scoring(conn, min_samples=args.min_samples)
        total = _total_resolved(conn)
    finally:
        conn.close()

    if args.json:
        print(json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_decisions_resolues": total,
                "min_samples": args.min_samples,
                "scoring": scoring,
            },
            indent=2, ensure_ascii=False, default=str,
        ))
    else:
        print(_format_console(scoring, total))

    return 0


if __name__ == "__main__":
    sys.exit(main())