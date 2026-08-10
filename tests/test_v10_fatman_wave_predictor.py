"""
tests/test_v10_fatman_wave_predictor.py
Unit tests for v10_fatman_wave_predictor — H7
≥ 8 cases: compression, divergence, neutral, edge cases
"""
import pytest
from core.v10.v10_fatman_wave_predictor import detect_pre_wave, PreWaveAlert


# ── COMPRESSION cases ────────────────────────────────────────────────────────

def test_compression_standard():
    """sigma in [12,20], slope clearly negative over 4 bars → COMPRESSION."""
    history = [20.0, 18.5, 17.0, 15.5, 14.0]  # slope ~ -1.5/bar
    result = detect_pre_wave(history)
    assert result.phase == "COMPRESSION"
    assert result.pre_wave is True
    assert result.sigma_slope_4 < -0.3
    assert 12.0 <= result.sigma_current <= 20.0


def test_compression_boundary_sigma_12():
    """sigma exactly 12 with negative slope → COMPRESSION."""
    history = [16.0, 15.0, 14.0, 13.0, 12.0]
    result = detect_pre_wave(history)
    assert result.phase == "COMPRESSION"
    assert result.pre_wave is True


def test_compression_boundary_sigma_20():
    """sigma exactly 20 with negative slope → COMPRESSION."""
    history = [24.0, 23.0, 22.0, 21.0, 20.0]
    result = detect_pre_wave(history)
    assert result.phase == "COMPRESSION"
    assert result.pre_wave is True


# ── DIVERGENCE cases ─────────────────────────────────────────────────────────

def test_divergence_standard():
    """sigma > 28 → DIVERGENCE regardless of slope."""
    history = [25.0, 27.0, 29.0, 31.0, 33.0]
    result = detect_pre_wave(history)
    assert result.phase == "DIVERGENCE"
    assert result.pre_wave is True
    assert result.sigma_current == 33.0


def test_divergence_boundary_just_above_28():
    """sigma = 28.1 → DIVERGENCE."""
    history = [28.5, 28.3, 28.2, 28.1, 28.1]
    result = detect_pre_wave(history)
    assert result.phase == "DIVERGENCE"
    assert result.pre_wave is True


# ── NEUTRAL cases ─────────────────────────────────────────────────────────────

def test_neutral_sigma_in_range_but_flat_slope():
    """sigma in [12,20] but slope ≥ -0.3 → NEUTRAL."""
    history = [15.0, 15.1, 15.0, 15.1, 15.0]  # essentially flat
    result = detect_pre_wave(history)
    assert result.phase == "NEUTRAL"
    assert result.pre_wave is False


def test_neutral_sigma_below_range():
    """sigma < 12 → NEUTRAL even with negative slope."""
    history = [14.0, 12.5, 11.5, 10.5, 9.5]
    result = detect_pre_wave(history)
    assert result.phase == "NEUTRAL"
    assert result.pre_wave is False


def test_neutral_sigma_between_20_and_28():
    """sigma in (20, 28] → NEUTRAL (not compression, not divergence)."""
    history = [26.0, 25.5, 25.0, 24.5, 24.0]
    result = detect_pre_wave(history)
    assert result.phase == "NEUTRAL"
    assert result.pre_wave is False


# ── EDGE cases ────────────────────────────────────────────────────────────────

def test_empty_history():
    """Empty list → graceful NEUTRAL with zeros."""
    result = detect_pre_wave([])
    assert result.phase == "NEUTRAL"
    assert result.pre_wave is False
    assert result.sigma_current == 0.0
    assert result.force_expected == 0.0


def test_single_value_compression_range():
    """Single value in [12,20] → slope 0 → NEUTRAL (insufficient slope data)."""
    result = detect_pre_wave([15.0])
    assert result.phase == "NEUTRAL"  # slope = 0, not < -0.3
    assert result.pre_wave is False


def test_force_expected_calculation():
    """Verify force_expected = std(last 10) * 2.5."""
    import numpy as np
    history = [10.0, 12.0, 14.0, 13.0, 15.0, 16.0, 14.5, 13.0, 12.5, 12.0]
    result = detect_pre_wave(history)
    expected_force = float(np.std(history[-10:]) * 2.5)
    assert abs(result.force_expected - expected_force) < 1e-9
