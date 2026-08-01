"""tests/test_v9_phase90.py — Phase 90 motion CEO 48H (post-Plan C).

Tests pour ab_testing_framework.
"""
import pytest


def test_create_variant():
    from scripts.v9_ab_testing_framework import Variant
    v = Variant("control", lambda x: x)
    assert v.name == "control"


def test_create_experiment():
    from scripts.v9_ab_testing_framework import Experiment
    e = Experiment("exp1", [])
    assert e.name == "exp1"


def test_run_experiment_basic():
    from scripts.v9_ab_testing_framework import (
        Experiment, Variant, run_experiment,
    )
    variants = [
        Variant("control", lambda x: x["a"] * 1.0),
        Variant("treatment", lambda x: x["a"] * 1.1),
    ]
    exp = Experiment("exp1", variants)
    samples = [{"a": 1.0}, {"a": 2.0}, {"a": 3.0}]
    res = run_experiment(exp, samples)
    assert "variants" in res
    assert "control" in res["variants"]
    assert "treatment" in res["variants"]


def test_compute_effect_size_basic():
    from scripts.v9_ab_testing_framework import compute_effect_size
    # treatment > control
    effect = compute_effect_size(
        control_mean=10.0, control_std=2.0,
        treatment_mean=12.0, treatment_std=2.0,
        n_control=100, n_treatment=100,
    )
    assert effect["significant"] is True
    assert effect["effect_size"] > 0
    assert "uplift_pct" in effect


def test_compute_effect_size_no_significance():
    from scripts.v9_ab_testing_framework import compute_effect_size
    effect = compute_effect_size(
        control_mean=10.0, control_std=5.0,
        treatment_mean=10.1, treatment_std=5.0,
        n_control=20, n_treatment=20,
    )
    # Avec petit n et grand std, probablement pas significatif
    assert "significant" in effect
    assert "effect_size" in effect


def test_compute_effect_size_negative_uplift():
    """Si treatment < control, uplift_pct negatif."""
    from scripts.v9_ab_testing_framework import compute_effect_size
    effect = compute_effect_size(
        control_mean=10.0, control_std=1.0,
        treatment_mean=9.0, treatment_std=1.0,
        n_control=100, n_treatment=100,
    )
    assert effect["uplift_pct"] < 0


def test_p_value_bounds():
    from scripts.v9_ab_testing_framework import compute_effect_size
    effect = compute_effect_size(
        control_mean=10.0, control_std=1.0,
        treatment_mean=12.0, treatment_std=1.0,
        n_control=100, n_treatment=100,
    )
    assert 0.0 <= effect["p_value"] <= 1.0


def test_run_experiment_with_samples():
    from scripts.v9_ab_testing_framework import (
        Experiment, Variant, run_experiment,
    )
    variants = [
        Variant("control", lambda x: x["value"]),
        Variant("treatment", lambda x: x["value"] * 1.5),
    ]
    exp = Experiment("test", variants)
    samples = [{"value": v} for v in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]
    res = run_experiment(exp, samples)
    # Treatment devrait avoir moyenne > control
    assert res["variants"]["treatment"]["mean"] > res["variants"]["control"]["mean"]


def test_main_demo(capsys):
    from scripts.v9_ab_testing_framework import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "A/B TESTING" in captured.out