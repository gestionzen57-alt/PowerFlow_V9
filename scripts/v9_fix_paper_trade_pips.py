#!/usr/bin/env python3
"""Recalcule les pips réels des paper trades depuis les décisions résolues.

Les 71 paper trades ont été clôturés avec des pips symboliques (±10).
Ce script lit les vrais pips depuis decisions.resolution_pips (calculés par
v9_resolve_decision_auto.py via MFE × 10000) et met à jour paper_trades.

Usage:
    python scripts/v9_fix_paper_trade_pips.py          # dry-run
    python scripts/v9_fix_paper_trade_pips.py --apply   # écriture réelle
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
    parser = argparse.ArgumentParser(description="Recalcule les pips réels des paper trades")
    parser.add_argument("--apply", action="store_true", help="Applique la correction (défaut: dry-run)")
    args = parser.parse_args()

    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Récupérer les paper trades avec leur décision résolue
    cur.execute("""
        SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.opened_at,
               d.resolution_pips, d.is_win, d.decision_id,
               fs.mid as entry_price
        FROM paper_trades pt
        JOIN decisions d ON d.snapshot_id = pt.snapshot_id
        JOIN forces_snapshots fs ON fs.snapshot_id = pt.snapshot_id
        WHERE pt.closed_at IS NOT NULL
          AND d.resolution_pips IS NOT NULL
        ORDER BY pt.opened_at
    """)
    rows = cur.fetchall()

    if not rows:
        print("[OK] Aucun paper trade à corriger.")
        conn.close()
        return

    # Statistiques
    total_pips = 0.0
    wins = 0
    losses = 0
    changed = 0
    already_correct = 0

    print(f"Paper trades à vérifier : {len(rows)}")
    print()

    for r in rows:
        real_pips = r["resolution_pips"]
        # Vérifier si déjà correct (pips_simulated != ±10 symbolique)
        cur.execute("SELECT pips_simulated FROM paper_trades WHERE trade_id = ?", (r["trade_id"],))
        current_pips = cur.fetchone()[0]

        if current_pips == real_pips:
            already_correct += 1
            continue

        changed += 1
        if r["is_win"] == 1:
            wins += 1
        else:
            losses += 1
        total_pips += real_pips

        if changed <= 5:
            print(f"  {r['trade_id'][:20]} | dir={r['direction']} | "
                  f"entry={r['entry_price']:.5f} | "
                  f"pips: {current_pips:.1f} → {real_pips:.1f} | "
                  f"win={r['is_win']}")

    if changed > 5:
        print(f"  ... et {changed - 5} autres")

    avg_pips = total_pips / changed if changed > 0 else 0
    print(f"\nÀ corriger : {changed} paper trades")
    print(f"Déjà corrects : {already_correct}")
    print(f"Pips réels : {total_pips:.1f} total, {avg_pips:.1f} moyenne")
    print(f"Wins: {wins} / Losses: {losses}")

    if not args.apply:
        print(f"\n[Dry-run] Aucune écriture. Passez --apply pour appliquer.")
        conn.close()
        return

    # Appliquer la correction
    updated = 0
    for r in rows:
        real_pips = r["resolution_pips"]
        cur.execute("""
            UPDATE paper_trades
            SET pips_simulated = ?
            WHERE trade_id = ? AND (pips_simulated IS NULL OR pips_simulated != ?)
        """, (real_pips, r["trade_id"], real_pips))
        if cur.rowcount:
            updated += 1

    conn.commit()
    conn.close()

    print(f"\n[OK] {updated} paper trades mis à jour avec les vrais pips.")
    print(f"     Pips réels : {total_pips:.1f} total, {avg_pips:.1f} moyenne")
    print(f"     Source : decisions.resolution_pips (MFE × 10000, horizon 4h)")


if __name__ == "__main__":
    main()
