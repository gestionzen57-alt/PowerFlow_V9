"""Tests unitaires — MarketCycleDetector + PhaseClassifier (Phase 13.3).

Couvre :
  - extraction défensive des signaux (dict imbriqué, str JSON, champs manquants)
  - détection des 6 phases (accumulation, cassure, trend, distribution,
    climax, retour) + INDETERMINE
  - transitions de phase
  - robustesse R6 (jamais d'exception)
"""
from __future__ import annotations

import json

from core.v9.market_cycle_detector import (
    CLIMAX_VELOCITY,
    CycleSignals,
    MarketCycleDetector,
    MarketPhase,
)
from core.v9.phase_classifier import PhaseClassifier


# ---------- Helpers ----------


def _ctx(
    *,
    velocite: float = 0.0,
    accel: str = "stable",
    compression: str = "neutre",
    coalition_intensity: float = 50.0,
    coalition_trend: str = "stable",
    coalition_age: int = 1,
    coalition_stability: float = 0.3,
    mtf_depth: str = "H1",           # neutre par défaut (ni HTF ni LTF)
    mtf_score: float = 0.0,
    emboitement: bool = False,
    regime: str = "NEUTRE",
    behavior_phase: str | None = None,
    point_rupture: bool = False,
    mrz: bool = False,
    session: str | None = None,
) -> dict:
    """Construit un contexte cognitif imbriqué (structure réelle V9)."""
    ctx: dict = {
        "scene": {
            "cinematique_json": {
                "velocite_moyenne": velocite,
                "acceleration_deceleration": accel,
                "compression_extension": {"etat": compression},
                "angle": 45.0,
                "dispersion_velocite": 0.0,
            },
            "coalitions_json": [{
                "intensite_alignement": coalition_intensity,
                "intensite_trend": coalition_trend,
                "age_bars": coalition_age,
                "stabilite": coalition_stability,
            }],
            "confluences_mtf_json": {
                "coalition_mtf_depth": mtf_depth,
                "coalition_mtf_score": mtf_score,
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


# ---------- Extraction ----------


def test_extract_full_context_richness_4():
    det = MarketCycleDetector()
    sig = det.extract(_ctx())
    # cinematique + coalitions + mtf + regime = 4 familles présentes
    assert sig.signal_richness == 4
    assert isinstance(sig, CycleSignals)


def test_extract_empty_context_neutral_defaults():
    det = MarketCycleDetector()
    sig = det.extract({})
    assert sig.signal_richness == 0
    assert sig.regime_type == "NEUTRE"
    assert sig.acceleration == "stable"
    assert sig.velocity_abs == 0.0


def test_extract_json_string_fields_coerced():
    """Les champs *_json stockés comme str JSON sont décodés (défensif)."""
    det = MarketCycleDetector()
    ctx = {
        "scene": {
            "cinematique_json": json.dumps(
                {"velocite_moyenne": -2.0, "acceleration_deceleration": "acceleration"}
            ),
            "coalitions_json": json.dumps(
                [{"intensite_alignement": 80.0, "intensite_trend": "montante"}]
            ),
        },
    }
    sig = det.extract(ctx)
    assert sig.velocity_abs == 2.0
    assert sig.acceleration == "acceleration"
    assert sig.coalition_intensity == 80.0
    assert sig.coalition_trend == "montante"


def test_extract_garbage_fields_do_not_raise():
    det = MarketCycleDetector()
    ctx = {"scene": {"cinematique_json": "not json {{{", "coalitions_json": 42}}
    sig = det.extract(ctx)  # ne doit pas lever
    assert isinstance(sig, CycleSignals)


def test_extract_velocity_absolute_value():
    det = MarketCycleDetector()
    sig = det.extract(_ctx(velocite=-1.7))
    assert sig.velocity_abs == 1.7


def test_coalition_class_thresholds():
    det = MarketCycleDetector()
    assert det.extract(_ctx(coalition_intensity=70)).coalition_class == "forte"
    assert det.extract(_ctx(coalition_intensity=45)).coalition_class == "moyenne"
    assert det.extract(_ctx(coalition_intensity=20)).coalition_class == "faible"


def test_htf_ltf_flags():
    det = MarketCycleDetector()
    assert det.extract(_ctx(mtf_depth="D1")).is_htf is True
    assert det.extract(_ctx(mtf_depth="M5")).is_ltf is True
    neutral = det.extract(_ctx(mtf_depth="H1"))
    assert neutral.is_htf is False and neutral.is_ltf is False


# ---------- Détection des phases ----------


def test_detect_climax_extreme_velocity():
    det = MarketCycleDetector()
    state = det.detect(_ctx(velocite=CLIMAX_VELOCITY + 0.5))
    assert state.phase == MarketPhase.CLIMAX
    assert state.confidence > 0.5


def test_detect_climax_behavioral():
    det = MarketCycleDetector()
    state = det.detect(_ctx(
        behavior_phase="culmination", accel="acceleration", compression="extension",
    ))
    assert state.phase == MarketPhase.CLIMAX


def test_detect_cassure_regime():
    det = MarketCycleDetector()
    assert det.detect(_ctx(regime="CASSURE")).phase == MarketPhase.CASSURE


def test_detect_cassure_point_de_rupture():
    det = MarketCycleDetector()
    assert det.detect(_ctx(point_rupture=True)).phase == MarketPhase.CASSURE


def test_detect_cassure_initiation_extension_acceleration():
    det = MarketCycleDetector()
    state = det.detect(_ctx(
        behavior_phase="initiation", compression="extension", accel="acceleration",
    ))
    assert state.phase == MarketPhase.CASSURE


def test_detect_trend_regime_extension():
    det = MarketCycleDetector()
    assert det.detect(_ctx(regime="EXTENSION")).phase == MarketPhase.TREND


def test_detect_trend_developpement():
    det = MarketCycleDetector()
    state = det.detect(_ctx(
        behavior_phase="developpement", coalition_trend="montante", accel="stable",
    ))
    assert state.phase == MarketPhase.TREND


def test_detect_distribution_culmination():
    det = MarketCycleDetector()
    # culmination sans accélération/extension → épuisement, pas climax
    state = det.detect(_ctx(behavior_phase="culmination", accel="stable"))
    assert state.phase == MarketPhase.DISTRIBUTION


def test_detect_distribution_rejet():
    det = MarketCycleDetector()
    assert det.detect(_ctx(regime="REJET")).phase == MarketPhase.DISTRIBUTION


def test_detect_retour_equilibre():
    det = MarketCycleDetector()
    assert det.detect(_ctx(regime="RETOUR_EQUILIBRE")).phase == MarketPhase.RETOUR


def test_detect_retour_resolution():
    det = MarketCycleDetector()
    assert det.detect(_ctx(behavior_phase="resolution")).phase == MarketPhase.RETOUR


def test_detect_accumulation_palier():
    det = MarketCycleDetector()
    assert det.detect(_ctx(regime="PALIER")).phase == MarketPhase.ACCUMULATION


def test_detect_accumulation_compression_default():
    det = MarketCycleDetector()
    state = det.detect(_ctx(compression="compression"))
    assert state.phase == MarketPhase.ACCUMULATION


def test_detect_indetermine_empty_context():
    det = MarketCycleDetector()
    state = det.detect({})
    assert state.phase == MarketPhase.INDETERMINE
    assert state.confidence == 0.0


# ---------- Transitions ----------


def test_transition_recorded():
    det = MarketCycleDetector()
    state = det.detect(_ctx(regime="CASSURE"), previous_phase=MarketPhase.ACCUMULATION)
    assert state.transition == "accumulation→cassure"
    assert state.previous_phase == MarketPhase.ACCUMULATION


def test_transition_none_when_same_phase():
    det = MarketCycleDetector()
    state = det.detect(_ctx(regime="PALIER"), previous_phase="accumulation")
    assert state.transition is None


def test_detect_never_raises_on_bad_input():
    det = MarketCycleDetector()
    for bad in (None, "x", 123, [], {"scene": "nope"}):
        state = det.detect(bad)  # type: ignore[arg-type]
        assert state.phase in set(MarketPhase)


# ---------- Classifieur pur ----------


def test_classifier_indetermine_on_zero_richness():
    clf = PhaseClassifier()
    phase, conf, reasons = clf.classify(CycleSignals(signal_richness=0))
    assert phase == MarketPhase.INDETERMINE
    assert conf == 0.0


def test_classifier_state_to_dict_serializable():
    det = MarketCycleDetector()
    state = det.detect(_ctx(regime="EXTENSION"))
    d = state.to_dict()
    json.dumps(d)  # ne doit pas lever
    assert d["phase"] == "trend"
