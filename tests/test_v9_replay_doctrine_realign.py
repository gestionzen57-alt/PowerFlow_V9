"""Tests — replay doctrine realign (48 ACTIVE post mandat CEO boucle fermée 2026-07-16)."""
from __future__ import annotations
from core.v9.config import PRINCIPLE_ACTIVE_IDS

def test_active_ids_count_is_48():
    # 22/07 recalibrage : 46 → 41 (6 principes perdants démodulés → SHADOW
    # + GRAMMAR_CROISEMENT_CONFIRMATION ajouté ACTIVE).
    assert len(PRINCIPLE_ACTIVE_IDS) == 41, (
        f"Attendu 41 ACTIVE (22/07 recalibrage), "
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
