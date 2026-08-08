"""apply_migrations.py — Runner de migrations SQL auto S24
Plateforme : Windows (SQLite)
Auteur : PowerFlow Senior Audit — 2026-08-08

Scan tous les fichiers .sql dans scripts/ et les applique si non encore exécutés.
Tracking via table _migrations dans la DB.

Usage :
  python scripts/apply_migrations.py              # dry-run (affiche les SQL à appliquer)
  python scripts/apply_migrations.py --apply      # applique réellement
  python scripts/apply_migrations.py --status     # affiche l'état des migrations
"""

import argparse
import sqlite3
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("POWERFLOW_DB", "data/powerflow_v10.db"))
SCRIPTS_DIR = Path("scripts")
LOG_PATH = Path("logs/migrations.log")


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ensure_migrations_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)
    conn.commit()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def get_applied(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT filename FROM _migrations").fetchall()
    return {r[0] for r in rows}


def find_sql_files() -> list[Path]:
    files = sorted(SCRIPTS_DIR.glob("*.sql"))
    return files


def apply_migration(conn: sqlite3.Connection, path: Path, dry_run: bool) -> bool:
    sql = path.read_text(encoding="utf-8")
    sha = sha256_file(path)
    if dry_run:
        log(f"[DRY-RUN] Appliquerait : {path.name} (SHA256: {sha[:16]}...)")
        print(f"--- SQL preview ({path.name}) ---")
        print(sql[:500])
        print("---")
        return True
    try:
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO _migrations (filename, sha256, applied_at) VALUES (?,?,?)",
            (path.name, sha, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        log(f"[APPLIED] {path.name} — OK")
        return True
    except Exception as e:
        log(f"[ERROR] {path.name} — {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Migration runner SQL — PowerFlow V10")
    parser.add_argument("--apply", action="store_true", help="Applique les migrations (défaut: dry-run)")
    parser.add_argument("--status", action="store_true", help="Affiche l'état des migrations")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    ensure_migrations_table(conn)

    if args.status:
        applied = get_applied(conn)
        all_sql = find_sql_files()
        log(f"=== STATUS MIGRATIONS ({len(all_sql)} fichiers SQL trouvés) ===")
        for f in all_sql:
            state = "✅ APPLIQUÉ" if f.name in applied else "⏳ EN ATTENTE"
            print(f"  {state}  {f.name}")
        conn.close()
        return 0

    dry_run = not args.apply
    sql_files = find_sql_files()
    applied = get_applied(conn)
    pending = [f for f in sql_files if f.name not in applied]

    if not pending:
        log("Toutes les migrations sont déjà appliquées.")
        conn.close()
        return 0

    mode = "DRY-RUN" if dry_run else "APPLY"
    log(f"=== apply_migrations START mode={mode} — {len(pending)} fichier(s) à traiter ===")
    ok = 0
    for path in pending:
        if apply_migration(conn, path, dry_run):
            ok += 1
    log(f"=== apply_migrations END — {ok}/{len(pending)} migrations traitées ===")
    conn.close()
    return 0 if ok == len(pending) else 1


if __name__ == "__main__":
    sys.exit(main())
