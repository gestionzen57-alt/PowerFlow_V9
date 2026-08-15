#!/usr/bin/env python3
"""
v9_purge_principle_evaluations.py — Rétention + VACUUM principle_evaluations

CEO motion 2026-08-15 (weekend 48h, marché fermé) :
- Purge principle_evaluations > 30 jours (calibration + replay-friendly)
- VACUUM pour rendre l'espace au FS (freelist_count=0 sans purge = DB ne rétrécit pas)
- Mesure pré/post pour traçabilité R8

Usage:
    python scripts/v9_purge_principle_evaluations.py [--dry-run] [--days N]

Doctrine:
- R6 — pas de simulation, mesure pré/post effective (counts + size)
- R7 — motion CEO documentée, exécution tracée
- R8 — MD5 défensif posé avant toute modification (data/v9_forces.md5)
- R22 — 1 DECISIONS_LOG append-only par session

Pièges connus (cf. skill v9-db-drainage-recovery):
- VACUUM sur DB live peut échouer si writers actifs. Toujours arrêter writers d'abord.
- VACUUM nécessite ~taille DB en espace libre (Étape F : si < 8 Go libre → flux direct).
- Ne JAMAIS supprimer data/v9_forces.db même après VACUUM (preuve forensics + rollback).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "v9_forces.db"
REPORT = REPO / "reports" / "v9_purge_principle_evaluations.json"


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def free_disk_gb(path: Path) -> float:
    import shutil
    return shutil.disk_usage(str(path)).free / (1024 ** 3)


def measure(conn: sqlite3.Connection) -> dict:
    """Mesure counts + distrib status + indexes (rapide, lit sqlite_master)."""
    cur = conn.cursor()
    counts = {}
    for t in ("principle_evaluations", "principles", "decisions",
              "forces_snapshots", "regime_snapshots", "zone_diagnostics",
              "paper_trades", "signals"):
        try:
            counts[t] = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        except sqlite3.OperationalError:
            counts[t] = None
    # Distribution v9_status
    dist = {}
    try:
        for s, n in cur.execute(
            "SELECT v9_status, COUNT(*) FROM principle_evaluations GROUP BY v9_status"
        ).fetchall():
            dist[s] = n
    except sqlite3.OperationalError:
        pass
    # Plage temporelle
    span = cur.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM principle_evaluations"
    ).fetchone()
    return {"counts": counts, "v9_status_dist": dist,
            "min_created": span[0], "max_created": span[1]}


def purge_older_than(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    """DELETE rows older than cutoff. Returns rowcount deleted."""
    cur = conn.cursor()
    cur.execute("DELETE FROM principle_evaluations WHERE created_at < ?", (cutoff_iso,))
    return cur.rowcount


def vacuum_db(db_path: Path) -> None:
    """VACUUM — reconstruit la DB, rend les pages libres au FS."""
    # VACUUM ne peut pas tourner dans une transaction, isolation_level=None
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Mesure sans purge ni VACUUM")
    ap.add_argument("--days", type=int, default=30, help="Rétention en jours (défaut 30)")
    ap.add_argument("--skip-vacuum", action="store_true", help="Skip VACUUM (debug)")
    ap.add_argument("--no-md5", action="store_true", help="Skip MD5 (MD5 déjà posé)")
    args = ap.parse_args()

    if not DB.exists():
        print(f"DB absente: {DB}", file=sys.stderr)
        return 2

    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    print(f"=== Purge principle_evaluations > {args.days}j (cutoff={cutoff}) ===")
    print(f"DB: {DB}")
    print(f"DB size: {DB.stat().st_size / 1024**3:.2f} Go")
    print(f"Free disk: {free_disk_gb(DB):.2f} Go")

    # MD5 défensif (R8)
    if not args.no_md5:
        print("=== MD5 pré-purge ===")
        md5_pre = md5_of(DB)
        md5_path = REPO / "data" / "v9_forces.md5.purge_pre"
        md5_path.write_text(f"{md5_pre}  {DB.name}\n")
        print(f"MD5 pré: {md5_pre} (saved to {md5_path})")

    # Mesure pré
    print("\n=== Mesure pré-purge ===")
    conn = sqlite3.connect(str(DB), isolation_level=None, timeout=300)
    pre = measure(conn)
    print(f"principle_evaluations: {pre['counts']['principle_evaluations']:,}")
    print(f"plage: {pre['min_created']} → {pre['max_created']}")
    print(f"distribution v9_status: {pre['v9_status_dist']}")

    if args.dry_run:
        # Estimation rows à purger
        n_to_purge = conn.execute(
            "SELECT COUNT(*) FROM principle_evaluations WHERE created_at < ?",
            (cutoff,),
        ).fetchone()[0]
        print(f"\n[DRY-RUN] rows à purger: {n_to_purge:,}")
        conn.close()
        return 0

    # Purge
    print(f"\n=== Purge rows < {cutoff} ===")
    t0 = time.time()
    n_deleted = purge_older_than(conn, cutoff)
    print(f"Rows purgées: {n_deleted:,} en {time.time()-t0:.1f}s")
    conn.commit()

    # Mesure post-purge
    post = measure(conn)
    print(f"principle_evaluations post-purge: {post['counts']['principle_evaluations']:,}")
    conn.close()

    # VACUUM (sauf si skip)
    if not args.skip_vacuum:
        # Pré-check espace libre (VACUUM = taille DB en pic)
        needed = DB.stat().st_size / 1024**3
        free = free_disk_gb(DB)
        print(f"\n=== VACUUM (besoin ~{needed:.1f} Go, libre: {free:.1f} Go) ===")
        if free < needed * 0.5:
            print(f"!! WARNING: espace libre < 50% de la DB. VACUUM peut échouer.")
        t0 = time.time()
        vacuum_db(DB)
        print(f"VACUUM terminé en {time.time()-t0:.1f}s")
        print(f"DB size post-VACUUM: {DB.stat().st_size / 1024**3:.2f} Go")
    else:
        print("\n[skip] VACUUM non exécuté (--skip-vacuum)")

    # MD5 post
    if not args.no_md5:
        print("\n=== MD5 post-purge ===")
        md5_post = md5_of(DB)
        md5_path_post = REPO / "data" / "v9_forces.md5.purge_post"
        md5_path_post.write_text(f"{md5_post}  {DB.name}\n")
        print(f"MD5 post: {md5_post} (saved to {md5_path_post})")

    # Rapport
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "retention_days": args.days,
        "cutoff": cutoff,
        "rows_deleted": n_deleted,
        "pre": {
            "db_size_gb": round(DB.stat().st_size / 1024**3, 3),
            **pre,
        },
        "post": {
            "db_size_gb": round(DB.stat().st_size / 1024**3, 3),
            **post,
        },
        "free_disk_gb_post": round(free_disk_gb(DB), 2),
    }
    if not args.no_md5:
        report["md5_pre"] = md5_pre
        report["md5_post"] = md5_post

    REPORT.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nRapport: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
