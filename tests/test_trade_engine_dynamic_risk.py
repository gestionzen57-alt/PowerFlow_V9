"""Tests d'intégration — hook SHADOW DynamicRiskManager dans TradeEngine
(Phase 13.3).

Vérifie que :
  - le kill switch env pilote l'évaluation shadow
  - la RiskDecision est JSON-sérialisable (elle entre dans result["dynamic_risk"])
  - l'évaluation shadow ne lève jamais (R6) et reste purement additive (R2 :
    ne modifie pas le SL/TP appliqué)
"""
from __future__ import annotations

import json

from core.v9.dynamic_risk_manager import DynamicRiskManager
from core.v9.trade_engine import _dynamic_risk_enabled


def _ctx(regime: str = "EXTENSION", mtf_depth: str = "D1") -> dict:
    return {
        "scene": {
            "cinematique_json": {
                "velocite_moyenne": 0.01,
                "acceleration_deceleration": "acceleration",
                "compression_extension": {"etat": "neutre"},
            },
            "coalitions_json": [{
                "intensite_alignement": 65.0,
                "intensite_trend": "montante",
                "age_bars": 2,
            }],
            "confluences_mtf_json": {
                "coalition_mtf_depth": mtf_depth,
                "emboitement_detecte": True,
            },
        },
        "behavior": {"phase": "developpement"},
        "regime": [{"regime_type": regime}],
    }


# ---------- Kill switch ----------


def test_dynamic_risk_enabled_default_on(monkeypatch):
    monkeypatch.delenv("V9_DYNAMIC_RISK_ENABLED", raising=False)
    assert _dynamic_risk_enabled() is True


def test_dynamic_risk_disabled_by_env(monkeypatch):
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "0")
    assert _dynamic_risk_enabled() is False


def test_dynamic_risk_enabled_explicit_on(monkeypatch):
    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "1")
    assert _dynamic_risk_enabled() is True


# ---------- Contrat de sortie (shadow → result["dynamic_risk"]) ----------


def test_risk_decision_is_json_serializable():
    """result["dynamic_risk"] doit pouvoir entrer dans un diagnostic JSON."""
    drm = DynamicRiskManager()
    decision = drm.evaluate(_ctx(), decision={
        "tp_pips": 8.0, "sl_pips": 15.0, "strategy": "DYNAMIC",
        "session_marche": "london",
    })
    payload = decision.to_dict()
    dumped = json.dumps(payload)          # ne doit pas lever
    assert "phase" in json.loads(dumped)


def test_shadow_decision_carries_expected_contract_keys():
    drm = DynamicRiskManager()
    payload = drm.evaluate(_ctx(), decision={"session_marche": "london"}).to_dict()
    for key in (
        "tp_pips", "sl_pips", "rr_ratio", "exit_strategy", "allow_new_position",
        "phase", "phase_confidence", "source", "session_tradable", "modulation",
    ):
        assert key in payload


def test_shadow_evaluation_is_additive_not_applied():
    """Le SL/TP dynamique diffère du SL/TP courant sans le modifier :
    l'appelant garde la main (SHADOW). On vérifie juste que l'évaluation
    produit une décision cohérente sans toucher au dict d'entrée."""
    drm = DynamicRiskManager()
    current = {"tp_pips": 8.0, "sl_pips": 15.0, "session_marche": "london"}
    before = dict(current)
    decision = drm.evaluate(_ctx(), decision=current)
    assert current == before                       # entrée non mutée
    assert decision.source == "dynamic"
    assert decision.phase == "trend"


def test_shadow_evaluation_never_raises_on_missing_context():
    drm = DynamicRiskManager()
    decision = drm.evaluate(None, decision={"tp_pips": 8.0, "sl_pips": 15.0})
    assert decision.source == "fallback"
    assert decision.tp_pips == 8.0
