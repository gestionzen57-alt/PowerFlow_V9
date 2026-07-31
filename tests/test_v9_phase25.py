"""tests/test_v9_phase25.py — Phase 25 motion CEO autopilote.

Tests pour VaR + DD recovery + Kelly uncertainty.
"""
import pytest


# === v9_var_live ===

def test_get_paper_trades_pips_db_missing_var(tmp_path):
    from scripts.v9_var_live import get_paper_trades_pips
    assert get_paper_trades_pips(tmp_path / "absent.db") == []


def test_var_insufficient():
    from scripts.v9_var_live import compute_var
    res = compute_var([1.0] * 5)
    assert "error" in res


def test_var_no_losses():
    from scripts.v9_var_live import compute_var
    res = compute_var([25.0] * 20)
    assert "error" in res


def test_var_basic():
    from scripts.v9_var_live import compute_var
    # 90 wins, 10 losses de -8
    pips = [25.0] * 90 + [-8.0] * 10
    res = compute_var(pips, confidence=0.95)
    assert res["n_trades"] == 100
    assert res["n_losses"] == 10
    assert res["var_pips"] <= -7  # au moins proche de -8


def test_var_high_confidence():
    from scripts.v9_var_live import compute_var
    pips = [25.0] * 90 + [-8.0] * 10
    res = compute_var(pips, confidence=0.99)
    # 99% VaR plus extreme que 95%
    res_95 = compute_var(pips, confidence=0.95)
    assert res["var_pips"] <= res_95["var_pips"]


def test_var_cvar_worse():
    """CVaR doit etre pire (plus negatif) que VaR."""
    from scripts.v9_var_live import compute_var
    pips = [25.0] * 90 + [-8.0, -15.0, -20.0]
    res = compute_var(pips, confidence=0.95)
    assert res["cvar_pips"] <= res["var_pips"]


# === v9_dd_recovery_analysis ===

def test_dd_recovery_insufficient():
    from scripts.v9_dd_recovery_analysis import analyze_dd_recovery
    res = analyze_dd_recovery([1.0] * 5)
    assert "error" in res


def test_dd_recovery_no_episodes():
    from scripts.v9_dd_recovery_analysis import analyze_dd_recovery
    res = analyze_dd_recovery([25.0] * 50, dd_threshold=100.0)
    assert res["n_episodes"] == 0


def test_dd_recovery_basic():
    from scripts.v9_dd_recovery_analysis import analyze_dd_recovery
    # 10 wins puis 5 losses (-8*5=-40 = DD 40) puis 20 wins
    pips = [25.0] * 10 + [-8.0] * 5 + [25.0] * 20
    res = analyze_dd_recovery(pips, dd_threshold=10.0)
    assert res["n_episodes"] >= 1


# === v9_kelly_uncertainty ===

def test_get_paper_trades_results_db_missing_kelly(tmp_path):
    from scripts.v9_kelly_uncertainty import get_paper_trades_results
    assert get_paper_trades_results(tmp_path / "absent.db") == (0, 0)


def test_kelly_uncertainty_no_data():
    from scripts.v9_kelly_uncertainty import kelly_with_uncertainty
    res = kelly_with_uncertainty(0, 0)
    assert "error" in res


def test_kelly_uncertainty_distribution():
    from scripts.v9_kelly_uncertainty import kelly_with_uncertainty
    res = kelly_with_uncertainty(n_wins=70, n_losses=4, n_sims=100, seed=42)
    assert "kelly_mean" in res
    assert res["kelly_mean"] > 0


def test_kelly_uncertainty_positive_skew():
    """WR elevee → Kelly eleve."""
    from scripts.v9_kelly_uncertainty import kelly_with_uncertainty
    res = kelly_with_uncertainty(n_wins=100, n_losses=1, n_sims=50, seed=42)
    assert res["kelly_mean"] > 0.1
    assert res["kelly_p95"] > 0


def test_kelly_uncertainty_low_wr():
    """WR faible → Kelly faible ou nul."""
    from scripts.v9_kelly_uncertainty import kelly_with_uncertainty
    res = kelly_with_uncertainty(n_wins=30, n_losses=70, n_sims=50, seed=42)
    # Kelly devrait etre proche de 0
    assert res["kelly_mean"] < 0.1