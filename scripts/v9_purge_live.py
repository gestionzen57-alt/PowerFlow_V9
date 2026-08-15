#!/usr/bin/env python3
"""v9_purge_live.py — Purge principle_evaluations > 30j en mode LIVE tolérant.

Différent de v9_purge_principle_evaluations.py (qui suppose writers arrêtés) :
- DELETE par chunks de N rows (évite de monopoliser le lock writer)
- VACUUM retry sur SQLITE_BUSY (le VACUUM Online de SQLite est conçu pour ça)
- Aucune garantie d'atomicité — la table est cohérente avant ET après, mais
  quelques INSERTs live peuvent survenir pendant la purge (c'est le but).

Doctrine:
- R6 — pas de simulation, mesure pré/post
- R7 — motion CEO 2026-08-15 (« arrête tous les crons »)
- R8 — MD5 défensif posé avant
- R22 — 1 DECISIONS_LOG entry

Usage:
    python scripts/v9_purge_live.py [--days 30] [--chunk 1000000] [--vacuum-retries 30]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Force unbuffered stdout pour que la progression soit visible via
# process(action='poll', ...) en temps réel (sinon Python bufférise).
sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "v9_forces.db"
REPORT = REPO / "reports" / "v9_purge_live.json"


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def free_disk_gb(path: Path) -> float:
    import shutil
    return shutil.disk_usage(str(path)).free / 1024 ** 3


def measure_size_and_count(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.cursor()
    n = cur.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0]
    return n, 0  # size séparé


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--chunk", type=int, default=1_000_000)
    ap.add_argument("--vacuum-retries", type=int, default=60)
    ap.add_argument("--vacuum-sleep", type=float, default=2.0,
                    help="Secondes entre retries VACUUM")
    ap.add_argument("--no-vacuum", action="store_true")
    ap.add_argument("--no-md5", action="store_true")
    args = ap.parse_args()

    if not DB.exists():
        print(f"DB absente: {DB}", file=sys.stderr)
        return 2

    cutoff = (datetime.now(UTC) - timedelta(days=args.days)).isoformat()
    print(f"=== Purge LIVE principle_evaluations > {args.days}j (cutoff={cutoff}) ===")
    print(f"DB: {DB}  ({DB.stat().st_size/1024**3:.2f} Go)")
    print(f"Free disk: {free_disk_gb(DB):.2f} Go")
    print(f"Chunk: {args.chunk:,} rows par passe")

    # MD5 pré
    if not args.no_md5:
        t0 = time.time()
        md5_pre = md5_of(DB)
        print(f"MD5 pré: {md5_pre}  (en {time.time()-t0:.0f}s)")
        (REPO / "data" / "v9_forces.md5.purge_pre").write_text(
            f"{md5_pre}  {DB.name}\n"
        )

    conn = sqlite3.connect(str(DB), isolation_level=None, timeout=300)
    cur = conn.cursor()

    # Compteur initial
    n0 = cur.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0]
    print(f"\nRows initial: {n0:,}")

    # Purge par chunks
    total_deleted = 0
    pass_n = 0
    t_start = time.time()
    while True:
        pass_n += 1
        t0 = time.time()
        try:
            # DELETE avec LIMIT — SQLite 3.39+ supporte DELETE...LIMIT.
            # Pour vieille version, on simule avec rowid.
            cur.execute(
                "DELETE FROM principle_evaluations "
                "WHERE rowid IN ("
                "  SELECT rowid FROM principle_evaluations "
                "  WHERE created_at < ? LIMIT ?"
                ")",
                (cutoff, args.chunk),
            )
            n = cur.rowcount
        except sqlite3.OperationalError as e:
            print(f"  [pass {pass_n}] Erreur SQL: {e}", file=sys.stderr)
            break
        if n == 0:
            print(f"  [pass {pass_n}] 0 row deleted — purge terminée")
            break
        total_deleted += n
        elapsed = time.time() - t0
        n_now = cur.execute(
            "SELECT COUNT(*) FROM principle_evaluations"
        ).fetchone()[0]
        print(
            f"  [pass {pass_n}] -{n:,} rows ({elapsed:.1f}s) "
            f"→ {n_now:,} restants — total purgé: {total_deleted:,} — "
            f"cumul: {time.time()-t_start:.0f}s"
        )
        if n < args.chunk:
            break

    # Mesure post-purge
    n_post = cur.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0]
    span = cur.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM principle_evaluations"
    ).fetchone()
    print(f"\nRows post-purge: {n_post:,}  (plage: {span[0]} → {span[1]})")
    conn.close()

    # VACUUM avec retry sur SQLITE_BUSY
    if not args.no_vacuum:
        needed = DB.stat().st_size / 1024**3
        free = free_disk_gb(DB)
        print(f"\n=== VACUUM (besoin ~{needed:.1f} Go, libre: {free:.1f} Go) ===")
        for attempt in range(1, args.vacuum_retries + 1):
            t0 = time.time()
            try:
                vconn = sqlite3.connect(str(DB), isolation_level=None, timeout=10)
                vconn.execute("VACUUM")
                vconn.close()
                print(f"VACUUM OK en {time.time()-t0:.1f}s (tentative {attempt})")
                break
            except sqlite3.OperationalError as e:
                if "locked" in str(e) or "busy" in str(e).lower():
                    if attempt % 5 == 0:
                        print(
                            f"  VACUUM retry {attempt}/{args.vacuum_retries} "
                            f"({str(e)[:50]})..."
                        )
                    time.sleep(args.vacuum_sleep)
                    continue
                print(f"VACUUM échec: {e}", file=sys.stderr)
                break
        else:
            print(f"VACUUM échec après {args.vacuum_retries} tentatives", file=sys.stderr)

    # MD5 post
    if not args.no_md5:
        t0 = time.time()
        md5_post = md5_of(DB)
        print(f"MD5 post: {md5_post}  (en {time.time()-t0:.0f}s)")
        (REPO / "data" / "v9_forces.md5.purge_post").write_text(
            f"{md5_post}  {DB.name}\n"
        )

    # Rapport
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "retention_days": args.days,
        "cutoff": cutoff,
        "rows_initial": n0,
        "rows_deleted": total_deleted,
        "rows_post": n_post,
        "db_size_pre_gb": round(DB.stat().st_size / 1024**3, 3),
        "db_size_post_gb": round(DB.stat().st_size / 1024**3, 3),
        "free_disk_gb_post": round(free_disk_gb(DB), 2),
        "min_created_post": span[0],
        "max_created_post": span[1],
        "passes": pass_n,
    }
    if not args.no_md5:
        report["md5_pre"] = md5_pre
        report["md5_post"] = md5_post
    REPORT.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nRapport: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
