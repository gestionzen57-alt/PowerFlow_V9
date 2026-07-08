"""Tests unitaires — GRAMMAR_BREAK conditions réelles (Phase 9.8 Phase B, B4).

Transcription des conditions déjà rédigées en note (enrichissement 2026-07-06)
dans `conditions:` — voir docs/audit/AUDIT_DOCTRINE_REPORT.md §5.2. Reste
v9_status=SHADOW (aucune promotion ACTIVE dans ce chantier).
"""

from __future__ import annotations

from core.v9.config import PRINCIPLE_ACTIVE_IDS
from core.v9.principle_engine import evaluate_principle, load_principles_from_yaml

GRAMMAR_BREAK_ID = "GRAMMAR_BREAK"


def _record():
    for p in load_principles_from_yaml():
        if p.principle_id == GRAMMAR_BREAK_ID:
            return p
    raise AssertionError(f"{GRAMMAR_BREAK_ID} absent du catalogue YAML")


def _favorable_context(**overrides):
    ctx = {
        "coalition_mtf_score": 3,
        "risk_sentiment": "RISK_ON",
        "coalition_mtf_depth": "H4",
    }
    ctx.update(overrides)
    return ctx


def test_grammar_break_yaml_has_3_conditions():
    p = _record()
    assert p.kind == "grammar"
    assert len(p.conditions) == 3
    fields = {c["field"] for c in p.conditions}
    assert fields == {"coalition_mtf_score", "risk_sentiment", "coalition_mtf_depth"}


def test_grammar_break_remains_shadow():
    """Le refactor B4 écrit des conditions réelles mais ne promeut pas le
    principe : rester SHADOW tant qu'aucune décision Søn n'est tracée
    (règle 25')."""
    assert GRAMMAR_BREAK_ID not in PRINCIPLE_ACTIVE_IDS


def test_grammar_break_triggers_when_all_conditions_met():
    p = _record()
    result = evaluate_principle(p, _favorable_context())
    assert result["triggered"] is True
    assert result["reason"] == "conditions_remplies"


def test_grammar_break_does_not_trigger_without_coalition_coherence():
    p = _record()
    result = evaluate_principle(p, _favorable_context(coalition_mtf_score=1))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:coalition_mtf_score"


def test_grammar_break_does_not_trigger_off_risk_appetite():
    p = _record()
    result = evaluate_principle(p, _favorable_context(risk_sentiment="RISK_OFF"))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:risk_sentiment"


def test_grammar_break_does_not_trigger_without_macro_depth_confirmation():
    p = _record()
    result = evaluate_principle(p, _favorable_context(coalition_mtf_depth="M5"))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:coalition_mtf_depth"
