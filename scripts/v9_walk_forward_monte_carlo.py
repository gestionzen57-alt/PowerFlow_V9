"""v9_walk_forward_monte_carlo.py — Phase 24A motion CEO autopilote.

Walk-forward Monte Carlo : N simulations aleatoires de walk-forward
sur les paper trades, pour estimer la distribution OOS expectancy.

Auteur : Hermes (Phase 24A motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.wfmc")


def get_paper_trades_chrono(db_path: Path | str) -> list[dict]:
    """Retourne les paper trades fermes classes par date fermeture."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT id, symbol, direction, opened_at, closed_at,
                       pips_net
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                ORDER BY closed_at ASC
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def walk_forward_simulation(trades: list[dict], train_ratio: float = 0.7,
                             seed: int = 42) -> dict:
    """Simule un walk-forward : train sur N% puis test sur reste."""
    random.seed(seed)
    if len(trades) < 20:
        return {"error": "insufficient_trades", "n": len(trades)}

    n = len(trades)
    split = int(n * train_ratio)
    in_sample = trades[:split]
    out_sample = trades[split:]

    # IS expectancy
    is_pips = [t["pips_net"] for t in in_sample]
    is_exp = sum(is_pips) / len(is_pips)
    is_wins = sum(1 for p in is_pips if p > 0)
    is_wr = is_wins / len(is_pips)

    # OOS expectancy
    oos_pips = [t["pips_net"] for t in out_sample]
    oos_exp = sum(oos_pips) / len(oos_pips) if oos_pips else 0
    oos_wins = sum(1 for p in oos_pips if p > 0)
    oos_wr = oos_wins / len(oos_pips) if oos_pips else 0

    # Degradation ratio
    deg_ratio = oos_exp / is_exp if is_exp != 0 else 0

    return {
        "n_total": n,
        "n_in_sample": len(in_sample),
        "n_out_sample": len(out_sample),
        "is_wr": round(is_wr * 100, 2),
        "is_expectancy": round(is_exp, 3),
        "is_pips_total": round(sum(is_pips), 2),
        "oos_wr": round(oos_wr * 100, 2),
        "oos_expectancy": round(oos_exp, 3),
        "oos_pips_total": round(sum(oos_pips), 2),
        "degradation_ratio": round(deg_ratio, 3),
        "passed": oos_exp > 0,
    }


def walk_forward_monte_carlo(trades: list[dict], n_sims: int = 1000,
                              train_ratio: float = 0.7,
                              seed: int = 42) -> dict:
    """Execute N walk-forward sims aleatoires."""
    if len(trades) < 20:
        return {"error": "insufficient_trades", "n": len(trades)}

    rng = random.Random(seed)
    results = []
    for i in range(n_sims):
        # Shuffle trades pour simuler walk-forward aleatoire
        shuffled = trades[:]
        rng.shuffle(shuffled)
        result = walk_forward_simulation(shuffled, train_ratio=train_ratio,
                                          seed=seed + i)
        if "error" not in result:
            results.append(result)

    if not results:
        return {"error": "no_results"}

    # Distribution OOS
    oos_exps = sorted([r["oos_expectancy"] for r in results])
    oos_wrs = sorted([r["oos_wr"] for r in results])
    deg_ratios = sorted([r["degradation_ratio"] for r in results])

    n_res = len(results)
    return {
        "n_simulations": n_res,
        "train_ratio": train_ratio,
        "is_wr_mean": round(sum(r["is_wr"] for r in results) / n_res, 2),
        "oos_wr_mean": round(sum(r["oos_wr"] for r in results) / n_res, 2),
        "is_exp_mean": round(sum(r["is_expectancy"] for r in results) / n_res, 3),
        "oos_exp_mean": round(sum(oos_exps) / n_res, 3),
        "oos_exp_median": round(oos_exps[n_res // 2], 3),
        "oos_exp_p5": round(oos_exps[n_res // 20], 3),
        "oos_exp_p95": round(oos_exps[n_res - n_res // 20], 3),
        "oos_exp_min": round(min(oos_exps), 3),
        "oos_exp_max": round(max(oos_exps), 3),
        "p_oos_positive": round(100.0 * sum(1 for e in oos_exps if e > 0) / n_res, 2),
        "deg_ratio_median": round(deg_ratios[n_res // 2], 3),
        "deg_ratio_p5": round(deg_ratios[n_res // 20], 3),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 walk-forward Monte Carlo (Phase 24A)",
    )
    parser.add_argument("--n-sims", type=int, default=1000)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    trades = get_paper_trades_chrono(DB_PATH)
    result = walk_forward_monte_carlo(trades, n_sims=args.n_sims,
                                        train_ratio=args.train_ratio,
                                        seed=args.seed)

    print("=" * 70)
    print("PHASE 24A — WALK-FORWARD MONTE CARLO")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1

    print(f"N simulations      : {result['n_simulations']}")
    print(f"Train ratio        : {result['train_ratio']}")
    print()
    print(f"IS WR mean         : {result['is_wr_mean']:.2f}%")
    print(f"OOS WR mean        : {result['oos_wr_mean']:.2f}%")
    print(f"IS exp mean        : {result['is_exp_mean']:+.3f} p/trade")
    print(f"OOS exp mean       : {result['oos_exp_mean']:+.3f} p/trade")
    print(f"OOS exp median     : {result['oos_exp_median']:+.3f} p/trade")
    print(f"OOS exp P5         : {result['oos_exp_p5']:+.3f} p/trade")
    print(f"OOS exp P95        : {result['oos_exp_p95']:+.3f} p/trade")
    print()
    print(f"P(OOS exp > 0)     : {result['p_oos_positive']:.2f}%")
    print(f"Degradation median : {result['deg_ratio_median']:.3f}")
    print()
    if result["p_oos_positive"] > 95 and result["oos_exp_p5"] > 0:
        print(">>> Edge OOS TRES ROBUSTE (>95% P>0, P5>0)")
    elif result["p_oos_positive"] > 80:
        print(">>> Edge OOS ROBUSTE (>80% P>0)")
    else:
        print(">>> Edge OOS FRAGILE")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())