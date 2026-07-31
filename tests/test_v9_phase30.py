"""tests/test_v9_phase30.py — Phase 30 motion CEO autopilote.

Tests pour token_auto_setup + paper_runner_continuous.
"""
import pytest


# === v9_token_auto_setup ===

def test_create_placeholder_token():
    """create_placeholder_token retourne SHA256 prefixe."""
    from scripts.v9_token_auto_setup import create_placeholder_token
    token = create_placeholder_token()
    assert token.startswith("AUTO_")
    assert "PLACEHOLDER_NOT_REAL" in token
    assert len(token) == len("AUTO_") + 32 + len("_PLACEHOLDER_NOT_REAL")


def test_create_placeholder_token_unique():
    """2 tokens crees a des moments differents sont uniques."""
    from scripts.v9_token_auto_setup import create_placeholder_token
    t1 = create_placeholder_token("test1")
    t2 = create_placeholder_token("test2")
    assert t1 != t2


def test_write_env(tmp_path, monkeypatch):
    """write_env cree le fichier .env avec placeholder."""
    from scripts.v9_token_auto_setup import write_env
    monkeypatch.setattr(
        "scripts.v9_token_auto_setup.TOKENS_ENV",
        tmp_path / "v9_tokens.env",
    )
    path = write_env("AUTO_TEST_TOKEN")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "AUTO_TEST_TOKEN" in content
    assert "PLACEHOLDER" in content


# === v9_paper_runner_continuous ===

def test_kelly_safe_basic():
    from scripts.v9_paper_runner_continuous import kelly_safe
    # WR 80%, RR 3.125 → Kelly = (0.8*4.125-1)/3.125 = 0.736, *0.25 = 0.184
    k = kelly_safe(0.80, rr=3.125, fractional=0.25)
    assert 0.15 < k < 0.25


def test_kelly_safe_low_wr():
    from scripts.v9_paper_runner_continuous import kelly_safe
    # WR 20% → Kelly = (0.2*4.125-1)/3.125 = -0.056, *0.25 = -0.014 → max(0,...) = 0
    k = kelly_safe(0.20, rr=3.125, fractional=0.25)
    assert k == 0.0


def test_kelly_safe_high_wr():
    from scripts.v9_paper_runner_continuous import kelly_safe
    # WR 95% → Kelly ~93%, *0.25 = 0.232 (cap 0.25)
    k = kelly_safe(0.95, rr=3.125, fractional=0.25)
    assert 0.2 < k <= 0.25


def test_kelly_safe_invalid():
    from scripts.v9_paper_runner_continuous import kelly_safe
    assert kelly_safe(0, rr=3.125) == 0.0
    assert kelly_safe(0.5, rr=0) == 0.0


def test_simulate_one_trade_win():
    from scripts.v9_paper_runner_continuous import simulate_one_trade
    # WR 100% → toujours win
    trade = simulate_one_trade(wr=1.0)
    assert trade["is_win"] is True
    assert trade["pips_net"] > 0
    assert trade["close_reason"] == "TP_hit"


def test_simulate_one_trade_loss():
    from scripts.v9_paper_runner_continuous import simulate_one_trade
    # WR 0% → toujours loss
    trade = simulate_one_trade(wr=0.0)
    assert trade["is_win"] is False
    assert trade["pips_net"] < 0
    assert trade["close_reason"] == "SL_hit"


def test_run_loop_small():
    """run_loop avec 50 trades WR 80% → WR proche de 80%."""
    from scripts.v9_paper_runner_continuous import run_loop
    random_seed = 42
    import random
    random.seed(random_seed)
    result = run_loop(n_iterations=50, wr=0.80, sleep_sec=0)
    assert result["n_total"] == 50
    # Avec seed 42, le WR doit etre autour de 80% (variation normale)
    assert 65 <= result["wr_pct"] <= 95
    assert result["expectancy"] > 0


def test_main_runs(capsys):
    """CLI main execute sans erreur."""
    from scripts.v9_paper_runner_continuous import main
    import sys
    exit_code = main(["--n", "10", "--wr", "0.85", "--sleep", "0"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PAPER RUNNER CONTINUOUS" in captured.out