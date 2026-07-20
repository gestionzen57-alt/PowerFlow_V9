"""v9_drop_batch_17jul.py — DROP contrôlé du batch catastrophe GBPUSD baissier.

Contexte (audit `PERF_PAPER_VS_DECISIONS_20260720.md` + motion CEO 2026-07-20) :
le 17/07 une boucle de ré-ouverture (idempotence défaillante, corrigée par le
Chantier 1 du 2026-07-20) a empilé des milliers de paper_trades GBPUSD baissier
clôturés à SL fixe → **3 690 trades baissier GBPUSD, WR ~1 %, -56 089 pips**,
qui tirent le WR global paper de ~92 % (sain) vers ~24 % (artefact). L'edge
baissier GBPUSD est structurellement négatif (V9_NO_BAISSIERE=1 +
V9_GBPUSD_LONG_ONLY=1 déjà actifs — aucun nouveau baissier GBPUSD ne sera créé).

Ce script DROP ces lignes de façon **auditée et réversible** :
  1. Vérifie le backup MD5 (R8) — `<backup>/md5_pre.txt` doit exister.
  2. Sauvegarde les lignes cibles AVANT suppression :
       - table in-DB `paper_trades_dropped_17jul_baissier` (CREATE ... AS SELECT) ;
       - dump JSON `<backup>/paper_trades_dropped.json`.
  3. DELETE en transaction unique (BEGIN IMMEDIATE ... COMMIT/ROLLBACK).
  4. Écrit un rapport `<backup>/drop_report.json` (métriques avant/après).

Sécurité :
  - Dry-run par DÉFAUT (aucune écriture). --apply pour exécuter.
  - --apply exige --backup <dir> contenant md5_pre.txt.
  - PAS de VACUUM (writer live actif — VACUUM exige un état quiescent).
  - Prédicat cible **fixe et explicite** : GBPUSD (snapshot_id LIKE 'v9-GBPUSD-%')
    ET direction='baissiere'. Les trades haussier GBPUSD (WR ~99 %, +8 767 pips)
    et toutes les autres paires sont PRÉSERVÉS.

Usage :
    python scripts/v9_drop_batch_17jul.py --dry-run
    python scripts/v9_drop_batch_17jul.py --apply --backup backups/drop_batch_20260720
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import sqlite3  # noqa: E402

from core.v9.config import DB_PATH  # noqa: E402

# Prédicat cible FIXE (le cœur du contrat d'audit). Ne pas paramétrer :
# toute variation du périmètre = nouvelle motion CEO + nouveau script.
TARGET_WHERE = "snapshot_id LIKE 'v9-GBPUSD-%' AND direction = 'baissiere'"
BACKUP_TABLE = "paper_trades_dropped_17jul_baissier"


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _verify_backup(backup_dir: Path) -> None:
    md5_file = backup_dir / "md5_pre.txt"
    if not md5_file.exists():
        raise FileNotFoundError(
            f"Backup MD5 introuvable : {md5_file}. "
            f"Génère d'abord un md5_pre.txt (R8) dans {backup_dir}."
        )
    lines = [
        ln for ln in md5_file.read_text(encoding="utf-8").splitlines()
        if ln and not ln.startswith("#")
    ]
    if not lines:
        raise ValueError(f"{md5_file} est vide — backup incomplet (aucun MD5).")


def _metrics(conn: sqlite3.Connection, where: str) -> dict:
    q = (
        f"SELECT COUNT(*), COALESCE(SUM(is_win), 0), "
        f"COALESCE(SUM(pips_simulated), 0), MIN(opened_at), MAX(opened_at), "
        f"SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) "
        f"FROM paper_trades WHERE {where}"
    )
    n, w, pips, mn, mx, opn = conn.execute(q).fetchone()
    wr = round((w or 0) * 100.0 / n, 2) if n else 0.0
    return {
        "n": n, "wins": w or 0, "wr_pct": wr,
        "pips_sum": round(pips or 0.0, 1),
        "date_min": mn, "date_max": mx, "open": opn,
    }


def _global_metrics(conn: sqlite3.Connection) -> dict:
    return _metrics(conn, "1=1")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--apply", action="store_true",
                        help="Applique réellement (défaut : dry-run).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Force le dry-run (équivalent à omettre --apply).")
    parser.add_argument("--backup", type=Path, default=None,
                        help="Dossier backup MD5 (OBLIGATOIRE avec --apply).")
    args = parser.parse_args(argv)

    db_path: Path = args.db
    dry_run = not args.apply

    if not dry_run:
        if not args.backup:
            print("ERREUR: --apply exige --backup <dir>.", file=sys.stderr)
            return 2
        try:
            _verify_backup(args.backup)
        except (FileNotFoundError, ValueError) as e:
            print(f"ERREUR backup: {e}", file=sys.stderr)
            return 2
        print(f"[OK ] Backup MD5 vérifié : {args.backup}/md5_pre.txt")

    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    try:
        target = _metrics(conn, TARGET_WHERE)
        g_before = _global_metrics(conn)
        print(f"[.. ] DB               : {db_path}")
        print(f"[.. ] Mode             : {'DRY-RUN' if dry_run else 'APPLY'}")
        print(f"[.. ] Prédicat cible   : {TARGET_WHERE}")
        print(f"[.. ] Cible            : n={target['n']} WR={target['wr_pct']}% "
              f"pips={target['pips_sum']} range=[{target['date_min']} .. {target['date_max']}]")
        print(f"[.. ] Global AVANT     : n={g_before['n']} WR={g_before['wr_pct']}% "
              f"pips={g_before['pips_sum']}")

        if target["n"] == 0:
            print("[.. ] Aucune ligne cible — rien à faire (DROP déjà effectué ?).")
            return 0

        if dry_run:
            g_after_est = {
                "n": g_before["n"] - target["n"],
                "pips_sum": round(g_before["pips_sum"] - target["pips_sum"], 1),
            }
            print(f"[.. ] Global APRÈS est.: n={g_after_est['n']} "
                  f"pips={g_after_est['pips_sum']}")
            print("\nAucun changement appliqué. Relancer avec --apply --backup <dir>.")
            return 0

        # === APPLY ===
        # 1. Dump JSON des lignes cibles (réversibilité hors-DB).
        rows = conn.execute(
            f"SELECT * FROM paper_trades WHERE {TARGET_WHERE}"
        ).fetchall()
        col_names = [d[0] for d in conn.execute(
            f"SELECT * FROM paper_trades WHERE {TARGET_WHERE} LIMIT 1"
        ).description]
        dump = [dict(zip(col_names, r)) for r in rows]
        dump_path = args.backup / "paper_trades_dropped.json"
        dump_path.write_text(
            json.dumps(dump, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[OK ] Dump JSON        : {dump_path} ({len(dump)} lignes)")

        # 2. Transaction : backup in-DB + DELETE.
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"DROP TABLE IF EXISTS {BACKUP_TABLE}")
            conn.execute(
                f"CREATE TABLE {BACKUP_TABLE} AS "
                f"SELECT * FROM paper_trades WHERE {TARGET_WHERE}"
            )
            n_backup = conn.execute(
                f"SELECT COUNT(*) FROM {BACKUP_TABLE}"
            ).fetchone()[0]
            if n_backup != target["n"]:
                raise RuntimeError(
                    f"backup in-DB {n_backup} != cible {target['n']} — ABORT"
                )
            deleted = conn.execute(
                f"DELETE FROM paper_trades WHERE {TARGET_WHERE}"
            ).rowcount
            if deleted != target["n"]:
                raise RuntimeError(
                    f"deleted {deleted} != cible {target['n']} — ROLLBACK"
                )
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            print(f"[ERR] DROP échoué, ROLLBACK : {e}", file=sys.stderr)
            return 4

        g_after = _global_metrics(conn)
        print(f"[OK ] Backup in-DB     : {BACKUP_TABLE} ({n_backup} lignes)")
        print(f"[OK ] DELETE           : {deleted} lignes supprimées")
        print(f"[OK ] Global APRÈS     : n={g_after['n']} WR={g_after['wr_pct']}% "
              f"pips={g_after['pips_sum']}")

        report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "db_path": str(db_path),
            "predicate": TARGET_WHERE,
            "backup_table": BACKUP_TABLE,
            "dump_json": str(dump_path),
            "target": target,
            "deleted": deleted,
            "global_before": g_before,
            "global_after": g_after,
        }
        report_path = args.backup / "drop_report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[OK ] Rapport JSON     : {report_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
