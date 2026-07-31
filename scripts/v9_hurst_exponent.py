"""v9_hurst_exponent.py — Phase 24C motion CEO autopilote.

Calcule l'exposant de Hurst sur la serie de pips_net.
H > 0.5 = trend (series persistante)
H < 0.5 = mean-reversion (series anti-persistante)
H = 0.5 = random walk

Implementation simplifiee : R/S method sur les pips cumules.

Auteur : Hermes (Phase 24C motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import math
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.hurst")


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


def rs_range(series: list[float]) -> tuple[float, float]:
    """Calcule R = max - min de la deviation cumulee, et S = std."""
    mean = sum(series) / len(series)
    cumulative = []
    running = 0.0
    for x in series:
        running += (x - mean)
        cumulative.append(running)
    r = max(cumulative) - min(cumulative)
    s = math.sqrt(sum((x - mean) ** 2 for x in series) / len(series))
    return r, s


def hurst_exponent(pips_list: list[float]) -> dict:
    """Calcule Hurst via R/S sur multiples fenetres.

    slope(log(n), log(R/S)) = H
    """
    if len(pips_list) < 30:
        return {"error": "insufficient_data", "n": len(pips_list)}

    # Test sur plusieurs tailles de sous-series
    sizes = [10, 20, 40, 80]
    sizes = [s for s in sizes if s <= len(pips_list) // 2]
    log_n = []
    log_rs = []

    for size in sizes:
        n_subseries = len(pips_list) // size
        rs_values = []
        for i in range(n_subseries):
            sub = pips_list[i * size:(i + 1) * size]
            r, s = rs_range(sub)
            if s > 0:
                rs_values.append(r / s)
        if rs_values:
            avg_rs = sum(rs_values) / len(rs_values)
            if avg_rs > 0:
                log_n.append(math.log(size))
                log_rs.append(math.log(avg_rs))

    if len(log_n) < 2:
        return {"error": "insufficient_window_sizes"}

    # Regression lineaire log(n) -> log(R/S)
    n = len(log_n)
    mean_x = sum(log_n) / n
    mean_y = sum(log_rs) / n
    cov = sum((log_n[i] - mean_x) * (log_rs[i] - mean_y) for i in range(n))
    var_x = sum((log_n[i] - mean_x) ** 2 for i in range(n))
    if var_x == 0:
        return {"error": "zero_variance"}
    slope = cov / var_x

    if slope > 0.6:
        regime = "TREND_FOLLOWING"
        rec = "EDGE_STABLE_TREND"
    elif slope < 0.4:
        regime = "MEAN_REVERTING"
        rec = "POSSIBLE_OVERTRADING"
    else:
        regime = "RANDOM_WALK"
        rec = "EDGE_NEUTRAL"

    return {
        "hurst_exponent": round(slope, 3),
        "n_trades": len(pips_list),
        "n_window_sizes": n,
        "regime": regime,
        "recommendation": rec,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 Hurst exponent (Phase 24C)",
    )
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    pips = get_paper_trades_pips(DB_PATH)
    result = hurst_exponent(pips)

    print("=" * 70)
    print("PHASE 24C — HURST EXPONENT")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    print(f"N trades           : {result['n_trades']}")
    print(f"Hurst exponent     : {result['hurst_exponent']}")
    print(f"Regime             : {result['regime']}")
    print(f"Recommendation     : {result['recommendation']}")
    print()
    if result["hurst_exponent"] > 0.5:
        print(">>> Serie PERSISTANTE (trend-following)")
        print(">>> Trades ont une 'memoire' : wins->wins, losses->losses")
    elif result["hurst_exponent"] < 0.5:
        print(">>> Serie ANTI-PERSISTANTE (mean-reverting)")
        print(">>> Trades alternent : win->loss, loss->win")
    else:
        print(">>> Serie ALEATOIRE (random walk)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())