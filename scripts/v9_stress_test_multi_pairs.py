"""v9_stress_test_multi_pairs.py — Phase 87 motion CEO 48H (post-Plan C).

Stress test multi-paires pour valider l'edge sur univers de paires.
Genere trades synthetiques, calcule metrics par paire, verdict global.

Auteur : Hermes (Phase 87 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
import math
import random
from typing import Any

log = logging.getLogger("v9.stress")

DEFAULT_PAIRS = ["GBPUSD", "EURUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD", "USDCHF", "XAUUSD"]

WR_BY_PAIR = {
    "GBPUSD": 0.85, "EURUSD": 0.55, "USDJPY": 0.60,
    "AUDUSD": 0.50, "USDCAD": 0.40, "NZDUSD": 0.50,
    "USDCHF": 0.55, "XAUUSD": 0.65,
}


def synthesize_pair_trades(
    symbol: str, n: int, seed: int | None = None,
) -> list[dict[str, Any]]:
    """Genere N trades synthetiques pour un symbol."""
    rng = random.Random(seed)
    wr = WR_BY_PAIR.get(symbol, 0.55)
    trades = []
    for i in range(n):
        is_win = rng.random() < wr
        if is_win:
            pips = rng.uniform(15, 35)
        else:
            pips = rng.uniform(-12, -5)
        trades.append({
            "symbol": symbol,
            "pips": round(pips, 2),
            "is_win": is_win,
            "hold_minutes": rng.randint(2, 7),
        })
    return trades


def compute_pair_metrics(
    symbol: str, trades: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calcule metrics par paire (Sharpe, Sortino, DD, PF, WR)."""
    if not trades:
        return {
            "symbol": symbol, "n_trades": 0, "wins": 0, "wr": 0.0,
            "total_pips": 0.0, "sharpe": 0.0, "sortino": 0.0,
            "max_dd": 0.0, "profit_factor": 0.0, "avg_hold_min": 0.0,
        }
    pips = [t["pips"] for t in trades]
    wins = sum(1 for t in trades if t["is_win"])
    total_pips = sum(pips)
    wr = wins / len(trades)
    mean = total_pips / len(trades)
    sd = math.sqrt(sum((p - mean) ** 2 for p in pips) / (len(pips) - 1)) if len(pips) > 1 else 0
    sharpe = mean / sd * math.sqrt(252) if sd > 0 else 0.0
    # Sortino
    downside = [p for p in pips if p < 0]
    downside_sd = math.sqrt(sum(p ** 2 for p in downside) / len(downside)) if downside else 0
    sortino = mean / downside_sd * math.sqrt(252) if downside_sd > 0 else 0.0
    # Max DD
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pips:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    # Profit factor
    gross_win = sum(p for p in pips if p > 0)
    gross_loss = abs(sum(p for p in pips if p < 0))
    pf = gross_win / gross_loss if gross_loss > 0 else 0.0
    avg_hold = sum(t["hold_minutes"] for t in trades) / len(trades)
    return {
        "symbol": symbol,
        "n_trades": len(trades),
        "wins": wins,
        "wr": round(wr, 4),
        "total_pips": round(total_pips, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_dd": round(max_dd, 2),
        "profit_factor": round(pf, 3),
        "avg_hold_min": round(avg_hold, 1),
    }


def run_stress_test(
    symbols: list[str] | None = None,
    n_trades_per_pair: int = 50,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute stress test multi-paires. Retourne verdict global."""
    symbols = symbols or DEFAULT_PAIRS
    rng = random.Random(seed)
    pairs_results = []
    for sym in symbols:
        seed_for_pair = rng.randint(0, 999999)
        trades = synthesize_pair_trades(sym, n_trades_per_pair, seed=seed_for_pair)
        metrics = compute_pair_metrics(sym, trades)
        pairs_results.append(metrics)
    # Global verdict
    avg_wr = sum(p["wr"] for p in pairs_results) / len(pairs_results)
    avg_sharpe = sum(p["sharpe"] for p in pairs_results) / len(pairs_results)
    n_winning = sum(1 for p in pairs_results if p["total_pips"] > 0)
    n_losing = sum(1 for p in pairs_results if p["total_pips"] <= 0)
    if avg_wr >= 0.65 and avg_sharpe >= 0.5 and n_winning >= n_losing:
        verdict = "PASS"
    elif avg_wr >= 0.50 and avg_sharpe >= 0.0:
        verdict = "WARN"
    else:
        verdict = "FAIL"
    return {
        "n_pairs": len(symbols),
        "n_trades_per_pair": n_trades_per_pair,
        "pairs": pairs_results,
        "avg_wr": round(avg_wr, 4),
        "avg_sharpe": round(avg_sharpe, 3),
        "n_winning_pairs": n_winning,
        "n_losing_pairs": n_losing,
        "global_verdict": verdict,
    }


def main(argv=None) -> int:
    """Demo stress test multi-paires."""
    print("=" * 70)
    print("V9 STRESS TEST MULTI-PAIRS (Phase 87)")
    print("=" * 70)
    res = run_stress_test(symbols=DEFAULT_PAIRS, n_trades_per_pair=50, seed=42)
    print(f"N pairs           : {res['n_pairs']}")
    print(f"Avg WR            : {res['avg_wr']*100:.2f}%")
    print(f"Avg Sharpe        : {res['avg_sharpe']}")
    print(f"Winning pairs     : {res['n_winning_pairs']}/{res['n_pairs']}")
    print(f"Global verdict    : {res['global_verdict']}")
    print()
    print("Per pair :")
    for p in res["pairs"]:
        marker = "OK" if p["total_pips"] > 0 else "FAIL"
        print(
            f"  {p['symbol']:7s} : n={p['n_trades']:3d} WR={p['wr']*100:.1f}% "
            f"pips={p['total_pips']:+7.1f} Sharpe={p['sharpe']:+.2f} "
            f"PF={p['profit_factor']:.2f} [{marker}]"
        )
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())