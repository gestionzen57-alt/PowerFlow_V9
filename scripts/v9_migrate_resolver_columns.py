"""v9_migrate_resolver_columns.py — Migration R2 additif colonnes resolver (motion #11).

Contexte (motion CEO #11, 2026-07-20) : le PaperTradeResolver ACTIVE est livré
(motion #7) mais pas branché dans le pipeline. Pour le brancher sans casser
le résultat ExitSimulator actuel (qui reste souverain, R25'), on stocke
le résultat resolver dans 2 colonnes dédiées :
  - pips_simulated_resolver : le pips que le resolver ACTIVE aurait calculé
  - exit_reason_resolver    : la raison de sortie ('tp', 'sl', 'horizon', etc.)

Ces colonnes sont optionnelles (NULL par défaut). R6 : migration idempotente
(check IF NOT EXISTS), ne lève jamais, rollback par DROP COLUMN possible.

Doctrine :
- R2 additif : nouvelles colonnes NULL, aucun comportement existant cassé
- R6 défensif : try/except, idempotente
- R18 : pure SQL + stdlib

Usage :
    python scripts/v9_migrate_resolver_columns.py --dry-run
    python scripts/v9_migrate_resolver_columns.py --apply
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "v9_forces.db"


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def migrate(db_path: Path, dry_run: bool = True) -> dict:
    """Ajoute pips_simulated_resolver + exit_reason_resolver si absents."""
    result = {
        "added_columns": [],
        "skipped_existing": [],
        "errors": [],
    }
    con = sqlite3.connect(str(db_path))
    try:
        con.row_factory = sqlite3.Row
        for col_name, col_type in [
            ("pips_simulated_resolver", "REAL"),
            ("exit_reason_resolver", "TEXT"),
        ]:
            try:
                if _has_column(con, "paper_trades", col_name):
                    result["skipped_existing"].append(col_name)
                    continue
                if dry_run:
                    result["added_columns"].append(f"{col_name} ({col_type}) [dry-run]")
                else:
                    con.execute(
                        f"ALTER TABLE paper_trades ADD COLUMN {col_name} {col_type}"
                    )
                    result["added_columns"].append(f"{col_name} ({col_type})")
            except sqlite3.OperationalError as e:
                result["errors"].append(f"{col_name}: {e}")
        if not dry_run:
            con.commit()
    except Exception as e:  # noqa: BLE001
        result["errors"].append(f"global: {e}")
    finally:
        con.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migration colonnes resolver (R2 additif)"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.apply:
        args.dry_run = True

    result = migrate(args.db, dry_run=args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "APPLY"
    print(f"[{mode}] DB: {args.db}")
    if result["added_columns"]:
        print(f"  Colonnes à ajouter : {result['added_columns']}")
    if result["skipped_existing"]:
        print(f"  Déjà présentes     : {result['skipped_existing']}")
    if result["errors"]:
        print(f"  ERREURS            : {result['errors']}")
        return 2
    if args.apply:
        print("  [OK ] Migration appliquée (commit fait)")
    else:
        print("  [    ] Aucune modification — passer --apply pour exécuter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
