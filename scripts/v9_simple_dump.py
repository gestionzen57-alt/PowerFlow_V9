#!/usr/bin/env python3
"""v9_simple_dump.py — Dump row-by-row tolérant + reconstruction.

Plus simple que v9_repair_dump.py : juste iterate sur toutes les tables,
fetchone par fetchone, skip les erreurs, INSERT dans repaired.

Usage: python scripts/v9_simple_dump.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "data" / "v9_forces.db"
DST = REPO / "data" / "v9_forces_repaired.db"


def main() -> int:
    print("=== Simple dump row-by-row ===", flush=True)
    print(f"Src: {SRC} ({SRC.stat().st_size/1024**3:.2f} Go)", flush=True)
    print(f"Free: {shutil.disk_usage(str(SRC)).free/1024**3:.2f} Go", flush=True)

    # 1. Créer DST vide avec même schema
    if DST.exists():
        DST.unlink()
    csrc = sqlite3.connect(str(SRC), timeout=60)
    # Schema multi-ligne via concatenation brutale
    schemas = []
    for sql, in csrc.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND type IN ('table','index','view','trigger')"
    ).fetchall():
        if sql:
            schemas.append(sql + ";")
    csrc.close()
    cdst = sqlite3.connect(str(DST), timeout=120)
    cdst.executescript("\n".join(schemas))
    cdst.commit()
    cdst.close()
    print(f"Schema copie: {len(schemas)} objets", flush=True)

    # 2. Pour chaque table : SELECT all rows + INSERT dans DST
    csrc = sqlite3.connect(str(SRC), timeout=60)
    cur_src = csrc.cursor()
    cdst = sqlite3.connect(str(DST), timeout=120)
    cdst.execute("PRAGMA journal_mode=DELETE")  # Eviter WAL sur repaired
    cur_dst = cdst.cursor()

    tables = [r[0] for r in cur_src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]

    total_ok = 0
    total_fail = 0
    t_start = time.time()
    for tname in tables:
        # Colonnes
        cols = [r[1] for r in cur_src.execute(f"PRAGMA table_info(\"{tname}\")").fetchall()]
        if not cols:
            continue
        cols_sql = ", ".join(f'"{c}"' for c in cols)
        ph = ",".join("?" for _ in cols)
        # Get total count (avec gestion d'erreur)
        try:
            n_total = cur_src.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
        except sqlite3.DatabaseError as e:
            print(f"  [{tname}] COUNT plante: {e}", flush=True)
            total_fail += 1
            continue
        print(f"  [{tname}] {n_total:,} rows a copier...", flush=True)
        # SELECT * LIMIT 1 OFFSET N : on prend tout par offset
        # Plus robuste que fetchone en streaming : on peut skipper les rows corrompues
        offset = 0
        copied = 0
        batch = 5_000
        while offset < n_total:
            try:
                rows = cur_src.execute(
                    f'SELECT {cols_sql} FROM "{tname}" LIMIT ? OFFSET ?',
                    (batch, offset),
                ).fetchall()
            except sqlite3.DatabaseError as e:
                print(f"    [{tname}] FATAL @ offset {offset}: {e}", flush=True)
                # Avancer par bond
                offset += batch
                continue
            if not rows:
                break
            # Insert
            try:
                cur_dst.executemany(
                    f'INSERT OR IGNORE INTO "{tname}" ({cols_sql}) VALUES ({ph})',
                    rows,
                )
                cdst.commit()
                copied += len(rows)
                offset += batch
            except sqlite3.DatabaseError as e:
                print(f"    [{tname}] INSERT fail: {e}", flush=True)
                # Tenter row par row
                for row in rows:
                    try:
                        cur_dst.execute(
                            f'INSERT OR IGNORE INTO "{tname}" ({cols_sql}) VALUES ({ph})',
                            row,
                        )
                    except sqlite3.DatabaseError:
                        pass  # skip
                cdst.commit()
                offset += batch
        print(f"  [{tname}] {copied:,}/{n_total:,} copiees ({100*copied/max(n_total,1):.1f}%)", flush=True)
        total_ok += copied
        total_fail += max(0, n_total - copied)

    cur_src.close()
    cdst.commit()
    cdst.close()

    print(f"\n=== Resultat ===", flush=True)
    print(f"Total rows copiees: {total_ok:,}", flush=True)
    print(f"Total rows perdues (corruption): {total_fail:,}", flush=True)
    print(f"DB repaired: {DST} ({DST.stat().st_size/1024**3:.2f} Go)", flush=True)
    print(f"Gain par rapport a src: {(SRC.stat().st_size - DST.stat().st_size)/1024**3:.2f} Go", flush=True)
    print(f"\nPour swap: mv {SRC} {SRC}.corrupt && mv {DST} {SRC}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
