"""v9_parallel_backtest.py — Backtest parallèle multi-paires V9.

2026-07-17 motion CEO « orchestre et optimise au max » :
Exploite tous les CPUs pour traiter les candidats en parallèle.

Pattern :
  1. Découpe les candidats par symbole (5-6 paires)
  2. Lance un subprocess Python par paire
  3. Agrège les résultats dans un rapport global
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get_pairs() -> list[str]:
    """Retourne les paires disponibles dans la DB."""
    db = ROOT / "data" / "v9_forces.db"
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM decisions "
            "WHERE action='preparer_entree' AND source_type='live'"
        ).fetchall()
        return sorted(r[0] for r in rows if r[0])
    finally:
        conn.close()


def backtest_pair(args: tuple[str, int]) -> dict:
    """Lance un batch paper-trade pour un symbole donné. Retourne résultat."""
    symbol, limit = args
    # Écrit le script dans un fichier temporaire (évite les problèmes de quotes)
    script = ROOT / "data" / "_tmp_parallel_backtest.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(f"""
import sys, json
sys.path.insert(0, r'{ROOT}')
from core.v9.trade_engine import TradeEngine
import sqlite3

conn = sqlite3.connect(r'{ROOT / "data" / "v9_forces.db"}')
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT DISTINCT d.snapshot_id FROM decisions d "
    "LEFT JOIN paper_trades pt ON pt.snapshot_id = d.snapshot_id "
    "WHERE d.action = 'preparer_entree' AND d.source_type = 'live' "
    "AND d.symbol = ? AND (pt.trade_id IS NULL) "
    "ORDER BY d.timestamp DESC LIMIT ?",
    ('{symbol}', {limit}),
).fetchall()
conn.close()

te = TradeEngine()
opened = 0
skipped = 0
for r in rows:
    res = te.process(r['snapshot_id'])
    if res['action'] == 'open':
        opened += 1
    else:
        skipped += 1

close_res = te.close_open_trades()
stats = te.get_stats()
print(json.dumps({{
    'symbol': '{symbol}',
    'opened': opened,
    'skipped': skipped,
    'closed': close_res['closed'],
    'wins': close_res['wins'],
    'losses': close_res['losses'],
    'wr_pct': stats['wr'],
    'total_pips': stats['total_pips'],
}}))
""", encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, cwd=str(ROOT), timeout=300,
        )
        lines = [l for l in result.stdout.strip().split("\n") if l.startswith("{")]
        if lines:
            try:
                return json.loads(lines[-1])
            except json.JSONDecodeError:
                return {"symbol": symbol, "error": "parse_failed",
                        "raw": lines[-1] if lines else "(empty)"}
        return {"symbol": symbol, "error": "no_output",
                "stderr": result.stderr[-200:] if result.stderr else "(none)"}
    finally:
        try:
            script.unlink()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest parallèle multi-paires V9")
    parser.add_argument("--limit", type=int, default=500,
                        help="Limite par paire (défaut 500)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Nombre de subprocess parallèles (défaut 4)")
    args = parser.parse_args()

    pairs = get_pairs()
    print(f"Paires détectées: {pairs}")
    print(f"Workers: {args.workers}, limit/pair: {args.limit}")
    print()

    tasks = [(symbol, args.limit) for symbol in pairs]

    t0 = time.perf_counter()
    # multiprocessing.Pool pour paralléliser
    with multiprocessing.Pool(processes=min(args.workers, len(pairs))) as pool:
        results = pool.map(backtest_pair, tasks)

    elapsed = time.perf_counter() - t0

    # Agrégation
    total_opened = 0
    total_skipped = 0
    total_closed = 0
    total_wins = 0
    total_losses = 0
    total_pips = 0.0

    print("=" * 70)
    print(f"{'Paire':>10} | {'Open':>5} | {'Skip':>5} | {'Close':>5} | {'WR%':>6} | {'Pips':>8}")
    print("-" * 70)
    for r in results:
        if "error" in r:
            print(f"{r['symbol']:>10} | ERROR: {r.get('error', '?')}")
            continue
        print(
            f"{r['symbol']:>10} | {r['opened']:>5} | {r['skipped']:>5} | "
            f"{r['closed']:>5} | {r['wr_pct']:>5.1f}% | {r['total_pips']:>+7.1f}"
        )
        total_opened += r["opened"]
        total_skipped += r["skipped"]
        total_closed += r["closed"]
        total_wins += r["wins"]
        total_losses += r["losses"]
        total_pips += r["total_pips"]

    print("-" * 70)
    wr = round(100 * total_wins / max(total_wins + total_losses, 1), 1)
    print(
        f"{'TOTAL':>10} | {total_opened:>5} | {total_skipped:>5} | "
        f"{total_closed:>5} | {wr:>5.1f}% | {total_pips:>+7.1f}"
    )
    print()
    print(f"Temps total: {elapsed:.1f}s ({elapsed / max(1, len(pairs)):.1f}s/paire)")

    return 0


if __name__ == "__main__":
    sys.exit(main())