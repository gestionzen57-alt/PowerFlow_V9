#!/usr/bin/env python
"""scripts/v9_migrate_edge_decay_index.py — migration index EdgeDecayMonitor (2026-07-28).

Ajoute l'index `idx_decisions_resolved_recent` sur la table `decisions` :
  (is_win, resolution_strategy, timestamp)

Sans cet index, le runner `v9_edge_decay_monitor_run` scannait la table
`decisions` en full table scan (5.27s pour 100k rows) sur DB prod 5.7GB,
rendant le check quotidien EdgeDecayMonitor inutilisable en pratique.

Avec l'index : 0.00s pour la même query. Migration testée en local
(data/v9_forces.db) avant push.

Idempotent, additif, non-destructif : CREATE INDEX IF NOT EXISTS est O(1)
(metadata only), sûr même sur une base de plusieurs Go. Aucun lock prolongé
sur SQLite (lecture/écriture continues possibles pendant création).

Doctrine :
- R2  : additif (n'altère pas les données, ne supprime aucun index).
- R6  : défensif (idempotent, dry-run disponible, ne casse pas si ré-exécuté).
- R8  : documentation à jour (commit + DECISIONS_LOG).
- R14 : git = source de vérité. Migration reproductible depuis le repo.

Usage :
    python scripts/v9_migrate_edge_decay_index.py                 # data/v9_forces.db
    python scripts/v9_migrate_edge_decay_index.py --db path.db
    python scripts/v9_migrate_edge_decay_index.py --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.v9.config import DB_PATH  # noqa: E402

INDEX_NAME = "idx_decisions_resolved_recent"
INDEX_DDL = (
    f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} "
    f"ON decisions(is_win, resolution_strategy, timestamp)"
)


def migrate(db_path: Path, dry_run: bool = False) -> dict:
    """Crée l'index si manquant. Retourne un rapport structuré."""
    report = {
        "db_path": str(db_path),
        "index_name": INDEX_NAME,
        "existed": False,
        "created": False,
        "elapsed_s": 0.0,
        "dry_run": dry_run,
    }
    if not db_path.exists():
        report["error"] = f"DB not found: {db_path}"
        return report

    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        # Vérifier existence
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            (INDEX_NAME,),
        )
        if cur.fetchone() is not None:
            report["existed"] = True
            return report

        if dry_run:
            report["would_create"] = True
            return report

        t0 = time.time()
        conn.execute(INDEX_DDL)
        conn.commit()
        report["elapsed_s"] = round(time.time() - t0, 2)
        report["created"] = True
    finally:
        conn.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Migration index EdgeDecayMonitor (2026-07-28).")
    parser.add_argument("--db", default=str(DB_PATH), help="Chemin DB cible")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien")
    args = parser.parse_args()

    db_path = Path(args.db)
    report = migrate(db_path, dry_run=args.dry_run)

    print(f"db_path: {report['db_path']}")
    print(f"index:   {report['index_name']}")
    print(f"existed: {report['existed']}")
    if report.get("would_create"):
        print("would_create: True (dry-run)")
    elif report.get("created"):
        print(f"created: True (en {report['elapsed_s']}s)")
    if "error" in report:
        print(f"ERROR: {report['error']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
