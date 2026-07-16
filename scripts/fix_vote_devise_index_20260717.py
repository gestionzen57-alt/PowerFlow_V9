#!/usr/bin/env python
"""fix_vote_devise_index_20260717.py — Correctif du biais vote-devise NZD.

CAUSE RACINE (audit reprise 2026-07-17) :
    L'index UNIQUE `idx_pe_snapshot_principle (snapshot_id, principle_id)`
    ajouté le 2026-07-06 (dédup DB, cf. DECISIONS_LOG) garantissait
    l'idempotence à une époque où le vote-devise assignait TOUT à une
    seule devise (NZD) par snapshot. Depuis le fix DIVERSIFY (15-16/07),
    `PrincipleEngine.evaluate_principles()` produit correctement 8
    évaluations (une par devise) pour chaque principe scope=ALL, MAIS
    `_write_evaluations_to_db()` utilise INSERT OR REPLACE : les 8 lignes
    entrent en collision sur le triple tronqué `(snapshot_id, principle_id)`
    et se collapsent en UNE seule — la DERNIÈRE écrite. Or l'ordre du loop
    est DEVISES = [USD, GBP, EUR, JPY, CAD, CHF, AUD, NZD] : NZD est
    toujours dernier, donc NZD écrase systématiquement les 7 autres.
    => 96-99 % des lignes persistées portent currency='NZD', quel que soit
    le symbole du snapshot (GBPUSD, USDJPY, ...). Le moteur est CORRECT ;
    c'est l'index UNIQUE tronqué qui détruit la granularité par-devise.

PREUVE (live, 2026-07-17) :
    eng.evaluate_principles(usdjpy_sid) retourne 440 évals = 55/devise,
    44 ACTIVE/devise (parfaitement équilibré).
    Après persistance : DB ne contient que NZD (44) + quelques SHADOW.

CORRECTIF :
    Remplacer l'index UNIQUE `(snapshot_id, principle_id)` par
    `(snapshot_id, principle_id, currency)`. Préserve l'idempotence du
    rejeu (un recalcul du même snapshot+principe+devise REPLACE la ligne)
    tout en laissant coexister les 8 devises.

    Additif R2 : ne casse pas GBPUSD (écrit toujours, désormais avec les 8
    devises au lieu de NZD seul). Idempotent, rejouable. Backup MD5 exigé
    par R8 fait AVANT exécution (data/v9_forces.db.bak_20260717_votedevise).

Usage :
    python scripts/fix_vote_devise_index_20260717.py --db data/v9_forces.db [--apply]
    (dry-run par défaut ; --apply pour exécuter)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

OLD_INDEX = "idx_pe_snapshot_principle"           # (snapshot_id, principle_id)  — FAUTIF
NEW_INDEX = "idx_pe_snapshot_principle_currency"  # (snapshot_id, principle_id, currency)  — CORRECT
NEW_INDEX_SQL = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX} "
    "ON principle_evaluations (snapshot_id, principle_id, currency)"
)


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _dup_count(conn: sqlite3.Connection) -> int:
    """Doublons sur le triple cible — doit être 0 avant création UNIQUE."""
    return conn.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM principle_evaluations "
        "GROUP BY snapshot_id, principle_id, currency HAVING COUNT(*) > 1)"
    ).fetchone()[0]


def migrate(db_path: str, apply: bool) -> int:
    conn = sqlite3.connect(db_path)
    try:
        has_old = _index_exists(conn, OLD_INDEX)
        has_new = _index_exists(conn, NEW_INDEX)
        dups = _dup_count(conn)
        print(f"[etat] {OLD_INDEX} present : {has_old}")
        print(f"[etat] {NEW_INDEX} present : {has_new}")
        print(f"[etat] doublons (snapshot,principle,currency) : {dups}")

        if has_new and not has_old:
            print("[ok] deja migre — rien a faire.")
            return 0
        if dups > 0:
            print(f"[STOP] {dups} doublons sur le triple cible — refuse de "
                  "creer un index UNIQUE (dedup requise avant).")
            return 2
        if not apply:
            print("\n[dry-run] Actions qui seraient executees avec --apply :")
            if not has_new:
                print(f"  CREATE UNIQUE INDEX {NEW_INDEX} (snapshot_id, principle_id, currency)")
            if has_old:
                print(f"  DROP INDEX {OLD_INDEX}")
            return 0

        # Application (transaction implicite sqlite3)
        conn.execute(NEW_INDEX_SQL)
        if has_old:
            conn.execute(f"DROP INDEX {OLD_INDEX}")
        conn.commit()
        print(f"\n[applique] {NEW_INDEX} cree, {OLD_INDEX} supprime.")
        print(f"[verif] {NEW_INDEX} present : {_index_exists(conn, NEW_INDEX)}")
        print(f"[verif] {OLD_INDEX} present : {_index_exists(conn, OLD_INDEX)}")
        return 0
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="data/v9_forces.db")
    p.add_argument("--apply", action="store_true", help="execute (sinon dry-run)")
    args = p.parse_args()
    return migrate(args.db, args.apply)


if __name__ == "__main__":
    sys.exit(main())
