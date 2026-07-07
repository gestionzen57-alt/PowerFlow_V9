#!/usr/bin/env python3
"""v9_resolve_decision.py — Saisie manuelle du résultat réel d'une décision.

Doctrine : aucune logique d'exécution d'ordre avant Phase 12. Ce script
ne trade PAS — il permet à l'opérateur d'enregistrer le résultat
post-trade d'une décision (WIN/LOSS + pips) dans la table `decisions`.
Zéro apprentissage automatique, zéro recalibration : ces colonnes sont
des champs de collecte, alimentés à la main.

Usage :
    python scripts/v9_resolve_decision.py \
        --decision-id dec_df961c3f104b \
        --is-win true \
        --pips 18.5

    python scripts/v9_resolve_decision.py \
        --decision-id dec_df961c3f104b \
        --is-win false \
        --pips -12.3 \
        --force                    # écraser un enregistrement déjà résolu

    python scripts/v9_resolve_decision.py --list          # lister les décisions
    python scripts/v9_resolve_decision.py --list --unresolved  # seulement les NULL
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.decision_db import init_decision_db  # noqa: E402


# ---------- Helpers ----------


def _parse_bool(value: str) -> bool:
    """Accepte true/false/1/0/yes/no (insensible à la casse)."""
    v = value.strip().lower()
    if v in ("true", "1", "yes", "y", "win", "w"):
        return True
    if v in ("false", "0", "no", "n", "loss", "l"):
        return False
    raise argparse.ArgumentTypeError(
        f"Valeur booléenne invalide : {value!r}. Attendu : true/false/1/0/yes/no."
    )


def _fetch_decision(conn, decision_id: str) -> dict | None:
    # Force row_factory localement (get_connection() ne le pose pas).
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
    ).fetchone()
    return dict(row) if row else None


def _format_decision(d: dict) -> str:
    """Affichage lisible d'une décision (pour confirmation interactive)."""
    keys = [
        "decision_id", "timestamp", "snapshot_id", "symbol", "timeframe",
        "currency", "direction", "confiance", "action", "source_type",
        "regime_type", "is_win", "resolution_pips", "resolved_at",
    ]
    lines = [f"  {k:>20} : {d.get(k)!r}" for k in keys if k in d]
    return "\n".join(lines)


def _list_decisions(conn, unresolved_only: bool, limit: int = 50) -> list[dict]:
    conn.row_factory = sqlite3.Row
    where = " WHERE resolved_at IS NULL" if unresolved_only else ""
    rows = conn.execute(
        f"SELECT decision_id, timestamp, symbol, timeframe, direction, "
        f"confiance, action, is_win, resolution_pips, resolved_at, source_type "
        f"FROM decisions{where} "
        f"ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------- Commands ----------


def cmd_list(args) -> int:
    init_decision_db()
    conn = get_connection()
    try:
        rows = _list_decisions(conn, unresolved_only=args.unresolved, limit=args.limit)
    finally:
        conn.close()

    if not rows:
        print("Aucune décision trouvée.")
        return 0

    print(f"  Nb résultats : {len(rows)}\n")
    header = (
        f"  {'decision_id':<18} {'timestamp':<26} "
        f"{'symbol':<8} {'dir':<10} {'conf':>4} "
        f"{'action':<16} {'is_win':>6} {'pips':>7} {'resolved_at':<26}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in rows:
        is_win_str = "NULL" if r["is_win"] is None else str(int(r["is_win"]))
        pips_str = "NULL" if r["resolution_pips"] is None else f"{r['resolution_pips']:+.1f}"
        resolved_str = r["resolved_at"] or "NULL"
        print(
            f"  {r['decision_id']:<18} {r['timestamp']:<26} "
            f"{(r['symbol'] or '?'):<8} {(r['direction'] or '?'):<10} "
            f"{(r['confiance'] if r['confiance'] is not None else '-'):>4} "
            f"{(r['action'] or '?'):<16} {is_win_str:>6} {pips_str:>7} {resolved_str:<26}"
        )
    return 0


def cmd_resolve(args) -> int:
    init_decision_db()
    conn = get_connection()
    try:
        decision = _fetch_decision(conn, args.decision_id)
        if decision is None:
            print(
                f"[ERREUR] decision_id introuvable : {args.decision_id!r}\n"
                f"         Utilisez --list pour voir les décisions existantes.",
                file=sys.stderr,
            )
            return 1

        # Refus d'écrasement si déjà résolu (sans --force)
        already_resolved = decision.get("resolved_at") is not None
        if already_resolved and not args.force:
            print(
                f"[ERREUR] décision déjà résolue le {decision['resolved_at']} "
                f"(is_win={decision['is_win']}, pips={decision['resolution_pips']}).\n"
                f"         Utilisez --force pour écraser.",
                file=sys.stderr,
            )
            return 2

        print("Décision ciblée :")
        print(_format_decision(decision))
        print()
        print(f"  -> Résolution proposée :")
        print(f"     is_win         : {int(args.is_win)}")
        print(f"     resolution_pips: {args.pips:+.1f}")
        print(f"     resolved_at    : <NOW UTC>")
        if already_resolved:
            print(f"     (écrasement d'une résolution existante — --force actif)")
        print()

        # Confirmation interactive (sauf si --yes)
        if not args.yes:
            try:
                confirm = input("Confirmer ? [o/N] ").strip().lower()
            except EOFError:
                confirm = ""
            if confirm not in ("o", "oui", "y", "yes"):
                print("Annulé.")
                return 3

        # Mise à jour
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE decisions SET is_win = ?, resolution_pips = ?, resolved_at = ? "
            "WHERE decision_id = ?",
            (int(args.is_win), args.pips, now_iso, args.decision_id),
        )
        conn.commit()

        # Re-lecture pour confirmation
        updated = _fetch_decision(conn, args.decision_id)
        print("\nDécision après mise à jour :")
        print(_format_decision(updated))
        print(f"\n[OK] {args.decision_id} résolu.")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Saisie manuelle du résultat réel d'une décision V9 "
        "(WIN/LOSS + pips). Aucune logique d'exécution — collecte uniquement.",
    )
    parser.add_argument(
        "--decision-id",
        type=str,
        help="Identifiant decision_id (ex: dec_df961c3f104b).",
    )
    parser.add_argument(
        "--is-win",
        type=_parse_bool,
        help="Résultat : true=WIN, false=LOSS.",
    )
    parser.add_argument(
        "--pips",
        type=float,
        help="Pips réalisés (signe +/-, ex: 18.5 ou -12.3).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Écrase une résolution existante (sans confirmation préalable du statut).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip la confirmation interactive (utile en batch/scripts).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lister les décisions existantes (sans les modifier).",
    )
    parser.add_argument(
        "--unresolved",
        action="store_true",
        help="Avec --list : filtre seulement les décisions non résolues.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Avec --list : nb max de décisions affichées (défaut 50).",
    )
    args = parser.parse_args()

    if args.list:
        return cmd_list(args)

    # Mode resolve : tous les arguments requis
    missing = [n for n, v in (
        ("--decision-id", args.decision_id),
        ("--is-win", args.is_win),
        ("--pips", args.pips),
    ) if v is None]
    if missing:
        parser.error(
            f"Arguments manquants pour le mode resolve : {', '.join(missing)}. "
            f"Ou utilisez --list pour consulter les décisions."
        )

    return cmd_resolve(args)


if __name__ == "__main__":
    sys.exit(main())