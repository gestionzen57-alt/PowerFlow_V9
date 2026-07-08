"""v9_db_hygiene.py — Maintenance périodique de la DB V9 (Phase 9.9).

Purge contrôlée des données `principle_evaluations` SHADOW et des
`decisions` "aucune_action" plus vieilles que N jours (défaut 7),
puis VACUUM pour récupérer l'espace disque. Ajoute également
l'index manquant `(symbol, timeframe, timestamp)` sur
`principle_evaluations` (le symétrique de `decisions`).

Suit la doctrine R8 du Phase 9.8 : lecture seule par défaut
(--dry-run par défaut), application explicite via --apply.
Backup MD5 préalable OBLIGATOIRE via `scripts/_db_md5_backup.py`
(CLI: --backup <dir>).

Usage:
    # Dry-run (lecture seule, n'écrit rien, ne purge rien)
    python scripts/v9_db_hygiene.py --dry-run

    # Application réelle (après backup MD5)
    python scripts/v9_db_hygiene.py --apply --backup backups/2026-07-08_pre_db_hygiene

    # Avec seuil custom (ex: 14 jours) + skip VACUUM
    python scripts/v9_db_hygiene.py --apply --days 14 --no-vacuum

Sécurité:
    - Dry-run par défaut (rien n'est modifié).
    - --apply exige --backup <dir> (le dossier doit contenir md5_pre.txt).
    - Transaction unique (BEGIN ... COMMIT/ROLLBACK) — en cas d'erreur,
      la DB est restaurée dans son état initial.
    - VACUUM n'est pas transactionnel (sqlite3 limitation) : effectué
      uniquement si la transaction COMMIT s'est bien déroulée.
    - Si le pipeline live écrit (port 31685 occupé), le script le détecte
      et ABORT sauf si --force (utile en cron, jamais en CLI manuelle).
"""

from __future__ import annotations

import argparse
import json
import socket
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402

CAPTURE_PORT = 31685  # v9_ops.py / capture_server
DEFAULT_RETENTION_DAYS = 7
# Colonnes de l'index manquant (déjà existant sur `decisions`,
# absent sur `principle_evaluations` — référencé par AUDIT_DB §8 R4).
MISSING_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_pe_symbol_timeframe_timestamp "
    "ON principle_evaluations (symbol, timeframe, timestamp)"
)


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _connect(db_path: Path) -> sqlite3.Connection:
    """Connexion lecture-écriture, pragmas alignés sur db_schema.get_connection
    sauf WAL désactivé en mode maintenance (incompatible avec VACUUM)."""
    if not db_path.exists():
        raise FileNotFoundError(f"DB introuvable : {db_path}")
    conn = sqlite3.connect(str(db_path), timeout=60)
    # PAS de PRAGMA journal_mode=WAL ici : VACUUM exige un état quiescent.
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Teste si le port de capture_server est ouvert (= pipeline live actif)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cutoff_iso(days: int) -> str:
    """Timestamp ISO8601 (Z) à `days` jours dans le passé. Format utilisé
    par toutes les colonnes timestamp V9 (YYYY-MM-DDTHH:MM:SS.ffffff+00:00)."""
    return (_now_utc() - timedelta(days=days)).isoformat()


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Décompte par table — base du rapport dry-run."""
    tables = [
        "principle_evaluations", "decisions", "regime_snapshots",
        "zone_diagnostics", "signals", "forces_snapshots",
        "scenes", "behaviors", "windows", "exploitability",
    ]
    out: dict[str, int] = {}
    for t in tables:
        try:
            out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            out[t] = -1  # table absente (cas tests partiels)
    return out


def _db_size_mb(db_path: Path) -> float:
    return db_path.stat().st_size / (1024 * 1024)


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _count_to_purge(conn: sqlite3.Connection, retention_days: int) -> dict:
    """Calcule (sans rien supprimer) combien de lignes seraient purgées
    et la taille approximative récupérée (estimation grossière :
    ~400 bytes/ligne pour principle_evaluations, ~300 pour decisions)."""
    cutoff = _cutoff_iso(retention_days)
    pe_shadow = conn.execute(
        "SELECT COUNT(*) FROM principle_evaluations "
        "WHERE v9_status='SHADOW' AND timestamp < ?",
        (cutoff,),
    ).fetchone()[0]
    pe_active_old = conn.execute(
        "SELECT COUNT(*) FROM principle_evaluations "
        "WHERE v9_status='ACTIVE' AND timestamp < ?",
        (cutoff,),
    ).fetchone()[0]
    dec_noop_old = conn.execute(
        "SELECT COUNT(*) FROM decisions "
        "WHERE action='aucune_action' AND timestamp < ?",
        (cutoff,),
    ).fetchone()[0]
    dec_other_old = conn.execute(
        "SELECT COUNT(*) FROM decisions "
        "WHERE (action<>'aucune_action' OR action IS NULL) AND timestamp < ?",
        (cutoff,),
    ).fetchone()[0]
    return {
        "retention_days": retention_days,
        "cutoff_utc": cutoff,
        "principle_evaluations_shadow_old": pe_shadow,
        "principle_evaluations_active_old": pe_active_old,
        "decisions_ancienne_action_old": dec_noop_old,
        "decisions_autres_old": dec_other_old,
        # Estimations : 400 B/eval (moyenne 6 colonnes remplies + context_json),
        # 300 B/decision (5 colonnes JSON). Très approximatif, sert d'ordre
        # de grandeur au rapport, jamais d'invariant.
        "est_mb_recovered": round(
            (pe_shadow * 400 + dec_noop_old * 300) / (1024 * 1024), 1
        ),
    }


def _verify_backup(backup_dir: Path) -> None:
    """Vérifie que le dossier backup contient md5_pre.txt non vide.
    Le nom de la DB peut être custom (--db en CLI ou en test), donc on
    vérifie seulement la présence d'au moins une ligne MD5, pas le nom
    exact de la DB."""
    md5_file = backup_dir / "md5_pre.txt"
    if not md5_file.exists():
        raise FileNotFoundError(
            f"Backup MD5 introuvable : {md5_file}. "
            f"Lance d'abord : python scripts/_db_md5_backup.py {backup_dir}"
        )
    md5_lines = [
        line for line in md5_file.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    if not md5_lines:
        raise ValueError(
            f"{md5_file} est vide — backup incomplet (aucun MD5)."
        )


def _run_purge(
    conn: sqlite3.Connection,
    retention_days: int,
) -> dict:
    """Effectue la purge en transaction. Retourne les compteurs réels
    (peuvent différer du dry-run si la DB bouge entre les deux)."""
    cutoff = _cutoff_iso(retention_days)
    deleted_pe_shadow = conn.execute(
        "DELETE FROM principle_evaluations "
        "WHERE v9_status='SHADOW' AND timestamp < ?",
        (cutoff,),
    ).rowcount
    deleted_dec_noop = conn.execute(
        "DELETE FROM decisions "
        "WHERE action='aucune_action' AND timestamp < ?",
        (cutoff,),
    ).rowcount
    return {
        "deleted_principle_evaluations_shadow": deleted_pe_shadow,
        "deleted_decisions_ancienne_action": deleted_dec_noop,
        "cutoff_utc": cutoff,
    }


def _run_add_index(conn: sqlite3.Connection) -> dict:
    """Ajoute l'index (symbol, timeframe, timestamp) sur
    principle_evaluations si absent. Idempotent."""
    name = "idx_pe_symbol_timeframe_timestamp"
    if _index_exists(conn, name):
        return {"index": name, "status": "already_exists"}
    conn.execute(MISSING_INDEX_SQL)
    return {"index": name, "status": "created"}


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Maintenance DB V9 (purge + index + VACUUM)."
    )
    parser.add_argument(
        "--db", type=Path, default=DB_PATH,
        help=f"Chemin DB (défaut: {DB_PATH})",
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_RETENTION_DAYS,
        help=f"Rétention en jours (défaut: {DEFAULT_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Applique réellement (sinon dry-run par DÉFAUT — sécurité).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Force le mode dry-run (équivalent à omettre --apply). "
             "Utile pour les scripts CLI/cron qui veulent expliciter.",
    )
    parser.add_argument(
        "--backup", type=Path, default=None,
        help="Dossier backup MD5 (OBLIGATOIRE avec --apply).",
    )
    parser.add_argument(
        "--no-vacuum", action="store_true",
        help="Skip VACUUM (utile si espace disque contraint).",
    )
    parser.add_argument(
        "--no-index", action="store_true",
        help="Skip création index manquant.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Ignore l'avertissement pipeline live (réservé cron).",
    )
    args = parser.parse_args(argv)

    db_path: Path = args.db
    dry_run = not args.apply

    if not dry_run:
        if not args.backup:
            print("ERREUR: --apply exige --backup <dir> (voir --help).", file=sys.stderr)
            return 2
        try:
            _verify_backup(args.backup)
        except (FileNotFoundError, ValueError) as e:
            print(f"ERREUR backup: {e}", file=sys.stderr)
            return 2
        print(f"[OK ] Backup MD5 vérifié : {args.backup}/md5_pre.txt")

    if not args.force and _port_in_use(CAPTURE_PORT):
        print(
            f"[WARN] Port {CAPTURE_PORT} occupé (capture_server actif). "
            f"Risque d'incohérence VACUUM. Utilisez --force ou arrêtez "
            f"le pipeline d'abord (python scripts/v9_ops.py stop).",
            file=sys.stderr,
        )
        if not dry_run:
            return 3

    print(f"[.. ] DB cible        : {db_path}")
    print(f"[.. ] Mode            : {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"[.. ] Rétention       : {args.days} jours")
    print(f"[.. ] VACUUM          : {'off' if args.no_vacuum else 'on'}")
    print(f"[.. ] Index           : {'off' if args.no_index else 'on'}")

    conn = _connect(db_path)
    try:
        size_before_mb = _db_size_mb(db_path)
        counts_before = _table_counts(conn)
        purge_plan = _count_to_purge(conn, args.days)
        print(f"[.. ] DB size (avant): {size_before_mb:.1f} MB")

        if dry_run:
            print("\n=== DRY-RUN — plan de purge ===")
            for k, v in purge_plan.items():
                print(f"  {k}: {v}")
            print(f"\n  index cible        : "
                  f"{'absent' if not _index_exists(conn, 'idx_pe_symbol_timeframe_timestamp') else 'présent'}")
            print(f"\nAucun changement appliqué. Relancer avec --apply pour exécuter.")
            return 0

        # === APPLY ===
        print("\n[>> ] Démarrage transaction de purge…")
        try:
            conn.execute("BEGIN IMMEDIATE")
            purge_result = _run_purge(conn, args.days)
            index_result = (
                _run_add_index(conn) if not args.no_index
                else {"index": "skipped", "status": "skipped"}
            )
            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            print(f"[ERR] Purge échouée, ROLLBACK effectué : {e}", file=sys.stderr)
            return 4

        print(f"[OK ] Purge COMMIT    : {purge_result}")
        print(f"[OK ] Index            : {index_result}")

        vacuum_result: dict = {"status": "skipped"}
        if not args.no_vacuum:
            print("[>> ] VACUUM en cours (peut prendre plusieurs minutes sur 3+ GB)…")
            try:
                conn.execute("VACUUM")
                vacuum_result = {"status": "ok"}
            except Exception as e:
                vacuum_result = {"status": "error", "error": str(e)}
                print(f"[WARN] VACUUM échoué : {e}", file=sys.stderr)
        size_after_mb = _db_size_mb(db_path)
        counts_after = _table_counts(conn)
        report = {
            "timestamp_utc": _now_utc().isoformat(),
            "db_path": str(db_path),
            "retention_days": args.days,
            "size_mb_before": round(size_before_mb, 1),
            "size_mb_after": round(size_after_mb, 1),
            "size_mb_recovered": round(size_before_mb - size_after_mb, 1),
            "counts_before": counts_before,
            "counts_after": counts_after,
            "purge": purge_result,
            "index": index_result,
            "vacuum": vacuum_result,
        }
        report_path = (
            Path("docs/calibration/backups") / args.backup.name / "hygiene_report.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\n[OK ] Rapport JSON    : {report_path}")
        print(f"[OK ] DB size (après) : {size_after_mb:.1f} MB "
              f"(récupéré {size_before_mb - size_after_mb:+.1f} MB)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
