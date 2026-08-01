"""tests/test_v9_phase45.py — Phase 45 motion CEO 48h.

Tests pour v9_adaptive_risk.
"""
import pytest


def test_realized_vol_basic():
    from scripts.v9_adaptive_risk import realized_volatility
    pips = [25.0, -8.0, 30.0, -10.0, 20.0, -5.0, 15.0, -12.0,
            22.0, -8.0]
    vol = realized_volatility(pips, window=10)
    assert vol > 0


def test_realized_vol_too_short():
    from scripts.v9_adaptive_risk import realized_volatility
    assert realized_volatility([25.0], window=20) == 0.0
    assert realized_volatility([], window=20) == 0.0


def test_vol_targeting_basic():
    from scripts.v9_adaptive_risk import vol_targeting_sizing
    res = vol_targeting_sizing(0.5, 10.0, target_vol=8.0)
    assert res["size_factor"] < 1.0  # vol > target -> reduction
    assert res["final_size"] < 0.5


def test_vol_targeting_low_vol():
    from scripts.v9_adaptive_risk import vol_targeting_sizing
    res = vol_targeting_sizing(0.5, 4.0, target_vol=8.0)
    assert res["size_factor"] > 1.0  # vol < target -> augmentation
    assert res["final_size"] > 0.5


def test_vol_targeting_zero_vol():
    from scripts.v9_adaptive_risk import vol_targeting_sizing
    res = vol_targeting_sizing(0.5, 0.0)
    assert res["reason"] == "vol_zero"
    assert res["size_factor"] == 1.0


def test_vol_targeting_capped_max():
    from scripts.v9_adaptive_risk import vol_targeting_sizing
    # Tres faible vol → raw tres haut → capped at max
    res = vol_targeting_sizing(0.5, 0.1, target_vol=8.0)
    assert res["reason"] == "capped_at_max"
    assert res["size_factor"] == 2.0


def test_vol_targeting_capped_min():
    from scripts.v9_adaptive_risk import vol_targeting_sizing
    # Tres haute vol → raw tres bas → capped at min
    res = vol_targeting_sizing(0.5, 100.0, target_vol=8.0)
    assert res["reason"] == "capped_at_min"
    assert res["size_factor"] == 0.25


def test_dynamic_kelly_basic():
    from scripts.v9_adaptive_risk import dynamic_kelly
    res = dynamic_kelly(0.20, regime_factor=1.0,
                           sentiment_factor=0.8, vol_factor=0.7)
    expected = 0.20 * 1.0 * 0.8 * 0.7  # 0.112
    assert abs(res["adjusted_kelly"] - expected) < 0.001


def test_dynamic_kelly_capped():
    from scripts.v9_adaptive_risk import dynamic_kelly
    res = dynamic_kelly(0.5, regime_factor=2.0, sentiment_factor=2.0,
                           vol_factor=2.0)
    assert res["adjusted_kelly"] == 0.5  # capped


def test_correlation_aware_empty():
    from scripts.v9_adaptive_risk import correlation_aware_sizing
    res = correlation_aware_sizing(0.5, [])
    assert res["size_factor"] == 1.0
    assert res["reason"] == "no_correlations"


def test_correlation_aware_low():
    from scripts.v9_adaptive_risk import correlation_aware_sizing
    res = correlation_aware_sizing(0.5, [0.1, 0.2, 0.3])
    assert res["size_factor"] == 1.0
    assert res["reason"] == "low_correlation"


def test_correlation_aware_high():
    from scripts.v9_adaptive_risk import correlation_aware_sizing
    res = correlation_aware_sizing(0.5, [0.6, 0.7, 0.8])
    assert res["size_factor"] < 1.0
    assert "high_correlation" in res["reason"]


def test_main_runs(capsys):
    from scripts.v9_adaptive_risk import main
    exit_code = main(["--target-vol", "8.0", "--current-vol", "12.0",
                       "--base-kelly", "0.20"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ADAPTIVE RISK" in captured.out