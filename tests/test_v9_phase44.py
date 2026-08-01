"""tests/test_v9_phase44.py — Phase 44 motion CEO 48h.

Tests pour v9_market_microstructure.
"""
import pytest


def test_order_book_imbalance_zero():
    from scripts.v9_market_microstructure import order_book_imbalance
    res = order_book_imbalance(100, 100)
    assert res["imbalance"] == 0.0
    assert res["pressure"] == "NEUTRAL"


def test_order_book_imbalance_strong_bid():
    from scripts.v9_market_microstructure import order_book_imbalance
    res = order_book_imbalance(1000, 200)
    assert res["imbalance"] > 0.4
    assert res["pressure"] == "STRONG_BID"


def test_order_book_imbalance_strong_ask():
    from scripts.v9_market_microstructure import order_book_imbalance
    res = order_book_imbalance(100, 1000)
    assert res["imbalance"] < -0.4
    assert res["pressure"] == "STRONG_ASK"


def test_order_book_imbalance_empty():
    from scripts.v9_market_microstructure import order_book_imbalance
    res = order_book_imbalance(0, 0)
    assert res["imbalance"] == 0.0


def test_volume_profile_basic():
    from scripts.v9_market_microstructure import volume_profile
    vp = {"1.2900": 100, "1.2920": 250, "1.2950": 500, "1.2980": 300}
    res = volume_profile(vp)
    assert res["poc"] == "1.2950"  # highest volume
    assert res["total_volume"] == 1150.0


def test_volume_profile_empty():
    from scripts.v9_market_microstructure import volume_profile
    res = volume_profile({})
    assert res["poc"] is None


def test_volume_profile_single_price():
    from scripts.v9_market_microstructure import volume_profile
    res = volume_profile({"1.30": 100})
    assert res["poc"] == "1.30"
    assert res["value_area_low"] == "1.30"


def test_toxicity_neutral():
    from scripts.v9_market_microstructure import trade_flow_toxicity
    res = trade_flow_toxicity(50, 50, 1.0, 1.0)
    assert res["toxicity"] == 0.0
    assert res["informed_side"] == "NEUTRAL"


def test_toxicity_buyers_informed():
    from scripts.v9_market_microstructure import trade_flow_toxicity
    res = trade_flow_toxicity(80, 20, 2.0, 1.0)
    assert res["informed_side"] == "BUYERS"


def test_toxicity_sellers_informed():
    from scripts.v9_market_microstructure import trade_flow_toxicity
    res = trade_flow_toxicity(20, 80, 1.0, 2.0)
    assert res["informed_side"] == "SELLERS"


def test_toxicity_empty():
    from scripts.v9_market_microstructure import trade_flow_toxicity
    res = trade_flow_toxicity(0, 0, 0, 0)
    assert res["toxicity"] == 0.0


def test_micro_alpha_long():
    from scripts.v9_market_microstructure import (
        order_book_imbalance, trade_flow_toxicity, micro_alpha_signal,
    )
    book = order_book_imbalance(1000, 200)  # STRONG_BID
    tox = trade_flow_toxicity(80, 20, 2.0, 1.0)  # BUYERS
    alpha = micro_alpha_signal(book, {}, tox)
    assert alpha["direction"] == "LONG"
    assert alpha["score"] > 0


def test_micro_alpha_short():
    from scripts.v9_market_microstructure import (
        order_book_imbalance, trade_flow_toxicity, micro_alpha_signal,
    )
    book = order_book_imbalance(200, 1000)  # STRONG_ASK
    tox = trade_flow_toxicity(20, 80, 1.0, 2.0)  # SELLERS
    alpha = micro_alpha_signal(book, {}, tox)
    assert alpha["direction"] == "SHORT"


def test_micro_alpha_wait():
    from scripts.v9_market_microstructure import (
        order_book_imbalance, micro_alpha_signal,
    )
    book = order_book_imbalance(100, 100)  # NEUTRAL
    alpha = micro_alpha_signal(book, {}, {"informed_side": "NEUTRAL"})
    assert alpha["direction"] == "WAIT"


def test_main_runs(capsys):
    from scripts.v9_market_microstructure import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MICROSTRUCTURE" in captured.out