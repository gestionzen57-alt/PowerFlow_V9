#!/usr/bin/env python3
"""Clôture les paper trades orphelins — Phase 13 CEO, Mouvement 2.1.

Lit les paper_trades ouverts (closed_at IS NULL), récupère le is_win
de la décision correspondante (même snapshot_id), et met à jour
closed_at, pips_simulated, is_win.

Usage:
    python scripts/v9_close_paper_trades.py          # dry-run
    python scripts/v9_close_paper_trades.py --apply   # écriture réelle
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="Clôture les paper trades orphelins")
    parser.add_argument("--apply", action="store_true", help="Applique la clôture (défaut: dry-run)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Récupérer les paper trades ouverts avec leur décision associée
    cur.execute("""
        SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.opened_at,
               d.is_win, d.decision_id
        FROM paper_trades pt
        JOIN decisions d ON d.snapshot_id = pt.snapshot_id
        WHERE pt.closed_at IS NULL
          AND d.is_win IS NOT NULL
        ORDER BY pt.opened_at
    """)
    rows = cur.fetchall()

    if not rows:
        print("[OK] Aucun paper trade ouvert à clôturer.")
        conn.close()
        return

    now_utc = datetime.now(timezone.utc).isoformat()
    wins = sum(1 for r in rows if r["is_win"] == 1)
    losses = sum(1 for r in rows if r["is_win"] == 0)

    print(f"Paper trades à clôturer : {len(rows)} ({wins} wins / {losses} losses)")
    print(f"Horodatage clôture      : {now_utc}")
    print()

    for r in rows[:10]:
        print(f"  {r['trade_id']} | dir={r['direction']} | opened={r['opened_at']} | is_win={r['is_win']}")
    if len(rows) > 10:
        print(f"  ... et {len(rows) - 10} autres")

    if not args.apply:
        print(f"\n[Dry-run] Aucune écriture. Passez --apply pour clôturer.")
        conn.close()
        return

    # Appliquer la clôture
    updated = 0
    for r in rows:
        cur.execute("""
            UPDATE paper_trades
            SET closed_at = ?,
                is_win = ?,
                pips_simulated = CASE WHEN ? = 1 THEN 10.0 ELSE -10.0 END
            WHERE trade_id = ? AND closed_at IS NULL
        """, (now_utc, r["is_win"], r["is_win"], r["trade_id"]))
        updated += cur.rowcount

    conn.commit()
    conn.close()

    print(f"\n[OK] {updated} paper trades clôturés.")
    print(f"     {wins} wins / {losses} losses")
    print(f"     Pips: +10.0 win / -10.0 loss (valeur symbolique — pas de prix réel stocké)")


if __name__ == "__main__":
    main()
