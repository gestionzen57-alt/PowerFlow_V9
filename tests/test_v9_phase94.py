"""tests/test_v9_phase94.py — Phase 94 motion CEO 48H (Plan C).

Tests pour multi_broker_arbitrage.
"""
import pytest


def test_fetch_prices():
    from scripts.v9_multi_broker_arbitrage import fetch_prices
    prices = fetch_prices("GBPUSD", ["a", "b"])
    assert "a" in prices
    assert "b" in prices
    assert isinstance(prices["a"], float)


def test_fetch_prices_default_brokers():
    from scripts.v9_multi_broker_arbitrage import (
        fetch_prices, DEFAULT_BROKERS,
    )
    prices = fetch_prices("GBPUSD")
    assert len(prices) == len(DEFAULT_BROKERS)


def test_detect_arbitrage_basic():
    from scripts.v9_multi_broker_arbitrage import (
        detect_arbitrage, fetch_prices,
    )
    prices = {"a": 1.3000, "b": 1.3050}
    opps = detect_arbitrage(prices, min_spread=2.0)
    assert len(opps) == 1
    assert opps[0]["spread_pips"] >= 2.0


def test_detect_arbitrage_no_opportunity():
    from scripts.v9_multi_broker_arbitrage import detect_arbitrage
    prices = {"a": 1.3000, "b": 1.3001}
    opps = detect_arbitrage(prices, min_spread=10.0)
    assert opps == []


def test_detect_arbitrage_profitable():
    from scripts.v9_multi_broker_arbitrage import detect_arbitrage
    prices = {"a": 1.3000, "b": 1.3050}
    opps = detect_arbitrage(prices, min_spread=2.0)
    assert opps[0]["profitable"] is True


def test_rank_opportunities():
    from scripts.v9_multi_broker_arbitrage import (
        rank_opportunities, detect_arbitrage,
    )
    prices = {"a": 1.3000, "b": 1.3050, "c": 1.3100}
    opps = detect_arbitrage(prices, min_spread=2.0)
    ranked = rank_opportunities(opps)
    assert ranked[0]["profit_pips"] >= ranked[-1]["profit_pips"]


def test_execute_arbitrage_profitable():
    from scripts.v9_multi_broker_arbitrage import execute_arbitrage
    opp = {"buy_at": "a", "sell_at": "b", "profit_pips": 4.5, "profitable": True}
    res = execute_arbitrage(opp, lot_size=0.01)
    assert res["executed"] is True
    assert res["profit_usd"] > 0


def test_execute_arbitrage_not_profitable():
    from scripts.v9_multi_broker_arbitrage import execute_arbitrage
    opp = {"profitable": False, "profit_pips": -1.0}
    res = execute_arbitrage(opp)
    assert res["executed"] is False


def test_run_arbitrage_scan_basic():
    from scripts.v9_multi_broker_arbitrage import run_arbitrage_scan
    res = run_arbitrage_scan(["GBPUSD"], ["a", "b"])
    assert "n_symbols" in res
    assert "n_opportunities" in res


def test_run_arbitrage_scan_default():
    from scripts.v9_multi_broker_arbitrage import run_arbitrage_scan
    res = run_arbitrage_scan()
    assert res["n_symbols"] >= 1


def test_main_demo(capsys):
    from scripts.v9_multi_broker_arbitrage import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MULTI-BROKER ARBITRAGE" in captured.out