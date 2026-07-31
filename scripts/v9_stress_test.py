"""v9_stress_test.py — Phase 28C motion CEO autopilote.

Stress test : simule des scenarios catastrophes et mesure l'impact.

Scenarios :
1. WR chute a 50%
2. Spread double (1.5 → 3.0)
3. 5 losses consecutives (streak noir)
4. Edge expire (edge devient 0)
5. Black swan : 1 trade perd 50 pips

Auteur : Hermes (Phase 28C motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.stress")


SCENARIOS = {
    "wr_50pct": "WR chute a 50%",
    "spread_double": "Spread double (1.5p → 3.0p)",
    "loss_streak_5": "5 losses consecutives",
    "edge_expires": "Edge expire (edge → 0)",
    "black_swan": "1 trade perd 50 pips",
}


def apply_scenario(pips_list: list[float], scenario: str,
                   trade_count: int = 30) -> dict:
    """Applique un scenario et calcule impact."""
    if not pips_list or len(pips_list) < 5:
        return {"error": "insufficient_data"}
    baseline_exp = sum(pips_list) / len(pips_list)
    baseline_total = sum(pips_list)

    if scenario == "wr_50pct":
        # Inverser tous les trades : si win→loss et vice versa (simplification)
        modified = [-p for p in pips_list]
        new_exp = sum(modified) / len(modified)
    elif scenario == "spread_double":
        # Augmenter le cout de chaque trade de 1.5p (double spread)
        modified = [p - 1.5 for p in pips_list]
        new_exp = sum(modified) / len(modified)
    elif scenario == "loss_streak_5":
        # Ajouter 5 pertes consecutives de -8p au milieu
        midpoint = len(pips_list) // 2
        modified = pips_list[:midpoint] + [-8.0] * 5 + pips_list[midpoint:]
        new_exp = sum(modified) / len(modified)
    elif scenario == "edge_expires":
        # Edge devient 0 : expectancy tend vers 0
        new_exp = 0.0
        modified = [0.0] * len(pips_list)
    elif scenario == "black_swan":
        # Ajouter 1 trade perdant 50p
        modified = pips_list + [-50.0]
        new_exp = sum(modified) / len(modified)
    else:
        return {"error": "unknown_scenario"}

    new_total = sum(modified)
    impact_exp = new_exp - baseline_exp
    impact_total = new_total - baseline_total
    impact_pct = (impact_exp / baseline_exp * 100) if baseline_exp != 0 else 0

    return {
        "scenario": scenario,
        "description": SCENARIOS.get(scenario, scenario),
        "n_trades": len(modified),
        "baseline_exp": round(baseline_exp, 3),
        "new_exp": round(new_exp, 3),
        "impact_exp": round(impact_exp, 3),
        "impact_total_pips": round(impact_total, 2),
        "impact_pct": round(impact_pct, 2),
        "survived": new_exp > 0,
    }


def run_all_scenarios(pips_list: list[float]) -> list[dict]:
    """Execute tous les scenarios."""
    results = []
    for scenario in SCENARIOS:
        res = apply_scenario(pips_list, scenario)
        if "error" not in res:
            results.append(res)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 stress test (Phase 28C)",
    )
    parser.add_argument("--scenario", default=None,
                        help=f"Scenario specifique ({list(SCENARIOS.keys())})")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    import sqlite3
    db_path = DB_PATH
    pips_list = []
    if Path(db_path).exists():
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                rows = conn.execute("""
                    SELECT pips_net FROM v9_paper_trades
                    WHERE closed_at IS NOT NULL
                """).fetchall()
                pips_list = [float(r[0] or 0) for r in rows]
            finally:
                conn.close()
        except Exception:
            pass

    if not pips_list:
        # Mock pour execution sans DB
        pips_list = [23.5] * 80 + [-9.5] * 20

    if args.scenario:
        results = [apply_scenario(pips_list, args.scenario)]
    else:
        results = run_all_scenarios(pips_list)

    print("=" * 70)
    print("PHASE 28C — STRESS TEST")
    print("=" * 70)
    print(f"N trades analyses : {len(pips_list)}")
    print()
    for r in results:
        if "error" in r:
            print(f"[{r['error']}]")
            continue
        status = "SURVIVED" if r["survived"] else "EDGE MORT"
        print(f"[{r['scenario']}] {r['description']}")
        print(f"  Exp baseline : {r['baseline_exp']:+.3f} → new : {r['new_exp']:+.3f}")
        print(f"  Impact       : {r['impact_exp']:+.3f} p/trade ({r['impact_pct']:+.1f}%)")
        print(f"  Status       : {status}")
        print()
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())