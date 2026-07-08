"""Tests unitaires — GRAMMAR_PULLBACK conditions réelles (Phase 9.8 Phase B, B4).

Transcription des conditions déjà rédigées en note (anomalies #1/#3,
enrichissement 2026-07-06) dans `conditions:` — voir
docs/audit/AUDIT_DOCTRINE_REPORT.md §5.2.
"""

from __future__ import annotations

from core.v9.config import PRINCIPLE_ACTIVE_IDS
from core.v9.principle_engine import evaluate_principle, load_principles_from_yaml

GRAMMAR_PULLBACK_ID = "GRAMMAR_PULLBACK"


def _record():
    for p in load_principles_from_yaml():
        if p.principle_id == GRAMMAR_PULLBACK_ID:
            return p
    raise AssertionError(f"{GRAMMAR_PULLBACK_ID} absent du catalogue YAML")


def _favorable_context(**overrides):
    ctx = {
        "bascule_detectee": False,
        "bascule_intensite": 20.0,
        "persistance_confirmee": True,
    }
    ctx.update(overrides)
    return ctx


def test_grammar_pullback_yaml_has_3_conditions():
    p = _record()
    assert p.kind == "grammar"
    assert len(p.conditions) == 3
    fields = {c["field"] for c in p.conditions}
    assert fields == {"bascule_detectee", "bascule_intensite", "persistance_confirmee"}


def test_grammar_pullback_remains_shadow():
    assert GRAMMAR_PULLBACK_ID not in PRINCIPLE_ACTIVE_IDS


def test_grammar_pullback_triggers_when_all_conditions_met():
    p = _record()
    result = evaluate_principle(p, _favorable_context())
    assert result["triggered"] is True
    assert result["reason"] == "conditions_remplies"


def test_grammar_pullback_does_not_trigger_during_active_bascule():
    """bascule_detectee==True -> pullback sur bascule en cours = piège."""
    p = _record()
    result = evaluate_principle(p, _favorable_context(bascule_detectee=True))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:bascule_detectee"


def test_grammar_pullback_does_not_trigger_on_strong_conflict():
    p = _record()
    result = evaluate_principle(p, _favorable_context(bascule_intensite=45.0))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:bascule_intensite"


def test_grammar_pullback_does_not_trigger_without_persistence():
    p = _record()
    result = evaluate_principle(p, _favorable_context(persistance_confirmee=False))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:persistance_confirmee"
