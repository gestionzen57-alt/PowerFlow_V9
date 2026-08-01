"""tests/test_v9_phase77.py — Phase 77 motion CEO 48H (P2.5 audit Perplexity).

Tests pour walk_forward_oos.
"""
import pytest


def test_synthesize_day_trades_default():
    from scripts.v9_walk_forward_oos import synthesize_day_trades
    trades = synthesize_day_trades(day_index=0, n_trades=3, seed=42)
    assert len(trades) == 3
    for t in trades:
        assert "day" in t
        assert "hour" in t
        assert "is_win" in t
        assert "pips" in t


def test_synthesize_day_trades_seed_reproducible():
    from scripts.v9_walk_forward_oos import synthesize_day_trades
    t1 = synthesize_day_trades(day_index=0, n_trades=3, seed=42)
    t2 = synthesize_day_trades(day_index=0, n_trades=3, seed=42)
    assert t1 == t2


def test_synthesize_day_trades_filter_in_window():
    """Verifie que hour_filter accepte les trades entre bornes."""
    from scripts.v9_walk_forward_oos import synthesize_day_trades
    # 200 trades, hour_filter large 0-23 (toutes heures valides)
    trades = synthesize_day_trades(
        day_index=0, n_trades=200,
        hour_filter=(0, 23), wr=0.85, seed=42,
    )
    wins = sum(1 for t in trades if t["is_win"])
    assert wins / len(trades) > 0.7  # toutes heures valides = WR ~85%


def test_compute_sharpe_constant():
    from scripts.v9_walk_forward_oos import compute_sharpe
    # Serie constante : std=0, Sharpe=0
    assert compute_sharpe([1.0, 1.0, 1.0]) == 0.0


def test_compute_sharpe_empty():
    from scripts.v9_walk_forward_oos import compute_sharpe
    assert compute_sharpe([]) == 0.0


def test_compute_sharpe_positive():
    from scripts.v9_walk_forward_oos import compute_sharpe
    s = compute_sharpe([1.0, 2.0, 3.0, 4.0, 5.0])
    assert s > 0


def test_compute_sharpe_negative():
    from scripts.v9_walk_forward_oos import compute_sharpe
    s = compute_sharpe([-5.0, -4.0, -3.0, -2.0, -1.0])
    assert s < 0


def test_compute_sortino_empty():
    from scripts.v9_walk_forward_oos import compute_sortino
    assert compute_sortino([]) == 0.0


def test_compute_sortino_all_positive():
    """Sortino = 0 si pas de downside."""
    from scripts.v9_walk_forward_oos import compute_sortino
    s = compute_sortino([1.0, 2.0, 3.0])
    assert s == 0.0


def test_compute_max_drawdown_no_loss():
    from scripts.v9_walk_forward_oos import compute_max_drawdown
    assert compute_max_drawdown([1.0, 2.0, 3.0]) == 0.0


def test_compute_max_drawdown_with_loss():
    from scripts.v9_walk_forward_oos import compute_max_drawdown
    # Gain 5 puis perte 4 puis gain 1 : peak=5, dd au pire=4
    assert compute_max_drawdown([5.0, -4.0, 1.0]) == 4.0


def test_compute_profit_factor_no_loss():
    from scripts.v9_walk_forward_oos import compute_profit_factor
    assert compute_profit_factor([1.0, 2.0, 3.0]) == 0.0


def test_compute_profit_factor_normal():
    from scripts.v9_walk_forward_oos import compute_profit_factor
    # Wins 30, loss 10 : PF = 3.0
    assert compute_profit_factor([10.0, -5.0, 20.0, -5.0]) == 3.0


def test_run_walk_forward_basic():
    from scripts.v9_walk_forward_oos import run_walk_forward
    res = run_walk_forward(
        n_folds=7, fold_days=13, wr=0.85,
        hour_filter=(11, 13), seed=42,
    )
    assert res["n_folds"] == 7
    assert len(res["folds"]) == 7
    assert res["verdict"] in ("PRODUCTION", "NEEDS_TUNING", "FRAGILE", "NOT_EDGE")


def test_run_walk_forward_verdict_production():
    from scripts.v9_walk_forward_oos import (
        run_walk_forward, TRADES_PER_DAY_DEFAULT,
    )
    # Patch temporaire pour plus de trades
    import scripts.v9_walk_forward_oos as wfo
    original = wfo.TRADES_PER_DAY_DEFAULT
    wfo.TRADES_PER_DAY_DEFAULT = 20  # 20 trades/jour = 260/fold = Sharpe stable
    try:
        res = run_walk_forward(
            n_folds=7, fold_days=13, wr=0.95,
            hour_filter=(0, 23), seed=42,
        )
        assert res["verdict"] in ("PRODUCTION", "NEEDS_TUNING")
    finally:
        wfo.TRADES_PER_DAY_DEFAULT = original


def test_run_walk_forward_verdict_not_edge():
    from scripts.v9_walk_forward_oos import run_walk_forward
    # WR 30% : NOT_EDGE
    res = run_walk_forward(
        n_folds=7, fold_days=13, wr=0.30,
        hour_filter=(11, 13), seed=42,
    )
    assert res["verdict"] == "NOT_EDGE"


def test_main_demo(capsys):
    from scripts.v9_walk_forward_oos import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "WALK-FORWARD OOS" in captured.out
    assert "VERDICT" in captured.out