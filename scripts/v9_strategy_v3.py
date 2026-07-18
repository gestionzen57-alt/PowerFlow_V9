"""v9_strategy_v3.py — V3 stratégies agressives (time ultra-court, asymétrie forte).

2026-07-17 motion CEO « change le SL elargie le pour tester SL 15 TP 9 ou 6
dans un premier temps ».

Le CEO veut tester SL élargi / TP réduit. On teste 8 nouvelles combinaisons.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.db_schema import get_connection  # noqa: E402
from core.v9.exit_simulator import ExitSimulator  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("v9.strat_v3")


def load_trades() -> list[dict]:
    conn = get_connection(ROOT / "data" / "v9_forces.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT pt.trade_id, pt.opened_at, d.symbol
        FROM paper_trades pt JOIN decisions d ON d.snapshot_id=pt.snapshot_id
        WHERE pt.closed_at IS NOT NULL AND d.symbol='GBPUSD' AND pt.direction='baissiere'
        ORDER BY pt.opened_at
    """).fetchall()
    conn.close()

    trades = []
    for r in rows:
        try:
            odt = datetime.fromisoformat(r["opened_at"].replace("Z", "+00:00"))
            epoch = int(odt.timestamp())
        except Exception:
            continue
        conn = get_connection(ROOT / "data" / "v9_forces.db")
        fr = conn.execute("""
            SELECT mid FROM forces_snapshots
            WHERE symbol=? AND timeframe='M5' AND bar_time > ?
            ORDER BY bar_time ASC LIMIT 200
        """, (r["symbol"], epoch)).fetchall()
        conn.close()
        if not fr:
            continue
        future_mids = [float(f[0]) for f in fr]
        trades.append({
            "trade_id": r["trade_id"],
            "entry_price": future_mids[0],
            "future_mids": future_mids,
        })
    return trades


def eval_strategy(trades: list[dict], tp: float, sl: float, time_bars: int = 0) -> dict:
    """Évalue TP/SL/(time_bars) sur tous les trades."""
    sim = ExitSimulator(
        strategy="TP_SL", tp_pips=tp, sl_pips=sl, time_bars=time_bars, symbol="GBPUSD",
    )
    wins, losses, total = 0, 0, 0.0
    cum, peak, max_dd = 0.0, 0.0, 0.0
    pips_list = []
    for trade in trades:
        try:
            res = sim.simulate(
                entry=trade["entry_price"], direction="baissiere",
                future_mids=trade["future_mids"],
            )
            pips = res.pips
            # Force time exit
            if time_bars > 0 and res.exit_reason not in ("tp_hit", "sl_hit"):
                n = min(time_bars, len(trade["future_mids"]))
                last = trade["future_mids"][n - 1]
                pips = (trade["entry_price"] - last) * 10000
        except Exception:
            continue
        pips_list.append(pips)
        if pips > 0: wins += 1
        else: losses += 1
        total += pips
        cum += pips
        if cum > peak: peak = cum
        dd = peak - cum
        if dd > max_dd: max_dd = dd
    n = wins + losses
    wr = round(100 * wins / n, 2) if n else 0
    avg = round(total / n, 2) if n else 0
    import statistics
    std = statistics.pstdev(pips_list) or 1
    sharpe = round(avg / std, 3) if std else 0
    return {"tp": tp, "sl": sl, "time_bars": time_bars, "n": n,
            "wins": wins, "wr_pct": wr, "avg_pips": avg,
            "total_pips": round(total, 1), "max_dd": round(max_dd, 1),
            "sharpe": sharpe}


def main() -> int:
    log.info("=" * 60)
    log.info("V3 STRATÉGIES — baissier GBPUSD (3681 trades)")
    log.info("=" * 60)
    trades = load_trades()
    log.info(f"Trades: {len(trades)}")

    # Grille CEO : TP 6/9/12, SL 15/25/40, time exit 3/5/8
    configs = []
    for tp in [6, 9, 12]:
        for sl in [15, 25, 40]:
            for tb in [0, 3, 5, 8]:
                configs.append((tp, sl, tb))

    results = []
    log.info(f"Grille: {len(configs)} configurations")
    for i, (tp, sl, tb) in enumerate(configs):
        if i % 10 == 0:
            log.info(f"  ... {i}/{len(configs)}")
        r = eval_strategy(trades, tp, sl, tb)
        results.append(r)

    # Top 15 par total_pips
    top = sorted(results, key=lambda x: -x["total_pips"])[:15]
    log.info("\n" + "=" * 60)
    log.info("TOP 15 (par total_pips)")
    log.info("=" * 60)
    print(f"{'TP':>4} {'SL':>4} {'TimeB':>6} | {'WR%':>6} {'AvgPips':>9} {'Total':>10} {'MaxDD':>8} {'Sharpe':>8}")
    for r in top:
        print(f"  {r['tp']:>3.0f} {r['sl']:>3.0f} {r['time_bars']:>5} | "
              f"{r['wr_pct']:>5.1f}% {r['avg_pips']:>+8.2f} {r['total_pips']:>+9.1f} "
              f"{r['max_dd']:>7.1f} {r['sharpe']:>7.3f}")

    # Export
    out = ROOT / "data" / "strategy_pole" / "strategy_v3_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "n_trades": len(trades),
            "n_configs": len(configs),
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    log.info(f"\nExporté dans {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())