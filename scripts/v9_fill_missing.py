#!/usr/bin/env python3
"""v9_fill_missing.py — Copier les tables manquantes depuis corrupted vers repaired.

Suite du dump : la repaired a toutes les tables SAUF les tables qui étaient
après principle_evaluations (regime_snapshots, scenes, signals, etc.).
Ce script extrait ces tables depuis la DB corrompue et les injecte.

Usage: python scripts/v9_fill_missing.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "data" / "v9_forces_corrupted_20260815.db"
DST = REPO / "data" / "v9_forces.db"

# Tables a remplir (vides dans repaired, OK dans corrupted)
TABLES = [
    "principles",
    "regime_snapshots",
    "scenes",
    "signals",
    "windows",
    "zone_diagnostics",
]


def main() -> int:
    import sqlite3
    csrc = sqlite3.connect(str(SRC), timeout=120)
    cdst = sqlite3.connect(str(DST), timeout=120)

    for table in TABLES:
        # Schema
        rows = csrc.execute(
            "SELECT sql FROM sqlite_master WHERE name=? AND sql IS NOT NULL", (table,)
        ).fetchall()
        if not rows:
            print(f"  [{table}] pas de schema dans src, skip", flush=True)
            continue
        sql = rows[0][0]
        # Verifier si table existe deja dans dst avec colonnes
        dst_cols = []
        try:
            dst_cols = [r[1] for r in cdst.execute(f"PRAGMA table_info(\"{table}\")").fetchall()]
        except sqlite3.OperationalError:
            pass

        if not dst_cols:
            # Creer la table dans dst
            cdst.execute(sql)
            cdst.commit()
            print(f"  [{table}] schema cree", flush=True)

        # Compter dans src
        try:
            n_src = csrc.execute(f"SELECT COUNT(*) FROM \"{table}\"").fetchone()[0]
        except sqlite3.DatabaseError as e:
            print(f"  [{table}] COUNT src ERROR: {e}", flush=True)
            continue

        # Compter dans dst
        n_dst = cdst.execute(f"SELECT COUNT(*) FROM \"{table}\"").fetchone()[0]
        if n_dst >= n_src:
            print(f"  [{table}] deja OK ({n_dst:,}/{n_src:,})", flush=True)
            continue

        print(f"  [{table}] copie {n_src - n_dst:,} rows...", flush=True)
        # Copier row par row par chunks
        cols = [r[1] for r in csrc.execute(f"PRAGMA table_info(\"{table}\")").fetchall()]
        cols_sql = ", ".join(f'"{c}"' for c in cols)
        ph = ",".join("?" for _ in cols)
        copied = 0
        batch = 5_000
        offset = 0
        while offset < n_src:
            try:
                rows_data = csrc.execute(
                    f'SELECT {cols_sql} FROM "{table}" LIMIT ? OFFSET ?',
                    (batch, offset),
                ).fetchall()
            except sqlite3.DatabaseError as e:
                print(f"    [{table}] SELECT ERROR @ offset {offset}: {e}", flush=True)
                offset += batch
                continue
            if not rows_data:
                break
            try:
                cdst.executemany(
                    f'INSERT OR IGNORE INTO "{table}" ({cols_sql}) VALUES ({ph})',
                    rows_data,
                )
                cdst.commit()
                copied += len(rows_data)
                offset += batch
            except sqlite3.DatabaseError as e:
                print(f"    [{table}] INSERT ERROR: {e}", flush=True)
                offset += batch
        print(f"  [{table}] {copied:,} rows copiees", flush=True)

    cdst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    cdst.close()
    csrc.close()

    print("\n=== Verification ===", flush=True)
    c = sqlite3.connect(str(DST), timeout=30)
    print(f"integrity_check: {c.execute('PRAGMA quick_check').fetchone()[0]}")
    for t in TABLES:
        n = c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        print(f"  {t:30s} {n:>15,}")
    print(f"DB size: {os.path.getsize(DST)/1024**3:.2f} Go", flush=True)
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
