"""V10 Migration data — ajoute la colonne `symbol` à paper_trades.

Débloque le Risk Parity cross-pair (bloqué en Phase B car paper_trades
n'avait pas de colonne symbol).

Méthode (100% additif, 0 suppression, 0 modif autres tables) :
  1. ALTER TABLE paper_trades ADD COLUMN symbol TEXT
  2. Remplissage par JOIN signals (252/337 résolus via snapshot_id)
  3. Fallback : parser le préfixe du snapshot_id ('v9-SYMBOL-TF-...')
     pour les 85 restants.
  4. Backup complet de la table avant toute modif (R8).

Usage : python scripts/v10_backfill_paper_symbol.py --apply
        python scripts/v10_backfill_paper_symbol.py --dry-run (défaut)

Doctrine : R2 additif pur, R8 backup, R9 audit (rapport JSON), R10 lecture
prudente (dry-run par défaut, backup obligatoire).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "v9_forces.db")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "backups")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "V10", "v10_paper_symbol_backfill.json")

KNOWN_SYMBOLS = {"GBPUSD", "USDJPY", "EURUSD", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}


def _parse_symbol_from_snapshot_id(sid: str) -> str:
    """snapshot_id format 'v9-GBPUSD-M15-<epoch>-<n>' → 'GBPUSD'."""
    if not sid:
        return ""
    m = re.match(r"v9-([A-Z]{6})-(M\d+|H\d+)", sid)
    if m and m.group(1) in KNOWN_SYMBOLS:
        return m.group(1)
    return ""


def _backup_table(con: sqlite3.Connection) -> str:
    """Copie la table paper_trades dans une table miroir horodatée."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_name = f"paper_trades_backup_{ts}"
    con.execute(f'CREATE TABLE "{backup_name}" AS SELECT * FROM paper_trades')
    con.commit()
    return backup_name


def run(dry_run: bool = True) -> dict:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    report = {"dry_run": dry_run, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        # Vérifier si la colonne existe déjà
        cols = [r[1] for r in con.execute("PRAGMA table_info(paper_trades)")]
        already = "symbol" in cols
        report["column_exists"] = already
        if already:
            # Recalculer le taux de couverture
            total = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
            filled = con.execute("SELECT COUNT(*) FROM paper_trades WHERE symbol IS NOT NULL AND symbol != ''").fetchone()[0]
            report["total"] = total
            report["filled"] = filled
            report["coverage_pct"] = round(100.0 * filled / total, 2) if total else 0
            return report

        total = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        report["total"] = total

        if not dry_run:
            backup = _backup_table(con)
            report["backup_table"] = backup
            con.execute("ALTER TABLE paper_trades ADD COLUMN symbol TEXT")
            con.commit()

        # 1) JOIN signals
        rows = con.execute(
            """
            SELECT pt.trade_id, s.symbol
            FROM paper_trades pt JOIN signals s ON pt.snapshot_id = s.snapshot_id
            """
        ).fetchall()
        joined = {r["trade_id"]: r["symbol"] for r in rows}

        # 2) Fallback parsing snapshot_id
        all_rows = con.execute("SELECT trade_id, snapshot_id FROM paper_trades").fetchall()
        parsed = {}
        for r in all_rows:
            if r["trade_id"] not in joined:
                sym = _parse_symbol_from_snapshot_id(r["snapshot_id"])
                if sym:
                    parsed[r["trade_id"]] = sym

        mapping = {**joined, **parsed}
        report["via_join"] = len(joined)
        report["via_parse"] = len(parsed)
        report["unresolved"] = total - len(mapping)

        if not dry_run:
            for tid, sym in mapping.items():
                con.execute("UPDATE paper_trades SET symbol=? WHERE trade_id=?", (sym, tid))
            con.commit()
            report["applied"] = len(mapping)
        else:
            report["would_apply"] = len(mapping)

        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return report
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="appliquer les changements (défaut: dry-run)")
    args = ap.parse_args()
    report = run(dry_run=not args.apply)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
