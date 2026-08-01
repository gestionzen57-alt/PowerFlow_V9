"""v9_robustness_checks.py — Phase 60 motion CEO validée.

Robustness checks : bootstrap + Monte Carlo + permutation test.
Verifie que l'edge est statistiquement significatif.

Auteur : Hermes (Phase 60 motion CEO validée, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.robustness")


def bootstrap_pips(pips: list[float], n_iter: int = 1000,
                     rng: random.Random = None) -> dict:
    """Bootstrap : resample pips avec remise, calcule distribution."""
    if not pips:
        return {"error": "no_data"}
    if rng is None:
        rng = random.Random(42)
    n = len(pips)
    boot_means = []
    boot_sharpes = []
    for _ in range(n_iter):
        sample = [pips[rng.randint(0, n - 1)] for _ in range(n)]
        mean = sum(sample) / n
        var = sum((p - mean) ** 2 for p in sample) / n
        std = var ** 0.5
        sharpe = mean / std if std > 0 else 0.0
        boot_means.append(mean)
        boot_sharpes.append(sharpe)
    boot_means.sort()
    boot_sharpes.sort()
    return {
        "n_iter": n_iter,
        "mean_p5": round(boot_means[int(n_iter * 0.05)], 3),
        "mean_p50": round(boot_means[int(n_iter * 0.50)], 3),
        "mean_p95": round(boot_means[int(n_iter * 0.95)], 3),
        "sharpe_p5": round(boot_sharpes[int(n_iter * 0.05)], 3),
        "sharpe_p50": round(boot_sharpes[int(n_iter * 0.50)], 3),
        "sharpe_p95": round(boot_sharpes[int(n_iter * 0.95)], 3),
    }


def monte_carlo_permutation(pips: list[float], n_iter: int = 1000,
                              rng: random.Random = None) -> dict:
    """Monte Carlo permutation : shuffle et compare mean avec original."""
    if not pips:
        return {"error": "no_data"}
    if rng is None:
        rng = random.Random(42)
    original_mean = sum(pips) / len(pips)
    n = len(pips)
    null_means = []
    for _ in range(n_iter):
        shuffled = pips[:]
        rng.shuffle(shuffled)
        null_means.append(sum(shuffled) / n)
    null_means.sort()
    # p-value : fraction des null means >= original mean
    n_above = sum(1 for m in null_means if m >= original_mean)
    p_value = n_above / n_iter
    return {
        "n_iter": n_iter,
        "original_mean": round(original_mean, 3),
        "null_mean_p5": round(null_means[int(n_iter * 0.05)], 3),
        "null_mean_p50": round(null_means[int(n_iter * 0.50)], 3),
        "null_mean_p95": round(null_means[int(n_iter * 0.95)], 3),
        "p_value": round(p_value, 4),
    }


def statistical_test(pips: list[float]) -> dict:
    """t-test simple : compare mean vs 0."""
    if len(pips) < 2:
        return {"error": "insufficient_data"}
    n = len(pips)
    mean = sum(pips) / n
    var = sum((p - mean) ** 2 for p in pips) / (n - 1)
    std = var ** 0.5
    if std == 0:
        return {"t_stat": 0.0, "p_value": 1.0, "significant": False}
    # t-stat = mean / (std / sqrt(n))
    t_stat = mean / (std / (n ** 0.5))
    # Approximation p-value via normal distribution (gros n)
    from math import erf, sqrt
    p_value = 2 * (1 - abs(0.5 * (1 + erf(abs(t_stat) / sqrt(2)))))
    return {
        "n": n,
        "mean": round(mean, 3),
        "std": round(std, 3),
        "t_stat": round(t_stat, 3),
        "p_value": round(p_value, 4),
        "significant": p_value < 0.05,
    }


def run_robustness_checks(pips: list[float], n_iter: int = 1000) -> dict:
    """Run tous les checks."""
    if not pips:
        return {"error": "no_data"}
    boot = bootstrap_pips(pips, n_iter=n_iter)
    mc = monte_carlo_permutation(pips, n_iter=n_iter)
    test = statistical_test(pips)
    # Verdict
    verdict = "PRODUCTION"
    if not test.get("significant", False):
        verdict = "NEEDS_TUNING"
    if mc.get("p_value", 1.0) > 0.05:
        verdict = "NOT_EDGE"
    if boot.get("mean_p5", 0) < 0:
        verdict = "NOT_EDGE"
    return {
        "n_trades": len(pips),
        "n_iter": n_iter,
        "bootstrap": boot,
        "monte_carlo": mc,
        "statistical_test": test,
        "verdict": verdict,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 robustness checks (Phase 60)",
    )
    parser.add_argument("--n-iter", type=int, default=1000)
    parser.add_argument("--demo", action="store_true",
                        help="Utilise des pips demo")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("PHASE 60 — ROBUSTNESS CHECKS")
    print("=" * 70)
    if args.demo:
        # Demo : 100 trades WR 85%, TP 25, SL 8
        rng = random.Random(42)
        pips = []
        for _ in range(100):
            if rng.random() < 0.85:
                pips.append(25.0)
            else:
                pips.append(-8.0)
    else:
        # Lecture depuis pips_file
        pips = [25.0, -8.0] * 50  # placeholder
    result = run_robustness_checks(pips, n_iter=args.n_iter)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    print(f"N trades       : {result['n_trades']}")
    print(f"N iterations   : {result['n_iter']}")
    print()
    print("--- Bootstrap ---")
    boot = result["bootstrap"]
    print(f"Mean p5/p50/p95: {boot['mean_p5']} / {boot['mean_p50']} / {boot['mean_p95']}")
    print(f"Sharpe p5/p50  : {boot['sharpe_p5']} / {boot['sharpe_p50']}")
    print()
    print("--- Monte Carlo permutation ---")
    mc = result["monte_carlo"]
    print(f"Original mean  : {mc['original_mean']}")
    print(f"p-value        : {mc['p_value']}")
    print()
    print("--- t-test ---")
    test = result["statistical_test"]
    print(f"t-stat         : {test['t_stat']}")
    print(f"p-value        : {test['p_value']}")
    print(f"Significant    : {test.get('significant', False)}")
    print()
    print(f"VERDICT : {result['verdict']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())