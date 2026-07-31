"""tests/test_v9_phase23_quantum.py — Phase 23 motion CEO « EDGE FUND MAX ».

Tests pour Monte Carlo + Kelly + Bayesian posterior.
"""
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest


# === v9_monte_carlo ===

def test_get_paper_trades_pips_db_missing(tmp_path):
    """get_paper_trades_pips sur DB absente → []."""
    from scripts.v9_monte_carlo import get_paper_trades_pips
    assert get_paper_trades_pips(tmp_path / "absent.db") == []


def test_get_paper_trades_pips_with_db(tmp_path):
    """get_paper_trades_pips retourne liste de pips_net."""
    import sqlite3
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        for p in [25.0, 25.0, -8.0, 25.0]:
            conn.execute("INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')", (p,))
        conn.commit()
    from scripts.v9_monte_carlo import get_paper_trades_pips
    pips = get_paper_trades_pips(db)
    assert len(pips) == 4
    assert sum(pips) == pytest.approx(67.0, abs=0.1)


def test_monte_carlo_insufficient_data():
    """monte_carlo_bootstrap avec <10 trades → error."""
    from scripts.v9_monte_carlo import monte_carlo_bootstrap
    res = monte_carlo_bootstrap([1.0] * 5)
    assert "error" in res


def test_monte_carlo_basic():
    """monte_carlo_bootstrap calcule percentiles correctement."""
    from scripts.v9_monte_carlo import monte_carlo_bootstrap
    pips = [25.0] * 70 + [-8.0] * 4  # 74 trades, WR 94.6%
    res = monte_carlo_bootstrap(pips, n_simulations=100, seed=42)
    assert res["n_simulations"] == 100
    assert res["n_trades_bootstrap"] == 74
    assert res["expectancy_mean"] > 0  # edge positif
    assert res["expectancy_p5"] > 0  # P5 > 0
    assert res["ruin_probability_pct"] < 50  # peu de chances de ruine


def test_monte_carlo_seed_deterministic():
    """monte_carlo_bootstrap deterministe avec seed."""
    from scripts.v9_monte_carlo import monte_carlo_bootstrap
    pips = [10.0, -5.0, 8.0, -3.0, 12.0, -6.0, 9.0, -2.0, 11.0, -4.0]
    r1 = monte_carlo_bootstrap(pips, n_simulations=50, seed=42)
    r2 = monte_carlo_bootstrap(pips, n_simulations=50, seed=42)
    assert r1["expectancy_mean"] == r2["expectancy_mean"]


def test_monte_carlo_negative_edge():
    """monte_carlo_bootstrap detecte edge negatif."""
    from scripts.v9_monte_carlo import monte_carlo_bootstrap
    pips = [-5.0] * 50 + [2.0] * 10  # 60 trades, majoritairement pertes
    res = monte_carlo_bootstrap(pips, n_simulations=100, seed=42)
    assert res["expectancy_mean"] < 0  # edge negatif


def test_monte_carlo_ruin_probability():
    """monte_carlo_bootstrap calcule proba de ruine."""
    from scripts.v9_monte_carlo import monte_carlo_bootstrap
    # Trades qui s'effondrent
    pips = [-15.0] * 80 + [5.0] * 20
    res = monte_carlo_bootstrap(pips, n_simulations=100, seed=42)
    assert res["ruin_probability_pct"] > 0


# === v9_kelly_criterion ===

def test_kelly_full_basic():
    """Kelly full = (W*(R+1) - 1) / R pour W=0.6, R=1."""
    from scripts.v9_kelly_criterion import compute_kelly
    res = compute_kelly(0.6, 1.0)
    assert res["kelly_full"] == pytest.approx(0.2, abs=0.01)


def test_kelly_full_high_winrate():
    """Kelly full pour W=0.946, R=25/8=3.125."""
    from scripts.v9_kelly_criterion import compute_kelly
    res = compute_kelly(0.946, 25 / 8)
    # Kelly = (0.946*4.125 - 1) / 3.125 = (3.902 - 1)/3.125 = 0.929
    assert res["kelly_full"] == pytest.approx(0.929, abs=0.01)
    # 1/4 Kelly = 0.232 (< cap 0.25)
    assert res["kelly_fractional"] == pytest.approx(0.232, abs=0.01)
    # Kelly safe = min(0.232, 0.25) = 0.232 (pas capped ici)
    assert res["kelly_safe"] == pytest.approx(0.232, abs=0.01)
    assert res["recommendation"] in ("AGGRESSIVE", "MODERATE")


def test_kelly_negative():
    """Kelly <= 0 si edge negatif."""
    from scripts.v9_kelly_criterion import compute_kelly
    res = compute_kelly(0.4, 1.0)
    assert res["kelly_full"] < 0
    assert res["recommendation"] == "NO_TRADE_NEGATIVE_KELLY"


def test_kelly_out_of_range():
    """Kelly detecte WR hors range."""
    from scripts.v9_kelly_criterion import compute_kelly
    assert "error" in compute_kelly(1.5, 1.0)
    assert "error" in compute_kelly(-0.1, 1.0)


def test_kelly_invalid_rr():
    """Kelly detecte RR invalide."""
    from scripts.v9_kelly_criterion import compute_kelly
    assert "error" in compute_kelly(0.6, 0)
    assert "error" in compute_kelly(0.6, -1)


def test_kelly_fractional_validation():
    """Kelly detecte fractional hors range."""
    from scripts.v9_kelly_criterion import compute_kelly
    assert "error" in compute_kelly(0.6, 1.0, fractional=0)
    assert "error" in compute_kelly(0.6, 1.0, fractional=1.5)


def test_compute_lot_size_basic():
    """compute_lot_size retourne lot coherent."""
    from scripts.v9_kelly_criterion import compute_lot_size
    # 10000 capital, 1% Kelly, 8 SL pips, 10 USD/pip/lot
    # risk = 100 USD / (8 * 10) = 1.25 lot
    res = compute_lot_size(0.01, 10000.0, 8.0)
    assert res["lot_size"] == pytest.approx(1.25, abs=0.01)


def test_kelly_recommendation_levels():
    """Kelly retourne recommendation selon niveau."""
    from scripts.v9_kelly_criterion import compute_kelly
    # Micro
    r = compute_kelly(0.55, 1.0, fractional=0.25)
    assert r["recommendation"] in ("MICRO", "CONSERVATIVE")


# === v9_bayesian_posterior ===

def test_get_paper_trades_results_db_missing(tmp_path):
    """get_paper_trades_results sur DB absente → (0,0)."""
    from scripts.v9_bayesian_posterior import get_paper_trades_results
    assert get_paper_trades_results(tmp_path / "absent.db") == (0, 0)


def test_get_paper_trades_results_with_db(tmp_path):
    """get_paper_trades_results compte wins/losses."""
    import sqlite3
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pips_net REAL, closed_at TEXT
            )
        """)
        for p in [25.0, -8.0, 25.0, -8.0, 25.0]:
            conn.execute(
                "INSERT INTO v9_paper_trades VALUES (NULL, ?, '2026-07-31')",
                (p,),
            )
        conn.commit()
    from scripts.v9_bayesian_posterior import get_paper_trades_results
    w, l = get_paper_trades_results(db)
    assert w == 3
    assert l == 2


def test_beta_pdf_bounds():
    """beta_pdf = 0 hors [0,1]."""
    from scripts.v9_bayesian_posterior import beta_pdf
    assert beta_pdf(-0.1, 2, 2) == 0.0
    assert beta_pdf(1.5, 2, 2) == 0.0
    assert beta_pdf(0.5, 2, 2) > 0  # centre


def test_beta_cdf_monotonic():
    """beta_cdf est monotone croissante."""
    from scripts.v9_bayesian_posterior import beta_cdf_approx
    cdf_03 = beta_cdf_approx(0.3, 5, 5)
    cdf_05 = beta_cdf_approx(0.5, 5, 5)
    cdf_07 = beta_cdf_approx(0.7, 5, 5)
    assert cdf_03 < cdf_05 < cdf_07


def test_beta_cdf_bounds():
    """beta_cdf bornes 0 et 1."""
    from scripts.v9_bayesian_posterior import beta_cdf_approx
    assert beta_cdf_approx(0.0, 5, 5) == 0.0
    assert beta_cdf_approx(1.0, 5, 5) == 1.0


def test_bayesian_no_data():
    """bayesian_posterior avec 0 trades → error."""
    from scripts.v9_bayesian_posterior import bayesian_posterior
    res = bayesian_posterior(0, 0)
    assert "error" in res


def test_bayesian_high_winrate():
    """bayesian_posterior avec WR 100% → posterior concentrated near 1."""
    from scripts.v9_bayesian_posterior import bayesian_posterior
    res = bayesian_posterior(n_wins=100, n_losses=0, threshold=0.60)
    assert res["posterior_mean_wr"] > 0.99
    assert res["p_wr_above_threshold"] > 0.99


def test_bayesian_low_winrate():
    """bayesian_posterior avec WR 0% → posterior concentrated near 0."""
    from scripts.v9_bayesian_posterior import bayesian_posterior
    res = bayesian_posterior(n_wins=0, n_losses=100, threshold=0.60)
    assert res["posterior_mean_wr"] < 0.01
    assert res["p_wr_above_threshold"] < 0.01


def test_bayesian_balanced():
    """bayesian_posterior avec WR 50% → posterior centered around 0.5."""
    from scripts.v9_bayesian_posterior import bayesian_posterior
    res = bayesian_posterior(n_wins=50, n_losses=50, threshold=0.60)
    # Posterior mean ~0.5
    assert 0.4 < res["posterior_mean_wr"] < 0.6
    # P(WR>60%) faible
    assert res["p_wr_above_threshold"] < 0.20


def test_bayesian_default_threshold():
    """bayesian_posterior utilise seuil 60% par defaut."""
    from scripts.v9_bayesian_posterior import bayesian_posterior
    res = bayesian_posterior(n_wins=70, n_losses=4)
    assert res["threshold"] == 0.60