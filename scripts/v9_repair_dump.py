#!/usr/bin/env python3
"""v9_repair_dump.py — Réparation DB corrompue via dump row-by-row tolérant.

Procédure documentée dans skill v9-db-drainage-recovery §Corruption structurelle :
- Détecter les ranges rowid corrompues (binary search)
- Pour chaque range saine : lire en streaming (fetchone) + executemany dans DB repaired
- Skipper les ranges corrompues avec log
- Schema via executescript (multi-ligne préservée)
- WAL checkpoint avant swap atomique

Usage:
    python scripts/v9_repair_dump.py [--keep-old]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "data" / "v9_forces.db"
REPAIRED = REPO / "data" / "v9_forces_repaired.db"
OLD = REPO / "data" / "v9_forces_corrupted_20260815.db"
REPORT = REPO / "reports" / "v9_repair_dump.json"


def md5_of(path: Path) -> str:
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def free_gb(path: Path) -> float:
    return shutil.disk_usage(str(path)).free / 1024**3


def find_corrupt_ranges(src: Path, table: str, batch: int = 100_000) -> list[tuple[int, int]]:
    """Binary search pour trouver les ranges rowid corrompues sur la table donnée."""
    print(f"  Recherche ranges corrompues sur {table} (batch={batch:,})...", flush=True)
    c = sqlite3.connect(str(src), mode=sqlite3.URI, uri=True, timeout=10)
    try:
        max_rid = c.execute(f"SELECT MAX(rowid) FROM \"{table}\"").fetchone()[0]
    except Exception as e:
        print(f"  Erreur MAX(rowid): {e}", flush=True)
        c.close()
        return []
    if max_rid is None:
        c.close()
        return []
    print(f"  Max rowid: {max_rid:,}", flush=True)
    corrupt = []
    # Binary search: pour chaque chunk de `batch` rows, tester si SELECT plante
    for lo in range(1, max_rid + 1, batch):
        hi = min(lo + batch - 1, max_rid)
        try:
            c.execute(f"SELECT 1 FROM \"{table}\" WHERE rowid BETWEEN ? AND ? LIMIT 1", (lo, hi)).fetchone()
        except sqlite3.DatabaseError:
            corrupt.append((lo, hi))
            print(f"  [CORRUPT] rowid {lo:,}-{hi:,}", flush=True)
    c.close()
    return corrupt


def stream_table_to_repaired(src: Path, dst: Path, table: str, corrupt_ranges: list) -> int:
    """Stream toutes les rows de `table` de src vers dst, skip corrupt_ranges.
    Retourne le nombre de rows copiées."""
    print(f"  Stream {table}...", flush=True)
    csrc = sqlite3.connect(str(src), mode=sqlite3.URI, uri=True, timeout=30)
    cdst = sqlite3.connect(str(dst), timeout=60)
    cdst.execute("PRAGMA synchronous=OFF")  # Speed
    cdst.execute("PRAGMA journal_mode=WAL")
    cur_src = csrc.cursor()
    cur_dst = cdst.cursor()

    # Colonnes
    cols = [r[1] for r in cur_src.execute(f"PRAGMA table_info(\"{table}\")").fetchall()]
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join("?" for _ in cols)
    insert_sql = f'INSERT OR IGNORE INTO "{table}" ({cols_sql}) VALUES ({placeholders})'

    copied = 0
    last_id = 0
    chunk = []
    chunk_size = 5_000
    t_start = time.time()

    def in_corrupt(rid: int) -> bool:
        for lo, hi in corrupt_ranges:
            if lo <= rid <= hi:
                return True
        return False

    try:
        while True:
            try:
                cols_quoted = ", ".join(f'"{c}"' for c in cols)
                ph = ", ".join("?" for _ in cols)
                row = cur_src.execute(
                    f'SELECT {cols_quoted} FROM "{table}" WHERE rowid > ? ORDER BY rowid LIMIT ?',
                    (last_id, chunk_size),
                ).fetchone()
                if row is None:
                    break
                last_id = row[0] if "rowid" in cols else None
                # On utilise le rowid virtuel via une autre query
            except sqlite3.DatabaseError as e:
                print(f"    [BUST] {table} @ ~rowid {last_id}: {e}", flush=True)
                # Avancer last_id par bond pour skip la zone
                last_id = (last_id or 0) + 1_000_000
                continue

            # Lecture rowid pour skip corrupt
            if last_id is None:
                # Fallback: lire rowid explicitement
                rid_row = cur_src.execute(f'SELECT rowid FROM "{table}" ORDER BY rowid DESC LIMIT 1').fetchone()
                if rid_row:
                    last_id = rid_row[0]
                break

            if in_corrupt(last_id):
                # Skip
                pass
            else:
                chunk.append(row)
                if len(chunk) >= chunk_size:
                    cur_dst.executemany(insert_sql, chunk)
                    cdst.commit()
                    copied += len(chunk)
                    chunk = []
                    if copied % 50_000 == 0:
                        elapsed = time.time() - t_start
                        print(f"    ... {copied:,} rows copiees en {elapsed:.0f}s", flush=True)

        # Flush le reste
        if chunk:
            cur_dst.executemany(insert_sql, chunk)
            cdst.commit()
            copied += len(chunk)

    finally:
        csrc.close()
        cdst.commit()
        # Checkpoint WAL sur repaired
        cdst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        cdst.close()
    print(f"  {table}: {copied:,} rows copiees", flush=True)
    return copied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-old", action="store_true", help="Garder l'ancienne DB comme .corrupted")
    args = ap.parse_args()

    if not SRC.exists():
        print(f"DB absente: {SRC}", file=sys.stderr)
        return 2

    print(f"=== Repair DB via dump row-by-row ===", flush=True)
    print(f"Src: {SRC} ({SRC.stat().st_size/1024**3:.2f} Go)", flush=True)
    print(f"Free: {free_gb(SRC):.2f} Go", flush=True)

    # MD5 défensif R8
    md5_pre = md5_of(SRC)
    (REPO / "data" / "v9_forces.md5.repair_pre").write_text(f"{md5_pre}  {SRC.name}\n")
    print(f"MD5 pré: {md5_pre}", flush=True)

    # 1. Copier schema de src vers repaired
    print("=== Copie schema ===", flush=True)
    if REPAIRED.exists():
        REPAIRED.unlink()
    csrc = sqlite3.connect(str(SRC), timeout=60)
    csrc.execute("PRAGMA journal_mode=WAL")  # On copie tout sauf les rows
    schema_sql = "\n".join(r[0] for r in csrc.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall())
    csrc.close()

    cdst = sqlite3.connect(str(REPAIRED), timeout=60)
    cdst.executescript(schema_sql)
    cdst.commit()
    cdst.close()
    print(f"Schema copie ({len(schema_sql)} chars SQL)", flush=True)

    # 2. Lister tables à copier
    csrc = sqlite3.connect(str(SRC), timeout=30)
    tables = [r[0] for r in csrc.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    csrc.close()
    print(f"Tables a copier: {len(tables)}", flush=True)

    # 3. Identifier ranges corrompues par table
    corrupt_by_table = {}
    for t in tables:
        cr = find_corrupt_ranges(SRC, t)
        if cr:
            corrupt_by_table[t] = cr

    # 4. Stream table par table
    total_copied = 0
    tables_failed = []
    for t in tables:
        try:
            n = stream_table_to_repaired(SRC, REPAIRED, t, corrupt_by_table.get(t, []))
            total_copied += n
        except Exception as e:
            print(f"  ERREUR fatale sur {t}: {e}", flush=True)
            tables_failed.append(t)

    # 5. Copier les index (déjà créés via schema)
    print("=== Verification integrity repaired ===", flush=True)
    cdst = sqlite3.connect(str(REPAIRED), timeout=60)
    res = cdst.execute("PRAGMA quick_check").fetchone()
    print(f"  quick_check: {res[0] if isinstance(res, tuple) else res}", flush=True)
    cdst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    cdst.close()

    md5_post = md5_of(REPAIRED)
    (REPO / "data" / "v9_forces.md5.repair_post").write_text(f"{md5_post}  {REPAIRED.name}\n")

    print(f"\n=== Resultat ===", flush=True)
    print(f"DB repaired: {REPAIRED} ({REPAIRED.stat().st_size/1024**3:.2f} Go)", flush=True)
    print(f"MD5 post: {md5_post}", flush=True)
    print(f"Total rows copiees: {total_copied:,}", flush=True)
    print(f"Tables echouees: {tables_failed}", flush=True)
    print(f"Ranges corrompues skippees: {sum(len(v) for v in corrupt_by_table.values())}", flush=True)

    # Rapport
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "src_size_gb": round(SRC.stat().st_size / 1024**3, 3),
        "repaired_size_gb": round(REPAIRED.stat().st_size / 1024**3, 3),
        "md5_pre": md5_pre,
        "md5_post": md5_post,
        "rows_copied": total_copied,
        "tables_failed": tables_failed,
        "corrupt_ranges": {t: [(int(lo), int(hi)) for lo, hi in cr] for t, cr in corrupt_by_table.items()},
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print(f"Rapport: {REPORT}", flush=True)
    print(f"\nPour swap: mv {SRC} {OLD} && mv {REPAIRED} {SRC} && rm {OLD}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
