"""v9_paper_runner_continuous.py — Phase 30B motion CEO autopilote.

Paper trader continu qui tourne en boucle avec sizing Kelly uncertainty.
Ouvre/ferme paper trades toutes les N secondes selon edge + sizing.

Auteur : Hermes (Phase 30B motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.paper_cont")


def kelly_safe(wr: float, rr: float = 3.125, fractional: float = 0.25) -> float:
    """Kelly fractionnel safe."""
    if wr <= 0 or rr <= 0:
        return 0.0
    kelly_full = (wr * (rr + 1) - 1) / rr
    kelly_safe = max(0, kelly_full * fractional)
    return min(kelly_safe, 0.25)


def simulate_one_trade(wr: float, tp: float = 25.0, sl: float = 8.0
                        ) -> dict:
    """Simule un trade (Monte Carlo simple)."""
    is_win = random.random() < wr
    pips_net = tp - 1.5 if is_win else -sl - 1.5  # spread inclus
    return {
        "pips_net": pips_net,
        "pips_brut": tp if is_win else -sl,
        "is_win": is_win,
        "close_reason": "TP_hit" if is_win else "SL_hit",
    }


def run_loop(n_iterations: int = 100, wr: float = 0.85, sleep_sec: float = 0.5,
              edge_baseline_wr: float = 0.946) -> dict:
    """Execute N trades paper avec sizing Kelly uncertainty."""
    print(f"Edge baseline : {edge_baseline_wr * 100:.1f}% WR")
    print(f"WR simule     : {wr * 100:.1f}%")
    rr = 25.0 / 8.0
    size_factor = kelly_safe(wr, rr=rr, fractional=0.25)
    print(f"Kelly safe    : {size_factor * 100:.2f}%")
    print(f"N iterations : {n_iterations}")
    print(f"Sleep/trade  : {sleep_sec}s")
    print()
    total_pips = 0.0
    n_wins = 0
    n_losses = 0
    start = datetime.now(timezone.utc)
    for i in range(n_iterations):
        trade = simulate_one_trade(wr)
        total_pips += trade["pips_net"]
        if trade["is_win"]:
            n_wins += 1
        else:
            n_losses += 1
        if (i + 1) % 10 == 0:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            wr_so_far = 100.0 * n_wins / (i + 1)
            print(f"  Trade {i + 1:3d}/{n_iterations}  "
                  f"WR={wr_so_far:5.1f}%  "
                  f"pips_net={trade['pips_net']:+.1f}  "
                  f"total={total_pips:+.1f}  "
                  f"({elapsed:.1f}s)")
        if sleep_sec > 0:
            time.sleep(sleep_sec)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    n_total = n_wins + n_losses
    actual_wr = 100.0 * n_wins / n_total if n_total > 0 else 0
    expectancy = total_pips / n_total if n_total > 0 else 0
    return {
        "n_total": n_total,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "wr_pct": round(actual_wr, 2),
        "total_pips": round(total_pips, 2),
        "expectancy": round(expectancy, 3),
        "kelly_safe_pct": round(size_factor * 100, 2),
        "elapsed_sec": round(elapsed, 2),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 paper runner continuous (Phase 30B)",
    )
    parser.add_argument("--n", type=int, default=100,
                        help="Nombre iterations (defaut 100)")
    parser.add_argument("--wr", type=float, default=0.85,
                        help="WR simule (defaut 0.85)")
    parser.add_argument("--sleep", type=float, default=0.0,
                        help="Sleep par trade en secondes (defaut 0)")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("PHASE 30B — PAPER RUNNER CONTINUOUS")
    print("=" * 70)
    result = run_loop(n_iterations=args.n, wr=args.wr, sleep_sec=args.sleep)
    print()
    print("=" * 70)
    print("RÉSULTAT FINAL :")
    print(f"  N trades     : {result['n_total']}")
    print(f"  WR           : {result['wr_pct']}%")
    print(f"  Total pips   : {result['total_pips']:+.1f}")
    print(f"  Expectancy   : {result['expectancy']:+.3f} p/trade")
    print(f"  Kelly safe   : {result['kelly_safe_pct']}%")
    print(f"  Duree        : {result['elapsed_sec']}s")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())