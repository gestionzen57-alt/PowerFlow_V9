"""Tests — replay doctrine realign (48 ACTIVE post mandat CEO boucle fermée 2026-07-16)."""
from __future__ import annotations
from core.v9.config import PRINCIPLE_ACTIVE_IDS

def test_active_ids_count_is_48():
    assert len(PRINCIPLE_ACTIVE_IDS) == 48, (
        f"Attendu 48 ACTIVE (mandat CEO boucle fermee 2026-07-16), "
        f"obtenu {len(PRINCIPLE_ACTIVE_IDS)}"
    )

def test_grammar_contexte_is_active():
    """2026-07-16 : GRAMMAR_CONTEXTE promu ACTIVE (mandat CEO boucle fermée)."""
    assert "GRAMMAR_CONTEXTE" in PRINCIPLE_ACTIVE_IDS

def test_grammar_regime_is_active():
    assert "GRAMMAR_REGIME" in PRINCIPLE_ACTIVE_IDS

def test_grammar_break_is_active():
    assert "GRAMMAR_BREAK" in PRINCIPLE_ACTIVE_IDS

def test_grammar_pullback_is_active():
    assert "GRAMMAR_PULLBACK" in PRINCIPLE_ACTIVE_IDS
