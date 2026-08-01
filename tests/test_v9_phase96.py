"""tests/test_v9_phase96.py — Phase 96 motion CEO 48H (Plan C).

Tests pour hft_module.
"""
import pytest


def test_hft_signal_default():
    from scripts.v9_hft_module import generate_hft_signal
    signal = generate_hft_signal()
    assert "direction" in signal
    assert signal["direction"] in ("LONG", "SHORT", "NEUTRAL")


def test_hft_signal_with_features():
    from scripts.v9_hft_module import generate_hft_signal
    signal = generate_hft_signal(
        spread_pips=0.5, momentum=0.001, vol=0.5,
    )
    assert "edge_bps" in signal


def test_compute_spread_bps():
    from scripts.v9_hft_module import compute_spread_bps
    s = compute_spread_bps(bid=1.3000, ask=1.3001)
    # 0.0001 / 1.30005 * 10000 = 0.7692 ≈ 0.77
    assert s == 0.77


def test_compute_spread_bps_zero():
    from scripts.v9_hft_module import compute_spread_bps
    s = compute_spread_bps(bid=1.3000, ask=1.3000)
    # bid=ask → bid >= ask → return -1
    assert s == -1.0


def test_compute_spread_bps_invalid():
    """Si bid >= ask, retourne -1 (signal invalide)."""
    from scripts.v9_hft_module import compute_spread_bps
    s = compute_spread_bps(bid=1.3001, ask=1.3000)
    assert s == -1.0


def test_estimate_latency_penalty_bps():
    """Latence elevee = penalite plus forte."""
    from scripts.v9_hft_module import estimate_latency_penalty_bps
    p_low = estimate_latency_penalty_bps(latency_ms=1.0)
    p_high = estimate_latency_penalty_bps(latency_ms=100.0)
    assert p_low < p_high


def test_check_hft_feasibility():
    """Edge > fees + latency = feasible."""
    from scripts.v9_hft_module import check_hft_feasibility
    res = check_hft_feasibility(
        edge_bps=10.0, spread_bps=1.0, latency_ms=5.0,
    )
    assert "feasible" in res
    assert res["feasible"] is True


def test_check_hft_feasibility_not_feasible():
    from scripts.v9_hft_module import check_hft_feasibility
    res = check_hft_feasibility(
        edge_bps=0.5, spread_bps=5.0, latency_ms=100.0,
    )
    assert res["feasible"] is False


def test_main_demo(capsys):
    from scripts.v9_hft_module import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "HFT MODULE" in captured.out


def test_generate_hft_signal_bounded():
    from scripts.v9_hft_module import generate_hft_signal
    signal = generate_hft_signal(spread_pips=0.1, momentum=0.01, vol=2.0)
    assert signal["edge_bps"] >= 0


def test_estimate_latency_bounded():
    from scripts.v9_hft_module import estimate_latency_penalty_bps
    p = estimate_latency_penalty_bps(latency_ms=10.0)
    assert p > 0
    assert p < 1000  # pas absurde