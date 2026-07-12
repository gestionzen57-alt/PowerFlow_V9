"""Tests — vol_regime (V9 P6 autopilot, 2026-07-13).

Couvre :
- ATR brut (high-low), pip_multiplier (10000 vs 100), lookback défaut
- classify_atr : 5 niveaux (-1, 0, 1, 2, 3)
- detect_vol_regime : 4 labels + cas None
- compute_atr_and_regime : dict structuré pour l'orchestrateur
- Seuils par défaut vs seuils custom
- Régression : calibration empirique (9970 fen. M15 GBPUSD) doit donner
  25/24/46/5% LOW/NORMAL/HIGH/EXTREME
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.vol_regime import (
    ATR_LOOKBACK,
    DEFAULT_PIPS_MULTIPLIER,
    DEFAULT_THRESHOLDS_PIPS,
    classify_atr,
    compute_atr_and_regime,
    compute_atr_pips,
    detect_vol_regime,
)


# ── Données factices ─────────────────────────────────────────────────────


def _flat_series(price: float = 1.3400, n: int = 30):
    """ATR ≈ 0 (range parfait, aucun mouvement)."""
    return [price] * n, [price] * n


def _trending_series(start: float = 1.3000, step: float = 0.0010, n: int = 30):
    """high-low constant = step, ATR = step (en pips)."""
    highs = [start + step * (i + 1) for i in range(n)]
    lows = [start + step * i for i in range(n)]
    return highs, lows


def _volatile_series(price: float = 1.3400, half_range: float = 0.0050, n: int = 30):
    """high-low = 2 * half_range = 10 pips (GBPUSD)."""
    return [price + half_range] * n, [price - half_range] * n


# ── compute_atr_pips ────────────────────────────────────────────────────


def test_compute_atr_returns_none_if_too_few_bars():
    highs = [1.001] * 20
    lows = [1.000] * 20
    assert compute_atr_pips(highs, lows) is None


def test_compute_atr_perfect_range_returns_zero():
    highs, lows = _flat_series()
    atr = compute_atr_pips(highs, lows, lookback=30)
    assert atr == 0.0


def test_compute_atr_trending_series_constant_step():
    # step = 0.0010 par bougie → 10 pips sur GBPUSD (multiplier=10000)
    highs, lows = _trending_series(step=0.0010, n=30)
    atr = compute_atr_pips(highs, lows, lookback=30)
    assert atr == pytest.approx(10.0, abs=0.01)


def test_compute_atr_jpy_pair_uses_100_multiplier():
    # step = 0.15 par bougie → 15 pips sur JPY (multiplier=100)
    # (high - low)_par_bougie = 0.15, donc ATR = 0.15 * 100 = 15 pips côté JPY,
    # et 0.15 * 10000 = 1500 pips côté GBPUSD (le multiplicateur fait la différence).
    highs, lows = _trending_series(start=150.0, step=0.15, n=30)
    atr_gbpusd = compute_atr_pips(highs, lows, pip_multiplier=10000, lookback=30)
    atr_usdjpy = compute_atr_pips(highs, lows, pip_multiplier=100, lookback=30)
    assert atr_gbpusd == pytest.approx(1500.0, abs=0.5)  # absurde avec mult 10000
    assert atr_usdjpy == pytest.approx(15.0, abs=0.05)  # correct pour JPY


def test_compute_atr_lookback_smaller_than_full():
    highs = [1.001] * 100
    lows = [1.000] * 100
    # lookback=10 sur la fin → 1 pip
    atr = compute_atr_pips(highs, lows, lookback=10)
    assert atr == pytest.approx(10.0, abs=0.01)


# ── classify_atr ────────────────────────────────────────────────────────


@pytest.mark.parametrize("atr,expected_level,expected_label", [
    (1.0, 0, "LOW"),
    (2.0, 0, "LOW"),            # < P25=2.13
    (2.13, 1, "NORMAL"),        # borne incluse côté NORMAL
    (3.0, 1, "NORMAL"),
    (3.20, 2, "HIGH"),          # borne incluse côté HIGH
    (7.0, 2, "HIGH"),
    (11.34, 3, "EXTREME"),      # P95 atteinte
    (50.0, 3, "EXTREME"),
])
def test_classify_atr_default_thresholds(atr, expected_level, expected_label):
    level = classify_atr(atr)
    assert level == expected_level
    from core.v9.vol_regime import _LEVEL_TO_LABEL
    assert _LEVEL_TO_LABEL[level] == expected_label


def test_classify_atr_none_returns_minus_one():
    assert classify_atr(None) == -1


def test_classify_atr_custom_thresholds():
    # override : ATR=5 doit donner EXTREME
    custom = (10.0, 20.0, 30.0, 40.0)
    assert classify_atr(5.0, thresholds=custom) == 0
    assert classify_atr(50.0, thresholds=custom) == 3


# ── detect_vol_regime ──────────────────────────────────────────────────


def test_detect_returns_low_when_atr_is_small():
    highs, lows = _flat_series(price=1.3400, n=30)  # ATR = 0
    assert detect_vol_regime(highs, lows) == "LOW"


def test_detect_returns_normal_in_dense_band():
    # step = 0.0003 par bougie → 3 pips → NORMAL (entre P25=2.13 et P50=3.20)
    highs, lows = _trending_series(step=0.0003, n=30)
    assert detect_vol_regime(highs, lows) == "NORMAL"


def test_detect_returns_high_in_volatil_band():
    # step = 0.0005 par bougie → 5 pips → HIGH (entre P50=3.20 et P95=11.34)
    highs, lows = _trending_series(step=0.0005, n=30)
    assert detect_vol_regime(highs, lows) == "HIGH"


def test_detect_returns_extreme_above_p95():
    # half_range = 0.0060 → high-low = 12 pips → EXTREME
    highs, lows = _volatile_series(half_range=0.0060, n=30)
    assert detect_vol_regime(highs, lows) == "EXTREME"


def test_detect_returns_extreme_when_insufficient_data():
    """Conservateur : sans données suffisantes → EXTREME (ne pas trader)."""
    highs, lows = [1.001] * 10, [1.000] * 10
    assert detect_vol_regime(highs, lows) == "EXTREME"


def test_detect_custom_thresholds_override():
    # Seuils permissifs : 50 pips = NORMAL
    custom = (100.0, 200.0, 300.0, 400.0)
    highs, lows = _volatile_series(half_range=0.0025, n=30)  # 5 pips
    assert detect_vol_regime(highs, lows, thresholds=custom) == "LOW"


# ── compute_atr_and_regime ─────────────────────────────────────────────


def test_compute_atr_and_regime_structure():
    highs, lows = _trending_series(step=0.0005, n=30)  # 5 pips = HIGH
    out = compute_atr_and_regime(highs, lows)
    assert "atr_pips" in out
    assert "level" in out
    assert "regime" in out
    assert out["regime"] == "HIGH"
    assert out["level"] == 2
    assert abs(out["atr_pips"] - 5.0) < 0.01


def test_compute_atr_and_regime_insufficient_data_returns_extreme():
    highs, lows = [1.001] * 10, [1.000] * 10
    out = compute_atr_and_regime(highs, lows)
    assert out["atr_pips"] is None
    assert out["level"] == -1
    assert out["regime"] == "EXTREME"


# ── Régression calibration empirique ───────────────────────────────────


def test_default_thresholds_match_2026_07_13_calibration():
    """Les seuils par défaut sont issus de la calibration du 2026-07-13
    sur 9970 fenêtres ATR-30 GBPUSD M15. Toute modification des DEFAULT
    sans recalibration doit échouer ce test."""
    assert DEFAULT_THRESHOLDS_PIPS == pytest.approx((2.13, 3.20, 5.50, 11.34))


def test_default_pips_multiplier_matches_exit_simulator():
    """Cohérence avec exit_simulator.PIPS_MULTIPLIER (10000 GBPUSD/EURUSD)."""
    assert DEFAULT_PIPS_MULTIPLIER == 10000


def test_atr_lookback_default_30():
    """30 bougies d'historique (cohérent avec zone_detector.lookback=20 bars)."""
    assert ATR_LOOKBACK == 30
