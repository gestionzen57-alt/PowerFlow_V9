"""v9_monte_carlo.py — Phase 23 motion CEO « EDGE FUND MAX ».

Monte Carlo bootstrap : simule N runs aleatoires sur les trades historiques
pour estimer la distribution de l'expectancy et la probabilite de ruine.

Auteur : Hermes (Phase 23 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.monte_carlo")


def get_paper_trades_pips(db_path: Path | str) -> list[float]:
    """Retourne la liste des pips_net de tous les paper trades fermes."""
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


def monte_carlo_bootstrap(pips_list: list[float], n_simulations: int = 1000,
                          seed: int | None = 42) -> dict:
    """Execute N simulations bootstrap sur les trades historiques.

    Pour chaque simulation, on tire avec remise n trades et on calcule
    l'expectancy. Cela donne la distribution reelle de l'expectancy.
    """
    if seed is not None:
        random.seed(seed)
    if len(pips_list) < 10:
        return {"error": "insufficient_trades", "n_trades": len(pips_list)}

    n = len(pips_list)
    expectancies = []
    max_dds = []
    ruin_count = 0
    RUIN_THRESHOLD_PIPS = 100.0  # drawdown >= 100 pips = ruine

    for _ in range(n_simulations):
        # Bootstrap avec remise
        sample = [random.choice(pips_list) for _ in range(n)]
        exp = sum(sample) / n
        expectancies.append(exp)
        # Max DD + tracking ruine
        running_max = 0.0
        running_dd = 0.0
        max_dd = 0.0
        ruin_reached = False
        for p in sample:
            running_dd += p
            if running_dd > running_max:
                running_max = running_dd
            dd = running_max - running_dd
            if dd > max_dd:
                max_dd = dd
            # Ruine = drawdown atteint ou depasse le seuil (positif, en pips)
            if dd >= RUIN_THRESHOLD_PIPS:
                ruin_reached = True
        max_dds.append(max_dd)
        if ruin_reached:
            ruin_count += 1

    expectancies.sort()
    max_dds.sort()

    return {
        "n_simulations": n_simulations,
        "n_trades_bootstrap": n,
        "expectancy_mean": round(sum(expectancies) / n_simulations, 3),
        "expectancy_median": round(expectancies[n_simulations // 2], 3),
        "expectancy_p5": round(expectancies[n_simulations // 20], 3),
        "expectancy_p95": round(expectancies[n_simulations - n_simulations // 20], 3),
        "expectancy_min": round(min(expectancies), 3),
        "expectancy_max": round(max(expectancies), 3),
        "max_dd_median": round(max_dds[n_simulations // 2], 3),
        "max_dd_p95": round(max_dds[n_simulations - n_simulations // 20], 3),
        "ruin_probability_pct": round(100.0 * ruin_count / n_simulations, 2),
        "ruin_threshold_pips": RUIN_THRESHOLD_PIPS,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 Monte Carlo bootstrap (Phase 23 quantique)",
    )
    parser.add_argument("--n-sims", type=int, default=1000,
                        help="Nombre de simulations (defaut 1000)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Seed aleatoire (defaut 42)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    pips_list = get_paper_trades_pips(DB_PATH)
    result = monte_carlo_bootstrap(pips_list, n_simulations=args.n_sims,
                                    seed=args.seed)

    print("=" * 70)
    print("PHASE 23 — MONTE CARLO BOOTSTRAP")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']} (n={result['n_trades']})")
        return 1

    print(f"N simulations      : {result['n_simulations']}")
    print(f"N trades bootstrap : {result['n_trades_bootstrap']}")
    print()
    print(f"Expectancy moyenne : {result['expectancy_mean']:+.3f} p/trade")
    print(f"Expectancy mediane : {result['expectancy_median']:+.3f} p/trade")
    print(f"Expectancy P5      : {result['expectancy_p5']:+.3f} p/trade")
    print(f"Expectancy P95     : {result['expectancy_p95']:+.3f} p/trade")
    print(f"Expectancy min     : {result['expectancy_min']:+.3f} p/trade")
    print(f"Expectancy max     : {result['expectancy_max']:+.3f} p/trade")
    print()
    print(f"Max DD median      : {result['max_dd_median']:.1f} p")
    print(f"Max DD P95         : {result['max_dd_p95']:.1f} p")
    print()
    print(f"P(ruine>=-100p)    : {result['ruin_probability_pct']:.2f}%")
    print()
    if result["expectancy_p5"] > 0:
        print(">>> Edge ROBUSTE : P5 expectancy > 0 (95% confiance)")
    else:
        print(">>> Edge FRAGILE : P5 expectancy <= 0")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())