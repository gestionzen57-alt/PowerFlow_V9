"""Tests unitaires — GRAMMAR_CONTEXTE conditions réelles (Phase 9.8 Phase B, B4).

Transcription des conditions de gating déjà rédigées en note (enrichissement
2026-07-06, session 5) dans `conditions:` — voir
docs/audit/AUDIT_DOCTRINE_REPORT.md §5.2 (cas jugé le plus mûr : 17 champs
déjà documentés, tous PROPAGÉS CONTEXT_CONTRACT.md).
"""

from __future__ import annotations

from core.v9.config import PRINCIPLE_ACTIVE_IDS
from core.v9.principle_engine import evaluate_principle, load_principles_from_yaml

GRAMMAR_CONTEXTE_ID = "GRAMMAR_CONTEXTE"


def _record():
    for p in load_principles_from_yaml():
        if p.principle_id == GRAMMAR_CONTEXTE_ID:
            return p
    raise AssertionError(f"{GRAMMAR_CONTEXTE_ID} absent du catalogue YAML")


def _favorable_context(**overrides):
    ctx = {
        "marche_ouvert": True,
        "session_marche": "london",
        "contexte_temporel_fenetre": "mi-session",
    }
    ctx.update(overrides)
    return ctx


def test_grammar_contexte_yaml_has_3_conditions():
    p = _record()
    assert p.kind == "grammar"
    assert len(p.conditions) == 3
    fields = {c["field"] for c in p.conditions}
    assert fields == {"marche_ouvert", "session_marche", "contexte_temporel_fenetre"}


def test_grammar_contexte_is_now_active():
    """2026-07-08 : GRAMMAR_CONTEXTE promu SHADOW→ACTIVE (Phase 13 close).
    2026-07-15 : GRAMMAR_CONTEXTE mis DORMANT (WR 44.7% vs _ADAPTIVE 79.5%),
    remplacé en ACTIVE par GRAMMAR_CONTEXTE_ADAPTIVE."""
    assert GRAMMAR_CONTEXTE_ID not in PRINCIPLE_ACTIVE_IDS


def test_grammar_contexte_triggers_when_all_conditions_met():
    p = _record()
    result = evaluate_principle(p, _favorable_context())
    assert result["triggered"] is True
    assert result["reason"] == "conditions_remplies"


def test_grammar_contexte_does_not_trigger_when_market_closed():
    p = _record()
    result = evaluate_principle(p, _favorable_context(marche_ouvert=False))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:marche_ouvert"


def test_grammar_contexte_does_not_trigger_on_low_liquidity_session():
    p = _record()
    result = evaluate_principle(p, _favorable_context(session_marche="asie"))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:session_marche"


def test_grammar_contexte_does_not_trigger_without_temporal_window():
    p = _record()
    result = evaluate_principle(p, _favorable_context(contexte_temporel_fenetre=None))
    assert result["triggered"] is False
    assert result["reason"] == "condition_non_remplie:contexte_temporel_fenetre"
