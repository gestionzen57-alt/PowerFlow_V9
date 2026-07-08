"""Tests unitaires — GRAMMAR_REGIME conditions réelles (Phase 9.8 Phase B, F1/B3).

Verrouillage du correctif : GRAMMAR_REGIME était classé ACTIVE dans
config.PRINCIPLE_ACTIVE_IDS mais structurellement non-émetteur
(`conditions: []`) — voir docs/audit/AUDIT_DOCTRINE_REPORT.md §3.2 friction F1.
Les 4 conditions, déjà rédigées en note depuis 2026-07-06, sont désormais
transcrites dans le YAML.
"""

from __future__ import annotations

from core.v9.principle_engine import evaluate_principle, load_principles_from_yaml

GRAMMAR_REGIME_ID = "GRAMMAR_REGIME"


def _grammar_regime_record():
    for p in load_principles_from_yaml():
        if p.principle_id == GRAMMAR_REGIME_ID:
            return p
    raise AssertionError(f"{GRAMMAR_REGIME_ID} absent du catalogue YAML")


def _favorable_context(**overrides):
    ctx = {
        "risk_sentiment": "RISK_ON",
        "coalition_mtf_score": 3,
        "persistance_confirmee": True,
        "contexte_temporel_fenetre": "mi-session",
    }
    ctx.update(overrides)
    return ctx


def test_grammar_regime_yaml_has_4_conditions():
    p = _grammar_regime_record()
    assert p.kind == "grammar"
    assert len(p.conditions) == 4
    fields = {c["field"] for c in p.conditions}
    assert fields == {
        "risk_sentiment",
        "coalition_mtf_score",
        "persistance_confirmee",
        "contexte_temporel_fenetre",
    }


def test_grammar_regime_condition_ops_match_documented_spec():
    p = _grammar_regime_record()
    by_field = {c["field"]: c for c in p.conditions}
    assert by_field["risk_sentiment"]["op"] == "in"
    assert set(by_field["risk_sentiment"]["value"]) == {"RISK_ON", "RISK_OFF", "MIXTE"}
    assert by_field["coalition_mtf_score"]["op"] == ">="
    assert by_field["coalition_mtf_score"]["value"] == 2
    assert by_field["persistance_confirmee"]["op"] == "=="
    assert by_field["persistance_confirmee"]["value"] is True
    assert by_field["contexte_temporel_fenetre"]["op"] == "is_not_null"


def test_grammar_regime_is_no_longer_structurally_inert():
    """Avant le correctif, evaluate_principle retournait toujours
    entree_documentaire_non_emettrice, quel que soit le contexte."""
    p = _grammar_regime_record()
    result = evaluate_principle(p, _favorable_context())
    assert result["triggered"] is True
    assert result["reason"] == "conditions_remplies"


def test_grammar_regime_does_not_trigger_on_neutre_risk_sentiment():
    p = _grammar_regime_record()
    result = evaluate_principle(p, _favorable_context(risk_sentiment="NEUTRE"))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:risk_sentiment"


def test_grammar_regime_does_not_trigger_without_coalition_coherence():
    p = _grammar_regime_record()
    result = evaluate_principle(p, _favorable_context(coalition_mtf_score=1))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:coalition_mtf_score"


def test_grammar_regime_does_not_trigger_without_temporal_window():
    p = _grammar_regime_record()
    result = evaluate_principle(p, _favorable_context(contexte_temporel_fenetre=None))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:contexte_temporel_fenetre"
