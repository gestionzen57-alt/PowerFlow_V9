"""Tests — replay doctrine realign (23 ACTIVE post 2026-07-15)."""
from __future__ import annotations
from core.v9.config import PRINCIPLE_ACTIVE_IDS

def test_active_ids_count_is_25():
    assert len(PRINCIPLE_ACTIVE_IDS) == 25, (
        f"Attendu 25 ACTIVE (post 2026-07-15 : 5 DORMANT + 3 promus SHADOW→ACTIVE), "
        f"obtenu {len(PRINCIPLE_ACTIVE_IDS)}"
    )

def test_grammar_contexte_is_dormant():
    """2026-07-15 : GRAMMAR_CONTEXTE mis DORMANT (WR 44.7% vs _ADAPTIVE 79.5%)."""
    assert "GRAMMAR_CONTEXTE" not in PRINCIPLE_ACTIVE_IDS

def test_grammar_regime_is_active():
    assert "GRAMMAR_REGIME" in PRINCIPLE_ACTIVE_IDS

def test_grammar_break_is_active():
    assert "GRAMMAR_BREAK" in PRINCIPLE_ACTIVE_IDS

def test_grammar_pullback_is_active():
    assert "GRAMMAR_PULLBACK" in PRINCIPLE_ACTIVE_IDS
