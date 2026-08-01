"""tests/test_v9_phase42.py — Phase 42 motion CEO 48h.

Tests pour v9_execution_alpha.
"""
import pytest


def test_estimate_slippage_default():
    from scripts.v9_execution_alpha import estimate_slippage_pips
    res = estimate_slippage_pips(0.5, 1.2, 10.0, "london_ny", 120)
    assert "slippage_pips" in res
    assert res["slippage_pips"] > 0
    assert res["slippage_pips"] < 5.0  # reasonable


def test_estimate_slippage_high_volume():
    from scripts.v9_execution_alpha import estimate_slippage_pips
    res = estimate_slippage_pips(5.0, 1.2, 10.0, "london_ny", 120)
    high_vol = res["slippage_pips"]
    low_vol = estimate_slippage_pips(0.1, 1.2, 10.0, "london_ny", 120)["slippage_pips"]
    assert high_vol > low_vol


def test_estimate_slippage_news_proximity():
    from scripts.v9_execution_alpha import estimate_slippage_pips
    near_news = estimate_slippage_pips(0.5, 1.2, 10.0, "london_ny", 5)
    far_news = estimate_slippage_pips(0.5, 1.2, 10.0, "london_ny", 240)
    assert near_news["slippage_pips"] > far_news["slippage_pips"]
    assert near_news["news_penalty"] == 1.5
    assert far_news["news_penalty"] == 0.0


def test_estimate_slippage_session_asia():
    from scripts.v9_execution_alpha import estimate_slippage_pips
    london = estimate_slippage_pips(0.5, 1.2, 10.0, "london_ny", 120)
    asia = estimate_slippage_pips(0.5, 1.2, 10.0, "asia", 120)
    assert asia["slippage_pips"] > london["slippage_pips"]


def test_estimate_latency_basic():
    from scripts.v9_execution_alpha import estimate_latency_ms
    res = estimate_latency_ms(50.0, 30.0, False)
    assert res["latency_ms"] > 0
    assert res["news_add_ms"] == 0.0


def test_estimate_latency_news():
    from scripts.v9_execution_alpha import estimate_latency_ms
    res = estimate_latency_ms(50.0, 30.0, True)
    assert res["news_add_ms"] == 50.0
    assert res["latency_ms"] > 50


def test_order_flow_neutral():
    from scripts.v9_execution_alpha import order_flow_imbalance
    res = order_flow_imbalance(100.0, 100.0)
    assert res["imbalance"] == 0.0
    assert res["pressure"] == "NEUTRAL"


def test_order_flow_buy_pressure():
    from scripts.v9_execution_alpha import order_flow_imbalance
    res = order_flow_imbalance(1000.0, 100.0)
    assert res["imbalance"] > 0.8
    assert res["pressure"] == "BUY_PRESSURE"


def test_order_flow_sell_pressure():
    from scripts.v9_execution_alpha import order_flow_imbalance
    res = order_flow_imbalance(100.0, 1000.0)
    assert res["imbalance"] < -0.8
    assert res["pressure"] == "SELL_PRESSURE"


def test_order_flow_zero():
    from scripts.v9_execution_alpha import order_flow_imbalance
    res = order_flow_imbalance(0, 0)
    assert res["imbalance"] == 0.0
    assert res["pressure"] == "NEUTRAL"


def test_execution_quality_excellent():
    from scripts.v9_execution_alpha import execution_quality_score
    res = execution_quality_score(0.1, 30.0, 1.0)
    assert res["quality_score"] >= 95
    assert res["grade"] == "A+"


def test_execution_quality_poor():
    from scripts.v9_execution_alpha import execution_quality_score
    res = execution_quality_score(5.0, 200.0, 10.0)
    assert res["quality_score"] < 80
    assert res["grade"] in ["D", "F"]


def test_main_runs(capsys):
    from scripts.v9_execution_alpha import main
    exit_code = main(["--lot", "1.0", "--spread", "1.5",
                       "--atr", "12", "--session", "london_ny",
                       "--news-min", "120"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "EXECUTION ALPHA" in captured.out