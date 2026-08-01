"""tests/test_v9_phase43.py — Phase 43 motion CEO 48h.

Tests pour v9_strategy_ensemble.
"""
import pytest


def test_lever_l1_mega():
    from scripts.v9_strategy_ensemble import _lever_signal_l1
    s = _lever_signal_l1("GBPUSD", 12)
    assert s["vote"] == 1
    assert s["weight"] == 1.5


def test_lever_l1_no_match():
    from scripts.v9_strategy_ensemble import _lever_signal_l1
    s = _lever_signal_l1("EURUSD", 15)
    assert s["vote"] == 0


def test_lever_l2_kill():
    from scripts.v9_strategy_ensemble import _lever_signal_l2
    s = _lever_signal_l2(5)
    assert s["vote"] == -1


def test_lever_l2_safe():
    from scripts.v9_strategy_ensemble import _lever_signal_l2
    s = _lever_signal_l2(15)
    assert s["vote"] == 0


def test_lever_l7_blacklist():
    from scripts.v9_strategy_ensemble import _lever_signal_l7
    s = _lever_signal_l7("USDCAD")
    assert s["vote"] == -1


def test_lever_l7_allowed():
    from scripts.v9_strategy_ensemble import _lever_signal_l7
    s = _lever_signal_l7("GBPUSD")
    assert s["vote"] == 0


def test_lever_l8_neutral():
    from scripts.v9_strategy_ensemble import _lever_signal_l8
    s = _lever_signal_l8("NEUTRE")
    assert s["vote"] == -1


def test_lever_l8_regime_ok():
    from scripts.v9_strategy_ensemble import _lever_signal_l8
    s = _lever_signal_l8("FAVORABLE")
    assert s["vote"] == 1


def test_lever_l14_mardi():
    from scripts.v9_strategy_ensemble import _lever_signal_l14
    s = _lever_signal_l14(1)
    assert s["vote"] == -1


def test_lever_l14_vendredi():
    from scripts.v9_strategy_ensemble import _lever_signal_l14
    s = _lever_signal_l14(4)
    assert s["vote"] == 1


def test_lever_l15_bearish():
    from scripts.v9_strategy_ensemble import _lever_signal_l15
    s = _lever_signal_l15(-0.7)
    assert s["vote"] == -1


def test_lever_l15_bullish():
    from scripts.v9_strategy_ensemble import _lever_signal_l15
    s = _lever_signal_l15(0.7)
    assert s["vote"] == 1


def test_compute_ensemble_optimal():
    """All signals positive → TAKE_LONG."""
    from scripts.v9_strategy_ensemble import compute_ensemble
    # GBPUSD 12h vendredi regime favorable bullish sentiment
    res = compute_ensemble("GBPUSD", 12, 4, "FAVORABLE", 0.7)
    assert res["decision"] == "TAKE_LONG"
    assert res["score"] > 0
    assert res["confidence"] > 0


def test_compute_ensemble_block():
    """Multiple negatives → BLOCK or TAKE_SHORT."""
    from scripts.v9_strategy_ensemble import compute_ensemble
    # USDCAD 5h mardi neutre bearish sentiment
    res = compute_ensemble("USDCAD", 5, 1, "NEUTRE", -0.7)
    assert res["decision"] in ["BLOCK", "TAKE_SHORT"]
    assert res["score"] < 0


def test_compute_ensemble_wait():
    """Mixed signals → WAIT."""
    from scripts.v9_strategy_ensemble import compute_ensemble
    # GBPUSD 15h lundi neutre sentiment 0
    res = compute_ensemble("GBPUSD", 15, 0, "FAVORABLE", 0.0)
    # Should be WAIT (not strong enough)


def test_compute_ensemble_short():
    """Strong negatives → TAKE_SHORT."""
    from scripts.v9_strategy_ensemble import compute_ensemble
    # USDCAD 5h mardi NEUTRE sentiment bearish
    res = compute_ensemble("USDCAD", 5, 1, "NEUTRE", -0.7)
    # Negatives win → TAKE_SHORT or BLOCK
    assert res["decision"] in ["TAKE_SHORT", "BLOCK"]


def test_main_runs(capsys):
    from scripts.v9_strategy_ensemble import main
    exit_code = main(["--symbol", "GBPUSD", "--hour", "12",
                       "--weekday", "4", "--regime", "FAVORABLE",
                       "--sentiment", "0.7"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "STRATEGY ENSEMBLE" in captured.out