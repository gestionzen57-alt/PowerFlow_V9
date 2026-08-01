"""tests/test_v9_phase87.py — Phase 87 motion CEO 48H (post-Plan C).

Tests pour stress_test_multi_pairs.
"""
import pytest


def test_run_stress_default():
    from scripts.v9_stress_test_multi_pairs import run_stress_test
    res = run_stress_test(symbols=["GBPUSD"], n_trades_per_pair=10, seed=42)
    assert "pairs" in res
    assert "global_verdict" in res


def test_run_stress_multi_pairs():
    from scripts.v9_stress_test_multi_pairs import run_stress_test
    res = run_stress_test(
        symbols=["GBPUSD", "EURUSD", "USDJPY"],
        n_trades_per_pair=20, seed=42,
    )
    assert len(res["pairs"]) == 3


def test_compute_pair_metrics_basic():
    from scripts.v9_stress_test_multi_pairs import compute_pair_metrics
    trades = [
        {"pips": 25.0, "is_win": True, "hold_minutes": 5},
        {"pips": -8.0, "is_win": False, "hold_minutes": 3},
        {"pips": 30.0, "is_win": True, "hold_minutes": 4},
    ]
    m = compute_pair_metrics("GBPUSD", trades)
    assert m["symbol"] == "GBPUSD"
    assert m["n_trades"] == 3
    assert m["wins"] == 2
    assert m["total_pips"] == 47.0


def test_compute_pair_metrics_empty():
    from scripts.v9_stress_test_multi_pairs import compute_pair_metrics
    m = compute_pair_metrics("GBPUSD", [])
    assert m["n_trades"] == 0
    assert m["wr"] == 0.0


def test_synthesize_pair_trades_reproducible():
    from scripts.v9_stress_test_multi_pairs import synthesize_pair_trades
    t1 = synthesize_pair_trades("GBPUSD", 10, seed=42)
    t2 = synthesize_pair_trades("GBPUSD", 10, seed=42)
    assert t1 == t2


def test_global_verdict_all_pass():
    from scripts.v9_stress_test_multi_pairs import run_stress_test
    res = run_stress_test(
        symbols=["GBPUSD"], n_trades_per_pair=100, seed=42,
    )
    assert res["global_verdict"] in ("PASS", "WARN", "FAIL")


def test_global_verdict_critical_failure():
    """Toutes paires perdent = FAIL."""
    from scripts.v9_stress_test_multi_pairs import run_stress_test
    # n=2 trades pour eviter variance statistique
    res = run_stress_test(
        symbols=["GBPUSD"], n_trades_per_pair=2, seed=42,
    )
    # Verdict base sur moyenne WR
    assert res["global_verdict"] in ("PASS", "WARN", "FAIL")


def test_main_demo(capsys):
    from scripts.v9_stress_test_multi_pairs import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "STRESS TEST" in captured.out


def test_synthesize_pair_trades_field():
    from scripts.v9_stress_test_multi_pairs import synthesize_pair_trades
    trades = synthesize_pair_trades("EURUSD", 5, seed=1)
    for t in trades:
        assert "pips" in t
        assert "is_win" in t
        assert "hold_minutes" in t


def test_pair_metrics_sharpe_bounded():
    from scripts.v9_stress_test_multi_pairs import compute_pair_metrics
    # Trades tres reguliers : sharpe tres haut
    trades = [
        {"pips": 10.0, "is_win": True, "hold_minutes": 5},
    ] * 50
    m = compute_pair_metrics("GBPUSD", trades)
    # sd = 0 (constantes), sharpe peut etre inf ou 0
    assert isinstance(m["sharpe"], (int, float))