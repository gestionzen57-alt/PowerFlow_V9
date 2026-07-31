"""v9_expectancy_comparison.py — Phase 24B motion CEO autopilote.

Compare expectancy live (paper trades fermes) vs expectancy bootstrap
pour detecter drift structurel.

Auteur : Hermes (Phase 24B motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.exp_cmp")


def get_paper_trades_pips(db_path: Path | str) -> list[float]:
    """Liste pips_net des paper trades fermes."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("""
                SELECT pips_net FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
            """).fetchall()
            return [float(r[0] or 0) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def live_expectancy(pips_list: list[float]) -> dict:
    """Calcule expectancy live (point estimate)."""
    if not pips_list:
        return {"error": "no_trades"}
    n = len(pips_list)
    wins = [p for p in pips_list if p > 0]
    return {
        "n_total": n,
        "wr_pct": round(100.0 * len(wins) / n, 2),
        "expectancy": round(sum(pips_list) / n, 3),
        "total_pips": round(sum(pips_list), 2),
    }


def bootstrap_expectancy(pips_list: list[float], n_sims: int = 1000,
                          seed: int = 42) -> dict:
    """Calcule distribution bootstrap de l'expectancy."""
    if not pips_list or len(pips_list) < 10:
        return {"error": "insufficient"}
    random.seed(seed)
    n = len(pips_list)
    exps = []
    for _ in range(n_sims):
        sample = [random.choice(pips_list) for _ in range(n)]
        exps.append(sum(sample) / n)
    exps.sort()
    return {
        "n_sims": n_sims,
        "mean": round(sum(exps) / n_sims, 3),
        "median": round(exps[n_sims // 2], 3),
        "p5": round(exps[n_sims // 20], 3),
        "p95": round(exps[n_sims - n_sims // 20], 3),
        "min": round(min(exps), 3),
        "max": round(max(exps), 3),
    }


def compare_expectancies(live: dict, boot: dict) -> dict:
    """Compare live vs bootstrap et detecte drift."""
    if "error" in live or "error" in boot:
        return {"error": "insufficient_data"}
    delta = live["expectancy"] - boot["mean"]
    # Z-score
    boot_range = boot["max"] - boot["min"]
    z_score = delta / (boot_range / 6) if boot_range > 0 else 0  # 6 std
    if z_score > 1.5:
        drift = "LIVE_ABOVE_BOOTSTRAP"
        rec = "POSITIVE_DRIFT"
    elif z_score < -1.5:
        drift = "LIVE_BELOW_BOOTSTRAP"
        rec = "NEGATIVE_DRIFT"
    else:
        drift = "STABLE"
        rec = "NO_DRIFT"
    return {
        "delta": round(delta, 3),
        "z_score": round(z_score, 3),
        "drift": drift,
        "recommendation": rec,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 expectancy comparison (Phase 24B)",
    )
    parser.add_argument("--n-sims", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    pips = get_paper_trades_pips(DB_PATH)
    live = live_expectancy(pips)
    boot = bootstrap_expectancy(pips, n_sims=args.n_sims, seed=args.seed)
    comp = compare_expectancies(live, boot)

    print("=" * 70)
    print("PHASE 24B — EXPECTANCY COMPARISON")
    print("=" * 70)
    if "error" in live:
        print(f"Live erreur : {live['error']}")
        return 1
    print("LIVE (point estimate):")
    print(f"  N trades   : {live['n_total']}")
    print(f"  WR         : {live['wr_pct']:.2f}%")
    print(f"  Expectancy : {live['expectancy']:+.3f} p/trade")
    print()
    if "error" in boot:
        print(f"Boot erreur : {boot['error']}")
        return 1
    print(f"BOOTSTRAP ({boot['n_sims']} sims):")
    print(f"  Mean       : {boot['mean']:+.3f}")
    print(f"  Median     : {boot['median']:+.3f}")
    print(f"  P5         : {boot['p5']:+.3f}")
    print(f"  P95        : {boot['p95']:+.3f}")
    print()
    if "error" not in comp:
        print(f"Delta (live-boot) : {comp['delta']:+.3f}")
        print(f"Z-score          : {comp['z_score']:.3f}")
        print(f"Drift            : {comp['drift']}")
        print(f"Recommendation   : {comp['recommendation']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())