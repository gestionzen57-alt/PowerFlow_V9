"""Tests unitaires — DynamicRiskManager + SLTPCalibrator (Phase 13.3).

Couvre :
  - profil SL/TP/exit/trailing/break-even par phase (6 phases)
  - modulation coalition (HTF/LTF, emboîtement, force/faiblesse)
  - garde-fou climax (pas de nouvelle position) et session non tradable
  - fallback statique (phase indéterminée / contexte vide)
  - robustesse R6 (ne lève jamais) + bornes de clamp
"""
from __future__ import annotations

import json
import os

import pytest

from core.v9.dynamic_risk_manager import (
    DYNAMIC_RISK_VERSION,
    SL_MAX,
    TP_MAX,
    DynamicRiskManager,
    RiskDecision,
    SLTPCalibrator,
)
from core.v9.market_cycle_detector import MarketCycleDetector, MarketPhase


@pytest.fixture(autouse=True)
def _disable_human_scalp_default():
    """Ces tests hardcodent les profils PHASE_PROFILES historiques.
    Désactive V9_DRM_HUMAN_PROFILE_ENABLED (défaut ON autopilot CEO J5)
    pour qu'ils ciblent PHASE_PROFILES (motion antérieure aux 7j).
    """
    os.environ["V9_DRM_HUMAN_PROFILE_ENABLED"] = "0"
    yield
    os.environ.pop("V9_DRM_HUMAN_PROFILE_ENABLED", None)


# ---------- Helpers ----------


def _ctx(
    *,
    velocite: float = 0.0,
    accel: str = "stable",
    compression: str = "neutre",
    coalition_intensity: float = 50.0,
    coalition_trend: str = "stable",
    coalition_age: int = 1,
    mtf_depth: str = "H1",
    emboitement: bool = False,
    regime: str = "NEUTRE",
    behavior_phase: str | None = None,
    point_rupture: bool = False,
    mrz: bool = False,
    session: str | None = None,
) -> dict:
    ctx: dict = {
        "scene": {
            "cinematique_json": {
                "velocite_moyenne": velocite,
                "acceleration_deceleration": accel,
                "compression_extension": {"etat": compression},
            },
            "coalitions_json": [{
                "intensite_alignement": coalition_intensity,
                "intensite_trend": coalition_trend,
                "age_bars": coalition_age,
            }],
            "confluences_mtf_json": {
                "coalition_mtf_depth": mtf_depth,
                "emboitement_detecte": emboitement,
            },
        },
        "behavior": {
            "phase": behavior_phase,
            "point_de_rupture_detecte": point_rupture,
        },
        "regime": [{"regime_type": regime, "mean_reversion_zone": mrz}],
    }
    if session:
        ctx["session_marche"] = session
    return ctx


def _decide(**kwargs) -> RiskDecision:
    return DynamicRiskManager().evaluate(_ctx(**kwargs))


# ---------- Profils par phase ----------


def test_accumulation_phase_profile():
    d = _decide(regime="PALIER")
    assert d.phase == "accumulation"
    assert d.exit_strategy == "TP_SL"
    assert d.trailing_activation is None
    assert d.break_even_at is None
    # SL/TP de base (aucune modulation : mtf neutre, coalition moyenne)
    assert d.sl_pips == 10.0
    assert d.tp_pips == 8.0


def test_cassure_phase_trailing_and_break_even():
    d = _decide(regime="CASSURE")
    assert d.phase == "cassure"
    assert d.exit_strategy == "TRAILING"
    assert d.trailing_activation == 0.5   # trailing armé à 50% du TP
    assert d.break_even_at == 0.3          # break-even à 30% du TP
    assert d.trailing_distance is not None
    assert d.sl_pips > 10.0                 # SL large (breakout peut pullback)


def test_trend_phase_break_even_fast():
    d = _decide(regime="EXTENSION")
    assert d.phase == "trend"
    assert d.exit_strategy == "TRAILING"
    assert d.trailing_activation == 0.25   # trailing serré
    assert d.break_even_at == 0.2          # break-even rapide


def test_distribution_phase_break_even_no_trailing():
    d = _decide(behavior_phase="culmination", accel="stable")
    assert d.phase == "distribution"
    assert d.exit_strategy == "TP_SL"
    assert d.trailing_activation is None
    assert d.break_even_at == 0.5          # prendre le profit vite


def test_climax_phase_no_new_position():
    d = _decide(velocite=2.0)
    assert d.phase == "climax"
    assert d.allow_new_position is False   # aucune nouvelle position
    assert d.exit_strategy == "TIME_BASED"


def test_retour_phase_modest_target():
    d = _decide(regime="RETOUR_EQUILIBRE")
    assert d.phase == "retour"
    assert d.exit_strategy == "TP_SL"
    assert d.tp_pips <= d.sl_pips           # objectif modeste, SL large


# ---------- Modulation coalition ----------


def test_htf_coalition_tp_bonus():
    base = _decide(regime="PALIER", mtf_depth="H1")
    htf = _decide(regime="PALIER", mtf_depth="D1")
    assert htf.tp_pips > base.tp_pips
    assert "htf_tp" in htf.modulation
    assert htf.modulation["htf_tp"] == 1.5


def test_ltf_coalition_tp_reduction():
    base = _decide(regime="PALIER", mtf_depth="H1")
    ltf = _decide(regime="PALIER", mtf_depth="M5")
    assert ltf.tp_pips < base.tp_pips
    assert "ltf_tp" in ltf.modulation


def test_multi_tf_aligned_tp_boost():
    base = _decide(regime="EXTENSION", mtf_depth="H1", emboitement=False)
    aligned = _decide(regime="EXTENSION", mtf_depth="H1", emboitement=True)
    assert aligned.tp_pips > base.tp_pips
    assert "mtf_aligned_tp" in aligned.modulation


def test_strong_coalition_tp_bonus():
    d = _decide(regime="EXTENSION", coalition_intensity=75)
    assert d.coalition_class == "forte"
    assert "coalition_strong_tp" in d.modulation


def test_weak_coalition_tp_reduction():
    d = _decide(regime="EXTENSION", coalition_intensity=15)
    assert d.coalition_class == "faible"
    assert "coalition_weak_tp" in d.modulation


def test_modulation_respects_tp_clamp():
    # Toutes les modulations haussières cumulées ne dépassent pas TP_MAX.
    d = _decide(regime="CASSURE", mtf_depth="D1", emboitement=True,
                coalition_intensity=90)
    assert d.tp_pips <= TP_MAX
    assert d.sl_pips <= SL_MAX


# ---------- Session ----------


def test_session_non_tradable_blocks_new_position():
    d = _decide(regime="EXTENSION", session="new_york")
    assert d.session_tradable is False
    assert d.allow_new_position is False


def test_session_tradable_allows_position():
    d = _decide(regime="EXTENSION", session="asie")
    assert d.session_tradable is True
    assert d.allow_new_position is True


# ---------- Fallback / robustesse ----------


def test_fallback_on_empty_context():
    d = DynamicRiskManager().evaluate({}, decision={"tp_pips": 8.0, "sl_pips": 15.0})
    assert d.source == "fallback"
    assert d.tp_pips == 8.0
    assert d.sl_pips == 15.0


def test_fallback_uses_session_profile_when_no_decision():
    d = DynamicRiskManager().evaluate({}, decision={"session_marche": "asie"})
    assert d.source == "fallback"
    # profil DYNAMIC asie = TP 10 / SL 10 (22/07: RR équilibré, was SL 15)
    assert d.tp_pips == 10.0
    assert d.sl_pips == 10.0  # 22/07: was 15.0, RR équilibré


def test_evaluate_never_raises_on_garbage():
    drm = DynamicRiskManager()
    for bad in (None, "x", 123, [], {"scene": 42}):
        d = drm.evaluate(bad)  # type: ignore[arg-type]
        assert isinstance(d, RiskDecision)


def test_rr_ratio_computed():
    d = _decide(regime="CASSURE")
    assert d.rr_ratio == round(d.tp_pips / d.sl_pips, 2)


def test_to_dict_serializable_and_versioned():
    d = _decide(regime="EXTENSION")
    payload = d.to_dict()
    json.dumps(payload)  # ne doit pas lever
    assert payload["dynamic_risk_version"] == DYNAMIC_RISK_VERSION
    assert payload["source"] == "dynamic"


def test_calibrator_indetermine_returns_fallback():
    calib = SLTPCalibrator()
    state = MarketCycleDetector().detect({})   # INDETERMINE
    d = calib.compute(state, session="london")
    assert d.source == "fallback"
    assert d.phase == MarketPhase.INDETERMINE.value


def test_transition_prepended_to_rationale():
    drm = DynamicRiskManager()
    d = drm.evaluate(_ctx(regime="CASSURE"), previous_phase="accumulation")
    assert any("transition accumulation→cassure" in r for r in d.rationale)
