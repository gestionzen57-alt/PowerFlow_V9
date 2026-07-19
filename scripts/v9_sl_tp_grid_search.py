"""v9_sl_tp_grid_search.py — Grid search SL/TP sur trades baissiers GBPUSD.

2026-07-17 motion CEO « trouve pourquoi baissier perd, change le SL, test
différentes stratégies de gestion ».

But : identifier la combinaison (SL, TP, exit_strategy) qui maximise
l'expectancy des trades baissiers GBPUSD.

Pour chaque trade baissier GBPUSD, on dispose de :
  - entry_price (1er M5 après opened_at)
  - future_mids (200 prix M5 après entry)

On simule path-dependent pour chaque combinaison SL/TP/exit et on mesure :
  - WR
  - avg_pips
  - total_pips
  - max_drawdown

Grid search :
  - TP : [6, 8, 9, 10, 12, 15, 20, 25]
  - SL : [10, 15, 20, 25, 30, 40, 50]
  - exit : [TP_SL, TRAILING, TIME_BASED, MFE_ONLY]
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.exit_simulator import (  # noqa: E402
    ExitSimulator,
    ExitStrategy,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("v9.sl_tp_grid")


def load_trade_data(db_path: Path | str) -> list[dict]:
    """Charge tous les trades baissiers GBPUSD avec prix d'entrée + futurs."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT pt.trade_id, pt.opened_at, pt.direction,
                   d.symbol, d.snapshot_id
            FROM paper_trades pt
            JOIN decisions d ON d.snapshot_id=pt.snapshot_id
            WHERE pt.closed_at IS NOT NULL
              AND d.symbol='GBPUSD' AND pt.direction='baissiere'
            ORDER BY pt.opened_at DESC
            """
        ).fetchall()
    finally:
        conn.close()

    trades = []
    for r in rows:
        # Récupère prix M5 futurs
        from datetime import datetime
        try:
            odt = datetime.fromisoformat(r["opened_at"].replace("Z", "+00:00"))
            opened_epoch = int(odt.timestamp())
        except Exception:
            continue
        conn = get_connection(db_path)
        try:
            fr = conn.execute(
                """
                SELECT mid FROM forces_snapshots
                WHERE symbol = ? AND timeframe = 'M5'
                  AND bar_time > ?
                ORDER BY bar_time ASC
                LIMIT 200
                """,
                (r["symbol"], opened_epoch),
            ).fetchall()
        finally:
            conn.close()
        if not fr:
            continue
        future_mids = [float(f[0]) for f in fr]
        trades.append({
            "trade_id": r["trade_id"],
            "entry_price": future_mids[0],
            "future_mids": future_mids,
            "n_bars": len(future_mids),
        })
    return trades


def simulate_combo(
    trade: dict,
    tp_pips: float,
    sl_pips: float,
    strategy: str = "TP_SL",
) -> dict:
    """Simule un trade avec (entry, tp, sl, strategy) → result dict."""
    sim = ExitSimulator(
        strategy=strategy,
        tp_pips=tp_pips,
        sl_pips=sl_pips,
        symbol="GBPUSD",
    )
    result = sim.simulate(
        entry=trade["entry_price"],
        direction="baissiere",
        future_mids=trade["future_mids"],
    )
    return {
        "pips": result.pips,
        "is_win": result.is_win,
        "exit_reason": result.exit_reason,
        "bars_held": result.bars_held,
    }


def grid_search(
    trades: list[dict],
    tp_grid: list[float],
    sl_grid: list[float],
    strategies: list[str],
) -> list[dict]:
    """Teste toutes les combinaisons SL/TP/exit × tous les trades."""
    results = []
    n_trades = len(trades)
    total_combos = len(tp_grid) * len(sl_grid) * len(strategies)
    log.info(f"Grid search: {total_combos} combinaisons × {n_trades} trades = {total_combos * n_trades} simulations")

    for tp, sl, strat in product(tp_grid, sl_grid, strategies):
        wins = 0
        losses = 0
        total_pips = 0.0
        peak = 0.0
        cum = 0.0
        max_dd = 0.0

        for trade in trades:
            r = simulate_combo(trade, tp, sl, strat)
            if r["is_win"] == 1:
                wins += 1
            else:
                losses += 1
            total_pips += r["pips"]
            cum += r["pips"]
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd

        n = wins + losses
        wr = round(100 * wins / n, 2) if n else 0
        avg = round(total_pips / n, 2) if n else 0
        results.append({
            "tp": tp,
            "sl": sl,
            "strategy": strat,
            "n_trades": n,
            "wins": wins,
            "losses": losses,
            "wr_pct": wr,
            "avg_pips": avg,
            "total_pips": round(total_pips, 1),
            "max_dd": round(max_dd, 1),
            "ratio_tp_sl": round(tp / sl, 2),
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Émettre uniquement le résultat JSON sur stdout.",
    )
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("GRID SEARCH SL/TP/STRATEGY — baissier GBPUSD")
    log.info("=" * 60)

    trades = load_trade_data(ROOT / "data" / "v9_forces.db")
    log.info(f"Trades chargés : {len(trades)}")

    if not trades:
        log.error("Aucun trade disponible")
        return 1

    # Grid recommandé par CEO
    tp_grid = [6, 8, 9, 10, 12, 15, 20, 25]
    sl_grid = [10, 15, 20, 25, 30, 40, 50]
    strategies = ["TP_SL", "TRAILING", "TIME_BASED", "MFE_ONLY"]

    results = grid_search(trades, tp_grid, sl_grid, strategies)

    # Top 20 par total_pips
    top = sorted(results, key=lambda r: r["total_pips"], reverse=True)[:20]
    log.info("\n" + "=" * 60)
    log.info("TOP 20 COMBINAISONS (par total_pips)")
    log.info("=" * 60)
    if not args.json_output:
        print(f"{'TP':>5} {'SL':>5} {'Strat':>12} | {'WR%':>6} {'AvgPips':>9} {'Total':>10} {'MaxDD':>8} {'Ratio':>6}")
        for r in top:
            print(
                f"  {r['tp']:>4.0f} {r['sl']:>4.0f} {r['strategy']:>12} | "
                f"{r['wr_pct']:>5.1f}% {r['avg_pips']:>+8.2f} {r['total_pips']:>+9.1f} "
                f"{r['max_dd']:>7.1f} {r['ratio_tp_sl']:>5.2f}"
            )

    # Baseline (TP=8, SL=15, TP_SL)
    baseline = next(
        (r for r in results if r["tp"] == 8 and r["sl"] == 15 and r["strategy"] == "TP_SL"),
        None,
    )
    if baseline:
        log.info(f"\nBaseline TP=8 SL=15 TP_SL : WR={baseline['wr_pct']}%, total={baseline['total_pips']}")
        # Combos qui battent la baseline
        better = [r for r in results if r["total_pips"] > baseline["total_pips"]]
        log.info(f"Combinaisons battant la baseline : {len(better)}/{len(results)}")
        if better and not args.json_output:
            print(f"\n{'TP':>5} {'SL':>5} {'Strat':>12} | {'WR%':>6} {'AvgPips':>9} {'Total':>10} {'Delta':>10}")
            for r in sorted(better, key=lambda x: -x["total_pips"])[:15]:
                delta = r["total_pips"] - baseline["total_pips"]
                print(
                    f"  {r['tp']:>4.0f} {r['sl']:>4.0f} {r['strategy']:>12} | "
                    f"{r['wr_pct']:>5.1f}% {r['avg_pips']:>+8.2f} {r['total_pips']:>+9.1f} {delta:>+9.1f}"
                )

    # Export complet en JSON
    out = ROOT / "data" / "strategy_pole" / "sl_tp_grid_search.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "n_trades": len(trades),
        "tp_grid": tp_grid,
        "sl_grid": sl_grid,
        "strategies": strategies,
        "n_combos": len(results),
        "results": results,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log.info(f"\nRésultats exportés dans {out}")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())