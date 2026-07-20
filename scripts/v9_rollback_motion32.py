#!/usr/bin/env python
"""v9_rollback_motion32.py — rollback de la Motion #32 (idempotence paper_trades).

Rollback APPLICATIF non destructif : supprime l'index unique
`idx_pt_snap_dir_princ` posé par la migration `20260720_unique_paper_trade.sql`.
Ne touche AUCUNE donnée (les lignes restent intactes ; seule la contrainte tombe).

Le rollback du CODE (guard ON CONFLICT dans PaperTradeLogger.log_open) se fait via
git : `git revert -m 1 <merge>` ou `git reset --hard pre-motion-32-resolve-drift`.

Usage :
    python scripts/v9_rollback_motion32.py --dry-run     # affiche, n'écrit rien
    python scripts/v9_rollback_motion32.py               # supprime l'index
    python scripts/v9_rollback_motion32.py --db chemin.db

Sortie : code 0 si l'index est absent à la fin (rollback effectif ou déjà absent).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

INDEX_NAME = "idx_pt_snap_dir_princ"


def _index_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (INDEX_NAME,),
    ).fetchone()
    return row is not None


def rollback(db_path: Path, dry_run: bool = False) -> int:
    if not db_path.exists():
        print(f"[rollback] DB introuvable : {db_path}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        present = _index_exists(conn)
        print(f"[rollback] index {INDEX_NAME} présent = {present}")
        if not present:
            print("[rollback] rien à faire (index déjà absent).")
            return 0
        if dry_run:
            print("[rollback] DRY-RUN : DROP INDEX non exécuté.")
            return 0
        conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
        conn.commit()
        ok = not _index_exists(conn)
        print(f"[rollback] index supprimé = {ok}")
        return 0 if ok else 1
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rollback Motion #32 (idempotence paper_trades).")
    p.add_argument("--db", default="data/v9_forces.db", help="Chemin de la DB (défaut: data/v9_forces.db)")
    p.add_argument("--dry-run", action="store_true", help="Affiche sans écrire.")
    args = p.parse_args(argv)
    return rollback(Path(args.db), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
