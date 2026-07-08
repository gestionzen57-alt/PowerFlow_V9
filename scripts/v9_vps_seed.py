#!/usr/bin/env python3
"""v9_vps_seed.py — Prépare une DB v9_forces.db allégée pour le déploiement VPS.

Copie data/v9_forces.db vers une DB dédiée, purge tout ce qui a plus de
N jours (7 par défaut) table par table sur la colonne temporelle
pertinente, VACUUM, puis recrée les tables/index (idempotent, via
`init_all_dbs` — la même fonction utilisée par `scripts/v9_bootstrap.py`
et les fixtures pytest) pour repartir sur une base propre et compacte.

Ne touche jamais la DB source : travaille uniquement sur la copie.

Tables non purgées (conservées intégralement) : `principles` (règles
actives, pas une série temporelle), `sqlite_sequence` (interne SQLite).
`agent_telemetry` et `learning_proposals` sont copiées mais pas
réindexées explicitement : leurs fonctions d'init (`init_telemetry_db`,
`init_learning_db`) ciblent toujours `core.v9.config.DB_PATH` en dur, pas
un chemin arbitraire — les rouvrir sur la copie risquerait de recréer
les tables sur la DB de PRODUCTION. VACUUM ne supprime pas leurs index
existants, donc rien n'est perdu.

Usage:
    python scripts/v9_vps_seed.py
    python scripts/v9_vps_seed.py --days 3
    python scripts/v9_vps_seed.py --source data/v9_forces.db --dest /tmp/seed.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.db_schema import init_all_dbs  # noqa: E402
from core.v9.agent_bus import init_agent_bus_db  # noqa: E402
from core.v9.flow_probe import init_probe_schema  # noqa: E402

DEFAULT_SOURCE = ROOT_DIR / "data" / "v9_forces.db"
DEFAULT_DEST = ROOT_DIR / "data" / "v9_forces_seed.db"

# Table -> colonne temporelle utilisée pour la purge >7j. Tables absentes
# de ce dict sont conservées intégralement (état/config, pas une série
# temporelle d'événements).
PURGE_COLUMNS = {
    "forces_snapshots": "timestamp",
    "behaviors": "timestamp",
    "decisions": "timestamp",
    "exploitability": "timestamp",
    "scenes": "timestamp",
    "signals": "timestamp",
    "windows": "timestamp",
    "principle_evaluations": "timestamp",
    "regime_snapshots": "timestamp",
    "zone_diagnostics": "timestamp",
    "agent_telemetry": "ts",
    "probe_events": "ts",
    "paper_trades": "opened_at",
    "learning_proposals": "created_at",
}


def copy_db(source: Path, dest: Path) -> None:
    """Copie source -> dest via l'API backup sqlite3 (cohérent même sous WAL)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src_conn = sqlite3.connect(str(source))
    dest_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dest_conn)
    finally:
        src_conn.close()
        dest_conn.close()


def purge_older_than(conn: sqlite3.Connection, days: int) -> dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    deleted: dict[str, int] = {}
    existing_tables = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table, column in PURGE_COLUMNS.items():
        if table not in existing_tables:
            continue
        cur = conn.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))
        deleted[table] = cur.rowcount
    conn.commit()
    return deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare une DB V9 allegee pour le VPS")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)

    if not args.source.exists():
        print(f"[FAIL] DB source introuvable: {args.source}")
        return 1

    size_before = args.source.stat().st_size
    print(f"1. Copie {args.source} -> {args.dest} ({size_before / 1e6:.1f} Mo)...")
    copy_db(args.source, args.dest)

    conn = sqlite3.connect(str(args.dest))
    try:
        print(f"2. Purge des donnees > {args.days} jours...")
        deleted = purge_older_than(conn, args.days)
        for table, count in deleted.items():
            if count:
                print(f"   {table}: {count} lignes supprimees")
    finally:
        conn.close()

    print("3. VACUUM...")
    conn = sqlite3.connect(str(args.dest))
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()

    print("4. Recreation tables/index (idempotent, init_all_dbs)...")
    init_all_dbs(args.dest)
    init_agent_bus_db(args.dest)
    init_probe_schema(str(args.dest))

    size_after = args.dest.stat().st_size
    reduction = (1 - size_after / size_before) * 100 if size_before else 0
    print(
        f"=== SEED READY: {args.dest} ({size_after / 1e6:.1f} Mo, "
        f"{reduction:.0f}% de reduction) ==="
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
