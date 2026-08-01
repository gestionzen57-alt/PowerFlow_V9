"""v9_backup_strategy.py — Phase 86 motion CEO 48H (post-Plan C).

Backup strategy automatisee : daily / weekly / monthly rotation.
MD5 integrity check + cleanup old backups.

Auteur : Hermes (Phase 86 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import datetime
import enum
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger("v9.backup")


class RotationStrategy(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


DEFAULT_RETENTION = {
    "daily": 7,    # garder 7 daily
    "weekly": 4,   # garder 4 weekly
    "monthly": 12, # garder 12 monthly
}


def compute_md5(data: bytes) -> str:
    """MD5 d'un contenu binaire."""
    return hashlib.md5(data).hexdigest()


def format_backup_filename(db_name: str, strategy: str) -> str:
    """Format : <db_name>_<strategy>_<YYYYMMDD>.db"""
    stem = Path(db_name).stem
    today = datetime.date.today().strftime("%Y%m%d")
    return f"{stem}_{strategy}_{today}.db"


def list_existing_backups(backup_dir: Path) -> list[Path]:
    """Liste tous les backups dans le repertoire, tries par date desc."""
    if not backup_dir.exists():
        return []
    backups = []
    for f in backup_dir.glob("*.db"):
        # On accepte tout .db comme backup (tri par mtime)
        backups.append(f)
    backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return backups


def cleanup_old_backups(backup_dir: Path, keep: int) -> int:
    """Supprime les vieux backups au-dela de `keep`. Retourne le nombre supprimes."""
    backups = list_existing_backups(backup_dir)
    if len(backups) <= keep:
        return 0
    to_delete = backups[keep:]
    deleted = 0
    for b in to_delete:
        try:
            b.unlink()
            deleted += 1
        except Exception as exc:
            log.warning("cleanup: failed to delete %s: %s", b, exc)
    return deleted


def compute_next_rotation(strategy: str, current: datetime.datetime) -> datetime.datetime:
    """Prochaine rotation selon strategy."""
    if strategy == "daily":
        return current + datetime.timedelta(days=1)
    if strategy == "weekly":
        return current + datetime.timedelta(weeks=1)
    if strategy == "monthth":
        return current  # fallback (typo guard)
    # monthly
    if current.month == 12:
        return current.replace(year=current.year + 1, month=1)
    return current.replace(month=current.month + 1)


def verify_backup_integrity(
    backup_path: Path, expected_md5: str,
) -> tuple[bool, str]:
    """Verifie MD5 d'un backup. Retourne (ok, actual_md5)."""
    try:
        data = backup_path.read_bytes()
        actual = compute_md5(data)
        return actual == expected_md5, actual
    except Exception as exc:
        log.warning("verify_backup_integrity failed: %s", exc)
        return False, ""


def rotate_backup(db_path: Path, backup_dir: Path) -> bool:
    """Effectue la rotation : copie le DB vers backup_dir."""
    if not db_path.exists():
        return False
    backup_dir.mkdir(parents=True, exist_ok=True)
    fn = format_backup_filename(db_path.name, "daily")
    target = backup_dir / fn
    try:
        shutil.copy2(db_path, target)
        # Sauvegarder le MD5 dans un fichier sidecar
        md5 = compute_md5(db_path.read_bytes())
        target.with_suffix(".md5").write_text(md5)
        return True
    except Exception as exc:
        log.warning("rotate_backup failed: %s", exc)
        return False


def main(argv=None) -> int:
    """Demo backup strategy."""
    import argparse
    parser = argparse.ArgumentParser(description="V9 backup strategy")
    parser.add_argument("--db", default="./data/v9_forces.db")
    parser.add_argument("--backup-dir", default="./backups")
    parser.add_argument("--keep-daily", type=int, default=DEFAULT_RETENTION["daily"])
    args = parser.parse_args(argv)
    print("=" * 70)
    print("V9 BACKUP STRATEGY (Phase 86)")
    print("=" * 70)
    db = Path(args.db)
    backup_dir = Path(args.backup_dir)
    print(f"DB           : {db}")
    print(f"Backup dir   : {backup_dir}")
    print(f"DB exists    : {db.exists()}")
    if db.exists():
        ok = rotate_backup(db, backup_dir)
        print(f"Rotate       : {ok}")
        deleted = cleanup_old_backups(backup_dir, keep=args.keep_daily)
        print(f"Cleaned up   : {deleted} old backups")
        n = len(list_existing_backups(backup_dir))
        print(f"Total kept   : {n}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())