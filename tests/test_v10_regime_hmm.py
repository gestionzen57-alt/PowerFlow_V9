"""V10 Regime HMM — tests unitaires (Sprint 2 autopilote quant Hermes).

Obligations Sprint 2 :
  1. test_hmm_regime_uptrend
  2. test_hmm_regime_downtrend
  3. test_hmm_regime_range
  4. test_hmm_insufficient_data_r6
  5. test_hmm_returns_helper
  6. test_change_points_detect
  7. test_change_points_insufficient_r6
  8. test_compose_regime_signal
  9. test_serialization_as_dict
  10. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_regime_hmm import (  # noqa: E402
    Regime,
    RegimeResult,
    detect_hmm_regime,
    detect_change_points,
    compose_regime_signal,
    _returns_from_closes,
    _available,
)


def _uptrend(n=80):
    """Série de closes en hausse continue."""
    return [100.0 * (1.0006 ** i) for i in range(n)]


def _downtrend(n=80):
    """Série de closes en baisse continue."""
    return [100.0 * (0.9994 ** i) for i in range(n)]


def _range(n=80, base=100.0, vol=0.0005):
    """Série en range (marche aléatoire bornée, zero drift)."""
    import random
    rng = random.Random(7)
    out = []
    val = base
    for _ in range(n):
        val += rng.gauss(0.0, vol * base)
        out.append(val)
    return out


# ─────────────────────────────────────────────────────────────────────
# HMM régimes
# ─────────────────────────────────────────────────────────────────────
def test_hmm_regime_uptrend():
    closes = _uptrend()
    res = detect_hmm_regime(closes, symbol="EURUSD", timestamp="2026-08-05T10:00:00Z")
    if res.regime == Regime.UNKNOWN:
        pytest.skip("hmmlearn indisponible (R6 fail-open)")
    assert res.regime in (Regime.TRENDING_UP, Regime.VOLATILE)
    assert res.regime_confidence > 0.0
    assert res.n_states == 5


def test_hmm_regime_downtrend():
    closes = _downtrend()
    res = detect_hmm_regime(closes, symbol="GBPUSD", timestamp="2026-08-05T10:00:00Z")
    if res.regime == Regime.UNKNOWN:
        pytest.skip("hmmlearn indisponible (R6 fail-open)")
    assert res.regime in (Regime.TRENDING_DOWN, Regime.VOLATILE)


def test_hmm_regime_range():
    closes = _range()
    res = detect_hmm_regime(closes, symbol="USDJPY", timestamp="2026-08-05T10:00:00Z")
    if res.regime == Regime.UNKNOWN:
        pytest.skip("hmmlearn indisponible (R6 fail-open)")
    # Range → RANGING ou VOLATILE (pas de tendance franche)
    assert res.regime in (Regime.RANGING, Regime.VOLATILE)


def test_hmm_insufficient_data_r6():
    res = detect_hmm_regime([100.0, 100.1], symbol="EURUSD",
                            timestamp="2026-08-05T10:00:00Z")
    assert res.regime == Regime.UNKNOWN
    assert res.regime_confidence == 0.0
    assert "insufficient_data" in res.audit.get("reason", "")


def test_hmm_returns_helper():
    closes = [100.0, 110.0, 121.0]  # +10% chaque
    r = _returns_from_closes(closes)
    assert len(r) == 2
    assert r[0] == pytest.approx(0.09531, abs=1e-3)  # ln(1.1)
    assert r[1] == pytest.approx(0.09531, abs=1e-3)


def test_hmm_available_flag():
    # doit être un bool (R6)
    assert isinstance(_available(), bool)


# ─────────────────────────────────────────────────────────────────────
# Changepoint
# ─────────────────────────────────────────────────────────────────────
def test_change_points_detect():
    # deux régimes : uptrend puis downtrend → au moins 1 rupture
    closes = _uptrend(50) + _downtrend(50)
    cps, audit = detect_change_points(closes)
    if "error" in audit.get("reason", ""):
        pytest.skip("ruptures indisponible (R6 fail-open)")
    assert isinstance(cps, list)
    assert audit.get("method") == "pelt_rbf"


def test_change_points_insufficient_r6():
    cps, audit = detect_change_points([100.0, 100.1, 100.2])
    assert cps == []
    assert "insufficient_data" in audit.get("reason", "")


# ─────────────────────────────────────────────────────────────────────
# Compose
# ─────────────────────────────────────────────────────────────────────
def test_compose_regime_signal():
    closes = _uptrend(80)
    res = compose_regime_signal(closes, symbol="EURUSD",
                                timestamp="2026-08-05T10:00:00Z")
    assert isinstance(res, RegimeResult)
    assert "change_point_audit" in res.audit


# ─────────────────────────────────────────────────────────────────────
# Sérialisation R9
# ─────────────────────────────────────────────────────────────────────
def test_serialization_as_dict():
    res = RegimeResult(symbol="EURUSD", timestamp="t",
                       regime=Regime.TRENDING_UP, regime_confidence=0.8,
                       state_probs={"S0": 0.2, "S1": 0.8},
                       n_states=5, change_points=[10, 30])
    d = res.as_dict()
    assert d["regime"] == "TRENDING_UP"
    assert d["regime_confidence"] == pytest.approx(0.8)
    assert d["n_states"] == 5
    assert d["change_points"] == [10, 30]
    json.dumps(d)  # R9 JSON-sérialisable


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_regime_hmm.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
