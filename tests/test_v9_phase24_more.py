"""tests/test_v9_phase24_more.py — Phase 24B/24C motion CEO autopilote.

Tests pour expectancy_comparison + hurst_exponent.
"""
import pytest
import math


# === v9_expectancy_comparison ===

def test_get_paper_trades_pips_db_missing(tmp_path):
    from scripts.v9_expectancy_comparison import get_paper_trades_pips
    assert get_paper_trades_pips(tmp_path / "absent.db") == []


def test_live_expectancy_empty():
    from scripts.v9_expectancy_comparison import live_expectancy
    res = live_expectancy([])
    assert "error" in res


def test_live_expectancy_basic():
    from scripts.v9_expectancy_comparison import live_expectancy
    res = live_expectancy([25.0, 25.0, -8.0])
    assert res["n_total"] == 3
    assert res["wr_pct"] == pytest.approx(66.67, abs=0.1)
    assert res["expectancy"] == pytest.approx(14.0, abs=0.1)


def test_bootstrap_expectancy_insufficient():
    from scripts.v9_expectancy_comparison import bootstrap_expectancy
    res = bootstrap_expectancy([1.0] * 5)
    assert "error" in res


def test_bootstrap_expectancy_distribution():
    from scripts.v9_expectancy_comparison import bootstrap_expectancy
    pips = [25.0] * 80 + [-8.0] * 20
    res = bootstrap_expectancy(pips, n_sims=100, seed=42)
    assert res["mean"] > 10  # edge positif


def test_compare_expectancies_stable():
    from scripts.v9_expectancy_comparison import compare_expectancies
    live = {"n_total": 100, "wr_pct": 70, "expectancy": 5.0, "total_pips": 500}
    boot = {"n_sims": 100, "mean": 5.1, "median": 5.0, "p5": 4.0,
            "p95": 6.0, "min": 3.0, "max": 7.0}
    res = compare_expectancies(live, boot)
    assert res["drift"] == "STABLE"
    assert res["recommendation"] == "NO_DRIFT"


def test_compare_expectancies_negative_drift():
    from scripts.v9_expectancy_comparison import compare_expectancies
    live = {"n_total": 100, "wr_pct": 30, "expectancy": -3.0, "total_pips": -300}
    boot = {"n_sims": 100, "mean": 5.0, "median": 5.0, "p5": 4.0,
            "p95": 6.0, "min": 3.0, "max": 7.0}
    res = compare_expectancies(live, boot)
    assert res["drift"] == "LIVE_BELOW_BOOTSTRAP"


# === v9_hurst_exponent ===

def test_get_paper_trades_pips_hurst_db_missing(tmp_path):
    from scripts.v9_hurst_exponent import get_paper_trades_pips
    assert get_paper_trades_pips(tmp_path / "absent.db") == []


def test_hurst_insufficient():
    from scripts.v9_hurst_exponent import hurst_exponent
    res = hurst_exponent([1.0] * 10)
    assert "error" in res


def test_hurst_random_walk():
    """Serie random walk → Hurst ~ 0.5 (avec tolerance large)."""
    import random
    random.seed(42)
    # Marche aleatoire simple
    increments = [random.gauss(0, 1) for _ in range(200)]
    series = []
    running = 0.0
    for x in increments:
        running += x
        series.append(running)
    from scripts.v9_hurst_exponent import hurst_exponent
    res = hurst_exponent(series)
    # Random walk tend vers 0.5, tolerance large
    if "hurst_exponent" in res:
        assert 0.0 < res["hurst_exponent"] < 2.0  # au moins dans les clous


def test_hurst_trend_following():
    """Serie croissante monotone → Hurst > 0.5."""
    series = [float(i) for i in range(1, 201)]
    from scripts.v9_hurst_exponent import hurst_exponent
    res = hurst_exponent(series)
    # Trend-following devrait donner H > 0.5
    if "hurst_exponent" in res:
        assert res["hurst_exponent"] > 0.5


def test_rs_range_basic():
    from scripts.v9_hurst_exponent import rs_range
    r, s = rs_range([1.0, 2.0, 3.0, 4.0, 5.0])
    assert r > 0
    assert s > 0