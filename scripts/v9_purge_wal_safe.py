#!/usr/bin/env python3
"""v9_purge_wal_safe.py — Purge principle_evaluations avec checkpoint WAL forcé.

La version v9_purge_live.py a montré qu'à partir du 3e chunk, SQLite retourne
"database disk image is malformed" — sans doute à cause du WAL non tronqué
qui accumule des pages anciennes pendant qu'on DELETE massivement.

Cette variante force PRAGMA wal_checkpoint(TRUNCATE) entre chaque chunk pour
garder le wal minimal. Aussi, on commit APRÈS chaque chunk (et non pas
en batch) pour libérer le lock writer immédiatement.

Usage:
    python scripts/v9_purge_wal_safe.py --days 14 --chunk 100000
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "v9_forces.db"
REPORT = REPO / "reports" / "v9_purge_wal_safe.json"


def free_disk_gb(path: Path) -> float:
    import shutil
    return shutil.disk_usage(str(path)).free / 1024 ** 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--chunk", type=int, default=100_000)
    ap.add_argument("--checkpoint-every", type=int, default=1,
                    help="PRAGMA wal_checkpoint(TRUNCATE) toutes les N passes")
    ap.add_argument("--max-passes", type=int, default=200,
                    help="Garde-fou: stop après N passes (défaut 200 = 20M rows)")
    args = ap.parse_args()

    if not DB.exists():
        print(f"DB absente: {DB}", file=sys.stderr)
        return 2

    cutoff = (datetime.now(UTC) - timedelta(days=args.days)).isoformat()
    print(f"=== Purge WAL-SAFE principle_evaluations > {args.days}j ===")
    print(f"DB: {DB}  ({DB.stat().st_size/1024**3:.2f} Go)")
    print(f"Free: {free_disk_gb(DB):.2f} Go  | Cutoff: {cutoff}  | Chunk: {args.chunk:,}")

    # Connexion longue, checkpoint entre chaque chunk
    conn = sqlite3.connect(str(DB), isolation_level=None, timeout=300)
    cur = conn.cursor()
    # S'assurer qu'on est en WAL (le default depuis longtemps)
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")  # ~2x plus rapide, sûr pour V9 (R8 MD5 si nécessaire)

    n0 = cur.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0]
    print(f"Rows initial: {n0:,}")
    t_start = time.time()
    total = 0
    pass_n = 0
    last_checkpoint_at = 0
    while pass_n < args.max_passes:
        pass_n += 1
        t0 = time.time()
        try:
            cur.execute(
                "DELETE FROM principle_evaluations "
                "WHERE rowid IN ("
                "  SELECT rowid FROM principle_evaluations "
                "  WHERE created_at < ? LIMIT ?"
                ")",
                (cutoff, args.chunk),
            )
            n = cur.rowcount
        except sqlite3.DatabaseError as e:
            print(f"  [pass {pass_n}] FATAL: {e}", file=sys.stderr)
            # Essayer un checkpoint pour stabiliser
            try:
                cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                print("  [pass {pass_n}] Checkpoint post-erreur OK", file=sys.stderr)
            except Exception as e2:
                print(f"  [pass {pass_n}] Checkpoint failed: {e2}", file=sys.stderr)
            return 1
        if n == 0:
            print(f"  [pass {pass_n}] 0 row deleted — purge terminée")
            break
        total += n
        elapsed = time.time() - t0
        cumul = time.time() - t_start
        n_now = cur.execute(
            "SELECT COUNT(*) FROM principle_evaluations"
        ).fetchone()[0]
        # Force un checkpoint régulier
        if pass_n - last_checkpoint_at >= args.checkpoint_every:
            try:
                cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                last_checkpoint_at = pass_n
                checkpoint = "✓"
            except Exception:
                checkpoint = "✗"
        else:
            checkpoint = "·"
        print(
            f"  [pass {pass_n}] -{n:,} ({elapsed:.1f}s) "
            f"→ {n_now:,} | total: {total:,} | cumul: {cumul:.0f}s | wal: {checkpoint}",
            flush=True,
        )
        if n < args.chunk:
            break

    # Checkpoint final
    print("=== Checkpoint final ===")
    cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print("OK")

    n_post = cur.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0]
    span = cur.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM principle_evaluations"
    ).fetchone()
    print(f"\nRows post: {n_post:,}  (plage: {span[0]} → {span[1]})")
    conn.close()

    # VACUUM
    print(f"\n=== VACUUM (besoin ~{DB.stat().st_size/1024**3:.1f} Go, libre: {free_disk_gb(DB):.1f} Go) ===")
    for attempt in range(1, 121):
        try:
            vconn = sqlite3.connect(str(DB), isolation_level=None, timeout=10)
            vconn.execute("VACUUM")
            vconn.close()
            print(f"VACUUM OK en {time.time()-t_start:.0f}s")
            break
        except sqlite3.OperationalError as e:
            if "locked" in str(e) or "busy" in str(e).lower():
                if attempt % 10 == 0:
                    print(f"  retry {attempt}/120 ({str(e)[:50]})")
                time.sleep(2)
                continue
            print(f"VACUUM échec: {e}", file=sys.stderr)
            break
    else:
        print("VACUUM échec après 120 tentatives", file=sys.stderr)

    # Rapport
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "retention_days": args.days,
        "rows_initial": n0,
        "rows_deleted": total,
        "rows_post": n_post,
        "db_size_pre_gb": round(DB.stat().st_size / 1024**3, 3),
        "db_size_post_gb": round(DB.stat().st_size / 1024**3, 3),
        "free_disk_gb_post": round(free_disk_gb(DB), 2),
        "passes": pass_n,
    }
    REPORT.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nRapport: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
