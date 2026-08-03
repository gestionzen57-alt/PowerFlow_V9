"""Tests — replay doctrine realign (47 ACTIVE post mandat CEO boucle fermée 2026-08-04)."""
from __future__ import annotations
from core.v9.config import PRINCIPLE_ACTIVE_IDS

def test_active_ids_count_is_47():
    # 22/07 recalibrage : 46 → 41 (6 principes perdants démodulés → SHADOW
    # + GRAMMAR_CROISEMENT_CONFIRMATION ajouté ACTIVE).
    # 04/08 mise à jour : 41 → 47 (6 nouveaux principes ACTIVE ajoutés
    # par sprints V3/V4/V5 CEO no-stop).
    assert len(PRINCIPLE_ACTIVE_IDS) == 47, (
        f"Attendu 47 ACTIVE (04/08 sprint CEO V3+V4+V5), "
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
