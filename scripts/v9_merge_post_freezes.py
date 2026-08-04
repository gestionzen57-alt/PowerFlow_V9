#!/usr/bin/env python
"""
R2 additif — Merge des données post-freeze depuis la DB corrompue (04/08)
vers la DB restaurée (freeze 03/08 05:43 UTC, quick_check ok).

Contexte (2026-08-04) :
  - P0 : corruption `principle_evaluations` (Tree 29 page 672620, btreeInitPage
    err 11) causée par write contention = 2+ capture_server simultanés
    (Phase 150 root cause, récidive 06:19/06:25 UTC).
  - Restore : data/v9_forces.db = freeze 03/08 05:43 (sain, référence Phase 149).
  - Fenêtre perdue (si non mergée) : 03/08 05:44 → 04/08 04:22 (~23h).

Stratégie merge :
  - Copier depuis la DB corrompue les lignes des tables SAINES avec
    timestamp > freeze_max, en INSERT OR IGNORE (idempotent).
  - `principle_evaluations` : table corrompue → NON mergée (données 23h perdues,
    acceptable : table de détail, re-alimentée en continu par le pipeline).
  - Vérifications avant/après : counts, min/max timestamp par table, quick_check.

Doctrine : R2 additif (nouveau script, 0 modif core/), R6 fail-open
(si une table est corrompue → skip + warning, jamais bloquant),
R8 backup MD5 avant modif, R14 SQL live = source de vérité.

Usage:
    python scripts/v9_merge_post_freezes.py --dry-run   # montre le plan
    python scripts/v9_merge_post_freezes.py --apply     # exécute
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.config import DB_PATH  # noqa: E402

# DB corrompue (source des lignes post-freeze) — backup R8 déjà fait :
# backups/db_corruption_20260804/v9_forces_corrupted_20260804.db (MD5 6f6c8b2a…)
CORRUPTED_DB = ROOT / "backups" / "db_corruption_20260804" / "v9_forces_corrupted_20260804.db"

# Tables à merger (timestamp = colonne de fraîcheur) — SANS principle_evaluations
# (corrompue) ni tables dérivées re-générées par le pipeline.
MERGE_TABLES = {
    "forces_snapshots": "timestamp",
    "scenes": "timestamp",
    "signals": "timestamp",
    "decisions": "timestamp",
    "behaviors": "timestamp",
    "exploitability": "timestamp",
    "windows": "timestamp",
    "mtf_confirmations": "timestamp",
    "regime_snapshots": "timestamp",
    "probe_events": "timestamp",
    "zone_diagnostics": "timestamp",
}


def _ts_max(conn: sqlite3.Connection, table: str, col: str) -> str | None:
    try:
        return conn.execute(f'SELECT MAX("{col}") FROM "{table}"').fetchone()[0]
    except sqlite3.DatabaseError:
        return None


def plan() -> list[dict]:
    """Calcule les lignes à merger par table (lecture seule)."""
    out = []
    with sqlite3.connect(f"file:{CORRUPTED_DB}?mode=ro", uri=True) as src, \
         sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as dst:
        for table, ts_col in MERGE_TABLES.items():
            src_max = _ts_max(src, table, ts_col)
            dst_max = _ts_max(dst, table, ts_col)
            if src_max is None or dst_max is None:
                out.append({"table": table, "status": "SKIP (corrompue ou vide)", "rows": 0})
                continue
            try:
                n = src.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{ts_col}" > ?', (dst_max,)
                ).fetchone()[0]
                out.append({"table": table, "src_max": src_max, "dst_max": dst_max,
                            "rows": n, "status": "MERGE"})
            except sqlite3.DatabaseError as e:
                out.append({"table": table, "status": f"SKIP ({str(e)[:40]})", "rows": 0})
    return out


def apply() -> None:
    """Merge effectif avec INSERT OR IGNORE."""
    rows_total = 0
    with sqlite3.connect(str(DB_PATH), timeout=60) as dst, \
         sqlite3.connect(f"file:{CORRUPTED_DB}?mode=ro", uri=True) as src:
        for table, ts_col in MERGE_TABLES.items():
            dst_max = _ts_max(dst, table, ts_col)
            if dst_max is None:
                print(f"[SKIP] {table}: pas de max dans la cible")
                continue
            try:
                n = src.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{ts_col}" > ?', (dst_max,)
                ).fetchone()[0]
                if n == 0:
                    print(f"[OK]   {table}: 0 ligne à merger")
                    continue
                # Colonnes communes
                cols = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")').fetchall()]
                cols_sql = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join("?" for _ in cols)
                sql = f'INSERT OR IGNORE INTO "{table}" ({cols_sql}) VALUES ({placeholders})'
                batch = []
                cur = src.execute(
                    f'SELECT * FROM "{table}" WHERE "{ts_col}" > ?', (dst_max,)
                )
                for row in cur:
                    batch.append(row)
                    if len(batch) >= 5000:
                        dst.executemany(sql, batch)
                        batch.clear()
                if batch:
                    dst.executemany(sql, batch)
                dst.commit()
                rows_total += n
                print(f"[OK]   {table}: {n} lignes mergées (>{dst_max})")
            except sqlite3.DatabaseError as e:
                print(f"[SKIP] {table}: {str(e)[:60]}")
    print(f"\nTOTAL: {rows_total} lignes mergées")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="affiche le plan sans écrire")
    ap.add_argument("--apply", action="store_true", help="exécute le merge")
    args = ap.parse_args()

    if args.apply:
        apply()
    else:
        for p in plan():
            print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
