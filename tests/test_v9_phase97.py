"""tests/test_v9_phase97.py — Phase 97 motion CEO 48H (Plan C).

Tests pour quantum_portfolio_optimizer.
"""
import pytest


def test_create_portfolio():
    from scripts.v9_quantum_portfolio_optimizer import Portfolio
    p = Portfolio({"a": 100.0, "b": 50.0})
    assert p.weights == {"a": 100.0, "b": 50.0}


def test_portfolio_normalize():
    from scripts.v9_quantum_portfolio_optimizer import Portfolio
    p = Portfolio({"a": 100.0, "b": 100.0})
    norm = p.normalize()
    s = sum(norm.values())
    assert abs(s - 1.0) < 1e-6


def test_portfolio_total():
    from scripts.v9_quantum_portfolio_optimizer import Portfolio
    p = Portfolio({"a": 100.0, "b": 200.0})
    assert p.total() == 300.0


def test_compute_portfolio_sharpe_basic():
    from scripts.v9_quantum_portfolio_optimizer import (
        compute_portfolio_sharpe,
    )
    # 2 actifs correles negativement : sharpe eleve
    returns = {
        "a": [0.01, 0.02, -0.01, 0.03, 0.02],
        "b": [-0.01, -0.02, 0.01, -0.03, -0.02],
    }
    weights = {"a": 0.5, "b": 0.5}
    s = compute_portfolio_sharpe(returns, weights)
    assert isinstance(s, float)


def test_compute_portfolio_sharpe_zero_variance():
    from scripts.v9_quantum_portfolio_optimizer import (
        compute_portfolio_sharpe,
    )
    returns = {"a": [0.01] * 10}
    weights = {"a": 1.0}
    s = compute_portfolio_sharpe(returns, weights)
    # variance = 0, sharpe = 0
    assert s == 0.0


def test_optimize_portfolio_uniform():
    from scripts.v9_quantum_portfolio_optimizer import optimize_portfolio
    returns = {
        "a": [0.01, 0.02, -0.01, 0.03],
        "b": [-0.01, 0.01, 0.02, -0.02],
    }
    weights = optimize_portfolio(returns, n_iterations=50)
    assert abs(sum(weights.values()) - 1.0) < 1e-3


def test_optimize_portfolio_returns_weights():
    from scripts.v9_quantum_portfolio_optimizer import optimize_portfolio
    returns = {"a": [0.01, 0.02], "b": [-0.01, 0.01]}
    weights = optimize_portfolio(returns, n_iterations=10)
    assert "a" in weights
    assert "b" in weights


def test_main_demo(capsys):
    from scripts.v9_quantum_portfolio_optimizer import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "QUANTUM PORTFOLIO" in captured.out


def test_portfolio_empty():
    from scripts.v9_quantum_portfolio_optimizer import Portfolio
    p = Portfolio({})
    assert p.total() == 0


def test_optimize_portfolio_n_iterations():
    from scripts.v9_quantum_portfolio_optimizer import optimize_portfolio
    returns = {"a": [0.01], "b": [0.02]}
    weights = optimize_portfolio(returns, n_iterations=10)
    # N iterations plus grand = resultat plus stable
    assert all(0 <= w <= 1 for w in weights.values())