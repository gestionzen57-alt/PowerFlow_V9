#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v9_dedup_paper_trades.py — Suppression des paper_trades fantômes (P0 idempotence).

Contexte (incident 2026-07-17 catastrophe baissière) :
Le bug d'idempotence `post_decision_hook` (commit c47dc68 l'a fixé en code)
a laissé 1001 paper_trades fantômes dans la DB. Tous WIN par construction
(boucle re-entry sur même snapshot_id+direction). Le bilan comptable
est gonflé : 1179 trades affichés, mais seulement 178 légitimes.

Impact :
  - paper_trades WR affiché 95.5% (gonflé) → réel ~69.1% sur trades uniques
  - paper_trades pips_sum +8618 (faux) → réel +234 pips
  - watchdog lit paper_trades pour certaines métriques → verdicts pollués

Doctrine :
- R2 additif : script séparé, ne modifie aucun core/v9/*
- R6 défensif : dry-run par défaut, MD5 backup obligatoire pour --apply
- R18 : pure SQL + stdlib
- Idempotent : peut tourner plusieurs fois sans effet (déjà dédupliqué → noop)

Usage :
    python scripts/v9_dedup_paper_trades.py --dry-run
        # Affiche ce qui serait supprimé sans toucher

    python scripts/v9_dedup_paper_trades.py --apply --backup backups/dedup_paper_trades_20260720
        # MD5 vérifié + DELETE en transaction + rapport JSON

    python scripts/v9_dedup_paper_trades.py --archive-only --backup backups/dedup_paper_trades_20260720
        # Archive les fantômes dans paper_trades_fantomes_archive.db sans DELETE

Critère de "légitime" : pour chaque (snapshot_id, direction), on garde
le trade avec le MIN(opened_at). Les autres sont fantômes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "v9_forces.db"


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_backup(backup_dir: Path, db_path: Path, skip: bool = False) -> None:
    """Vérifie le MD5 du backup avant apply.

    Si skip=True (cas DB live qui écrit en continu via WAL), on accepte
    un delta mineur entre le moment du MD5 et l'apply. Le dry-run doit
    avoir été fait avant ; l'archive fantômes doit exister.
    """
    if skip:
        return
    md5_file = backup_dir / "md5_pre.txt"
    if not md5_file.exists():
        raise FileNotFoundError(f"md5_pre.txt absent dans {backup_dir}")
    expected = None
    for line in md5_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        h, name = line.split(maxsplit=1)
        if name.lstrip("*") == db_path.name:
            expected = h
            break
    if expected is None:
        raise ValueError(f"MD5 pour {db_path.name} absent de {md5_file}")
    actual = _md5_file(db_path)
    if actual != expected:
        raise ValueError(
            f"MD5 mismatch : DB actuelle {actual[:12]}... != backup {expected[:12]}...\n"
            f"Refais un backup ou passe un autre --backup."
        )


def analyze(db_path: Path) -> dict:
    """Calcule ce qui serait supprimé (lecture seule)."""
    con = sqlite3.connect(str(db_path))
    try:
        r_total = con.execute(
            "SELECT COUNT(*) FROM paper_trades"
        ).fetchone()[0]
        r_unique = con.execute(
            "SELECT COUNT(*) FROM ("
            "SELECT DISTINCT snapshot_id || '|' || direction FROM paper_trades"
            ")"
        ).fetchone()[0]
        r_dup = r_total - r_unique

        # Fantômes : tous sauf MIN(opened_at) par (snapshot_id, direction)
        # Approche portable : sous-requête corrélée (les versions récentes de
        # SQLite supportent MIN(...) OVER mais pour la perf et la portabilité
        # on utilise NOT EXISTS).
        r_phantoms = con.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END),
                   ROUND(SUM(COALESCE(pips_simulated, 0)), 1)
            FROM paper_trades pt
            WHERE EXISTS (
                SELECT 1 FROM paper_trades pt2
                WHERE pt2.snapshot_id = pt.snapshot_id
                  AND pt2.direction = pt.direction
                  AND pt2.opened_at < pt.opened_at
            )
        """).fetchone()
        r_legit = con.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END),
                   ROUND(SUM(COALESCE(pips_simulated, 0)), 1)
            FROM paper_trades pt
            WHERE NOT EXISTS (
                SELECT 1 FROM paper_trades pt2
                WHERE pt2.snapshot_id = pt.snapshot_id
                  AND pt2.direction = pt.direction
                  AND pt2.opened_at < pt.opened_at
            )
        """).fetchone()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "db_path": str(db_path),
            "total": r_total,
            "unique_pairs": r_unique,
            "duplicates_total": r_dup,
            "phantoms": {
                "n": r_phantoms[0] or 0,
                "wins": r_phantoms[1] or 0,
                "pips": r_phantoms[2] or 0.0,
            },
            "legitimes": {
                "n": r_legit[0] or 0,
                "wins": r_legit[1] or 0,
                "pips": r_legit[2] or 0.0,
            },
        }
    finally:
        con.close()


def archive_phantoms(db_path: Path, archive_dir: Path) -> int:
    """Archive les fantômes dans paper_trades_fantomes_archive.db. Idempotent."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_db = archive_dir / "paper_trades_fantomes_archive.db"
    con_src = sqlite3.connect(str(db_path))
    con_dst = sqlite3.connect(str(archive_db))
    try:
        con_dst.execute(
            "CREATE TABLE IF NOT EXISTS paper_trades_fantomes ("
            "trade_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT, "
            "confiance INTEGER, opened_at TEXT, closed_at TEXT, "
            "pips_simulated REAL, is_win INTEGER, "
            "principes_source TEXT, risk_go_context TEXT)"
        )
        # Copie via ATTACH pour éviter de tout charger en mémoire
        con_dst.execute("ATTACH DATABASE ? AS src", (str(db_path),))
        # INSERT OR IGNORE pour idempotence
        before = con_dst.execute(
            "SELECT COUNT(*) FROM paper_trades_fantomes"
        ).fetchone()[0]
        con_dst.execute("""
            INSERT OR IGNORE INTO paper_trades_fantomes
            SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.confiance,
                   pt.opened_at, pt.closed_at, pt.pips_simulated, pt.is_win,
                   pt.principes_source, pt.risk_go_context
            FROM src.paper_trades pt
            WHERE EXISTS (
                SELECT 1 FROM src.paper_trades pt2
                WHERE pt2.snapshot_id = pt.snapshot_id
                  AND pt2.direction = pt.direction
                  AND pt2.opened_at < pt.opened_at
            )
        """)
        con_dst.commit()
        con_dst.execute("DETACH DATABASE src")
        after = con_dst.execute(
            "SELECT COUNT(*) FROM paper_trades_fantomes"
        ).fetchone()[0]
        return after - before
    finally:
        con_src.close()
        con_dst.close()


def apply_dedup(db_path: Path, archive_dir: Path) -> dict:
    """Supprime les fantômes en transaction après MD5 vérifié."""
    archive_phantoms(db_path, archive_dir)
    con = sqlite3.connect(str(db_path))
    try:
        before = con.execute(
            "SELECT COUNT(*) FROM paper_trades"
        ).fetchone()[0]
        con.execute("BEGIN IMMEDIATE")
        con.execute("""
            DELETE FROM paper_trades
            WHERE EXISTS (
                SELECT 1 FROM paper_trades pt2
                WHERE pt2.snapshot_id = paper_trades.snapshot_id
                  AND pt2.direction = paper_trades.direction
                  AND pt2.opened_at < paper_trades.opened_at
            )
        """)
        after = con.execute(
            "SELECT COUNT(*) FROM paper_trades"
        ).fetchone()[0]
        # Stats post-dedup
        r = con.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END),
                   ROUND(SUM(COALESCE(pips_simulated, 0)), 1)
            FROM paper_trades
        """).fetchone()
        con.execute("COMMIT")
        return {
            "deleted": before - after,
            "before_total": before,
            "after_total": after,
            "after_wins": r[1] or 0,
            "after_pips": r[2] or 0.0,
            "after_wr_pct": round(100 * (r[1] or 0) / max(1, r[0]), 2),
        }
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dedup paper_trades fantômes (P0)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--archive-only", action="store_true")
    parser.add_argument("--backup", type=Path, default=None,
                        help="Dossier backup MD5 (obligatoire pour --apply)")
    parser.add_argument("--skip-md5-check", action="store_true",
                        help="Skip MD5 check (DB live qui écrit via WAL)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.apply and not args.archive_only:
        args.dry_run = True

    if args.apply and not args.backup:
        print("--apply exige --backup <dir> (avec md5_pre.txt)", file=sys.stderr)
        return 2

    if args.apply:
        # Si --skip-md5-check, exiger que l'archive fantômes existe
        # (rollback possible si DELETE foire).
        if args.skip_md5_check:
            archive_check = (args.backup /
                             "paper_trades_fantomes_archive.db")
            if not archive_check.exists():
                print(
                    f"[FATAL] --skip-md5-check exige {archive_check} "
                    f"(rollback impossible sans archive). "
                    f"Lance d'abord : --archive-only",
                    file=sys.stderr,
                )
                return 2
            print(f"[WARN] --skip-md5-check : MD5 non vérifié. "
                  f"Archive présente : {archive_check}")

        try:
            _verify_backup(args.backup, args.db, skip=args.skip_md5_check)
            print(f"[OK ] Backup MD5 vérifié : {args.backup}/md5_pre.txt"
                  + (" (skip)" if args.skip_md5_check else ""))
        except (FileNotFoundError, ValueError) as e:
            print(f"[FATAL] {e}", file=sys.stderr)
            return 2

    if args.archive_only or args.apply:
        archive_dir = args.backup if args.backup else Path(
            r"C:\projet\V9\backups\dedup_paper_trades_20260720"
        )
        n_arch = archive_phantoms(args.db, archive_dir)
        print(f"[OK ] {n_arch} fantômes archivés dans {archive_dir}/paper_trades_fantomes_archive.db")

    if args.apply:
        result = apply_dedup(args.db, args.backup)
        print(f"[OK ] Dedup appliqué : {result['deleted']} trades supprimés")
        print(f"      {result['before_total']} → {result['after_total']} trades")
        print(f"      P&L post : {result['after_pips']:+.1f} pips, "
              f"WR {result['after_wr_pct']}%")
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    # dry-run
    stats = analyze(args.db)
    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0

    print("=== ANALYSE PAPER_TRADES FANTÔMES (dry-run) ===")
    print(f"  Total trades : {stats['total']}")
    print(f"  Paires uniques (snapshot+direction) : {stats['unique_pairs']}")
    print(f"  Doublons totaux : {stats['duplicates_total']}")
    print(f"  Fantômes à supprimer : {stats['phantoms']['n']}")
    print(f"    - wins fantômes : {stats['phantoms']['wins']}")
    print(f"    - pips fantômes : {stats['phantoms']['pips']:+.1f}")
    print(f"  Légitimes à conserver : {stats['legitimes']['n']}")
    print(f"    - wins légitimes : {stats['legitimes']['wins']}")
    print(f"    - pips légitimes : {stats['legitimes']['pips']:+.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
