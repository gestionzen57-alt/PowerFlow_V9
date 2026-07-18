#!/usr/bin/env python
"""scripts/v9_migrate_cvd.py — migration CVD (Chantier C, 2026-07-18).

Ajoute les colonnes `cvd_delta` / `cvd_cumul` à forces_snapshots sur la base
cible (défaut : data/v9_forces.db). Idempotent, additif, non-destructif :
ADD COLUMN en SQLite est O(1) (metadata only), sûr même sur une base de
plusieurs Go.

⚠️ Prod live : à lancer dans une fenêtre contrôlée. Après migration, redémarrer
le capture_server pour qu'il recharge les colonnes effectives (cache pragma).
L'EA V9_Sonde_M1.mq4 doit être recompilé/redéployé pour émettre cvd_delta/cvd_cumul.
Rien n'est écrit tant que V9_CVD_ENABLED != 1.

Usage :
    python scripts/v9_migrate_cvd.py                 # data/v9_forces.db
    python scripts/v9_migrate_cvd.py --db path.db
    python scripts/v9_migrate_cvd.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.v9.config import DB_PATH  # noqa: E402
from core.v9.db_schema import get_connection, migrate_cvd  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Migration CVD forces_snapshots (Chantier C)")
    parser.add_argument("--db", type=str, default=None, help="Chemin DB (défaut: config.DB_PATH)")
    parser.add_argument("--dry-run", action="store_true", help="N'applique rien, affiche l'état")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DB_PATH
    if not db_path.exists():
        print(f"[migrate_cvd] base introuvable: {db_path}")
        return 1

    conn = get_connection(db_path)
    try:
        existing = {d[1] for d in conn.execute("PRAGMA table_info(forces_snapshots)").fetchall()}
        missing = [c for c in ("cvd_delta", "cvd_cumul") if c not in existing]
        if not missing:
            print(f"[migrate_cvd] déjà à jour ({db_path}) — cvd_delta/cvd_cumul présents.")
            return 0
        if args.dry_run:
            print(f"[migrate_cvd] DRY-RUN — colonnes à ajouter: {missing} ({db_path})")
            return 0
        added = migrate_cvd(conn)
        conn.commit()
        print(f"[migrate_cvd] OK — colonnes ajoutées: {added} ({db_path})")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
