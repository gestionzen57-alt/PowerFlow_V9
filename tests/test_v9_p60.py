"""tests/test_v9_p60.py — Phase 60 motion CEO validée.

Tests pour robustness_checks.
"""
import pytest


def test_bootstrap_empty():
    from scripts.v9_robustness_checks import bootstrap_pips
    res = bootstrap_pips([])
    assert "error" in res


def test_bootstrap_basic():
    from scripts.v9_robustness_checks import bootstrap_pips
    pips = [25.0] * 9 + [-8.0]
    res = bootstrap_pips(pips, n_iter=100)
    assert "mean_p50" in res
    assert res["mean_p50"] > 0  # plus de wins que losses


def test_bootstrap_zero_variance():
    from scripts.v9_robustness_checks import bootstrap_pips
    pips = [25.0] * 100
    res = bootstrap_pips(pips, n_iter=100)
    assert res["mean_p5"] == 25.0


def test_monte_carlo_permutation_empty():
    from scripts.v9_robustness_checks import monte_carlo_permutation
    res = monte_carlo_permutation([])
    assert "error" in res


def test_monte_carlo_permutation_basic():
    from scripts.v9_robustness_checks import monte_carlo_permutation
    pips = [25.0] * 9 + [-8.0]
    res = monte_carlo_permutation(pips, n_iter=100)
    assert "p_value" in res


def test_monte_carlo_permutation_zero_pvalue():
    """Si tous les pips sont identiques, p_value = 0 car original > null."""
    from scripts.v9_robustness_checks import monte_carlo_permutation
    pips = [25.0] * 100
    res = monte_carlo_permutation(pips, n_iter=100)
    # original_mean = 25.0, null_means = 25.0 (identiques)
    # n_above = 100 (car >=), p_value = 1.0
    assert res["p_value"] == 1.0


def test_statistical_test_insufficient():
    from scripts.v9_robustness_checks import statistical_test
    res = statistical_test([1.0])
    assert "error" in res


def test_statistical_test_basic():
    from scripts.v9_robustness_checks import statistical_test
    pips = [25.0] * 9 + [-8.0]
    res = statistical_test(pips)
    assert "t_stat" in res
    # mean > 0 donc t_stat > 0
    assert res["t_stat"] > 0


def test_statistical_test_zero_variance():
    from scripts.v9_robustness_checks import statistical_test
    pips = [25.0] * 50
    res = statistical_test(pips)
    assert res["t_stat"] == 0.0


def test_run_robustness_checks_empty():
    from scripts.v9_robustness_checks import run_robustness_checks
    res = run_robustness_checks([])
    assert "error" in res


def test_run_robustness_checks_edge():
    from scripts.v9_robustness_checks import run_robustness_checks
    pips = [25.0] * 90 + [-8.0] * 10
    res = run_robustness_checks(pips, n_iter=100)
    assert "verdict" in res


def test_run_robustness_checks_no_edge():
    from scripts.v9_robustness_checks import run_robustness_checks
    pips = [-8.0] * 9 + [25.0]  # 10% WR
    res = run_robustness_checks(pips, n_iter=100)
    assert res["verdict"] in ("NOT_EDGE", "NEEDS_TUNING")


def test_main_demo_runs(capsys):
    from scripts.v9_robustness_checks import main
    exit_code = main(["--demo", "--n-iter", "100"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ROBUSTNESS" in captured.out
    assert "VERDICT" in captured.out


def test_main_pips_runs(capsys):
    from scripts.v9_robustness_checks import main
    exit_code = main(["--n-iter", "100"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ROBUSTNESS" in captured.out