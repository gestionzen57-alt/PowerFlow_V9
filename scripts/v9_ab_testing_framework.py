"""v9_ab_testing_framework.py — Phase 90 motion CEO 48H (post-Plan C).

A/B testing framework pour comparer variantes de strategies/leviers.
Calcule effect size, p-value, uplift.

Auteur : Hermes (Phase 90 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log_level = "INFO"

SIG_THRESHOLD_P = 0.05


@dataclass
class Variant:
    """Variante d'une experience A/B."""
    name: str
    func: Callable[[dict[str, Any]], float]


@dataclass
class Experiment:
    """Experience A/B avec plusieurs variantes."""
    name: str
    variants: list[Variant] = field(default_factory=list)


def compute_effect_size(
    control_mean: float, control_std: float,
    treatment_mean: float, treatment_std: float,
    n_control: int, n_treatment: int,
) -> dict[str, Any]:
    """Calcule effect size (Cohen's d), p-value approx, uplift %.

    Retourne dict avec significant, effect_size, uplift_pct, p_value.
    """
    # Cohen's d (pooled std)
    if n_control < 2 or n_treatment < 2:
        return {
            "effect_size": 0.0, "uplift_pct": 0.0,
            "p_value": 1.0, "significant": False,
            "n_control": n_control, "n_treatment": n_treatment,
        }
    pooled_var = (
        (n_control - 1) * control_std ** 2
        + (n_treatment - 1) * treatment_std ** 2
    ) / (n_control + n_treatment - 2)
    pooled_std = math.sqrt(pooled_var) if pooled_var > 0 else 1.0
    d = (treatment_mean - control_mean) / pooled_std
    # Uplift %
    uplift = (
        ((treatment_mean - control_mean) / control_mean * 100)
        if control_mean != 0 else 0.0
    )
    # t-test approx (Welch)
    se_diff = math.sqrt(
        control_std ** 2 / n_control + treatment_std ** 2 / n_treatment,
    )
    t_stat = (treatment_mean - control_mean) / se_diff if se_diff > 0 else 0
    # p-value approx via |t| (grossier, suffit pour framework)
    p_value = 2 * (1 - _normal_cdf(abs(t_stat)))
    return {
        "effect_size": round(d, 3),
        "uplift_pct": round(uplift, 2),
        "t_stat": round(t_stat, 3),
        "p_value": round(p_value, 4),
        "significant": p_value < SIG_THRESHOLD_P,
        "n_control": n_control,
        "n_treatment": n_treatment,
    }


def _normal_cdf(x: float) -> float:
    """CDF approx de la loi normale standard (Abramowitz & Stegun)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def run_experiment(
    exp: Experiment, samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute l'experience : applique chaque variante aux samples."""
    if len(exp.variants) < 2:
        return {"error": "need at least 2 variants"}
    results = {}
    for variant in exp.variants:
        values = [variant.func(s) for s in samples]
        results[variant.name] = {
            "n": len(values),
            "mean": round(statistics.mean(values), 4),
            "std": round(statistics.stdev(values) if len(values) > 1 else 0.0, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }
    # Effect size (premier = control, deuxieme = treatment)
    control = results[exp.variants[0].name]
    treatment = results[exp.variants[1].name]
    if exp.variants[0].name == "control" or len(exp.variants) >= 2:
        effect = compute_effect_size(
            control_mean=control["mean"],
            control_std=control["std"],
            treatment_mean=treatment["mean"],
            treatment_std=treatment["std"],
            n_control=control["n"],
            n_treatment=treatment["n"],
        )
        results["effect"] = effect
    return {
        "experiment": exp.name,
        "n_samples": len(samples),
        "variants": results,
    }


def main(argv=None) -> int:
    """Demo A/B test : control vs treatment +10%."""
    print("=" * 70)
    print("V9 A/B TESTING FRAMEWORK (Phase 90)")
    print("=" * 70)
    variants = [
        Variant("control", lambda x: x["value"]),
        Variant("treatment", lambda x: x["value"] * 1.10),
    ]
    exp = Experiment("test_uplift", variants)
    samples = [{"value": v} for v in [10, 12, 15, 14, 11, 13, 16, 18, 14, 15]]
    res = run_experiment(exp, samples)
    print(f"Experiment : {res['experiment']}")
    print(f"N samples  : {res['n_samples']}")
    for name, stats in res["variants"].items():
        if name == "effect":
            continue
        print(f"  {name:10s} : mean={stats['mean']:.3f} std={stats['std']:.3f}")
    if "effect" in res["variants"]:
        e = res["variants"]["effect"]
        print(f"\nEffect size : {e['effect_size']}")
        print(f"Uplift %    : {e['uplift_pct']:+.2f}%")
        print(f"p-value     : {e['p_value']}")
        print(f"Significant : {e['significant']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())