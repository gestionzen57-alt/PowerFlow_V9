"""Tests — replay doctrine realign (27 ACTIVE post 2026-07-14)."""
from __future__ import annotations
from core.v9.config import PRINCIPLE_ACTIVE_IDS

def test_active_ids_count_is_27():
    assert len(PRINCIPLE_ACTIVE_IDS) == 27, (
        f"Attendu 27 ACTIVE (9 node_rule + 16 grammar + SIGNAL_OPEN + ADAPTIVE_VOL_GATE), "
        f"obtenu {len(PRINCIPLE_ACTIVE_IDS)}"
    )

def test_grammar_contexte_is_active():
    assert "GRAMMAR_CONTEXTE" in PRINCIPLE_ACTIVE_IDS

def test_grammar_regime_is_active():
    assert "GRAMMAR_REGIME" in PRINCIPLE_ACTIVE_IDS

def test_grammar_break_is_active():
    assert "GRAMMAR_BREAK" in PRINCIPLE_ACTIVE_IDS

def test_grammar_pullback_is_active():
    assert "GRAMMAR_PULLBACK" in PRINCIPLE_ACTIVE_IDS
