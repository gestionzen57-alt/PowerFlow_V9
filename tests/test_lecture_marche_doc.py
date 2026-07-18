"""Tests pour le document de lecture de marché.

2026-07-18 motion CEO « ta lecture de la baisse est vrai c'est une autre
philosophie, peux tu creer un document d'interpretation de lecture de marché ».

Le document doit être pertinent (données V9 réelles), avec exemples
concrets et filosofia claire.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "LECTURE_MARCHE_ASYMETRIE_2026-07-18.md"


def test_document_exists() -> None:
    """Le document doit exister."""
    assert DOC.exists(), f"Document manquant : {DOC}"


def test_document_minimum_length() -> None:
    """Le document doit être substantiel (>10 KB)."""
    assert DOC.stat().st_size > 10_000, (
        f"Document trop court : {DOC.stat().st_size} octets (attendu >10KB)"
    )


def test_document_contains_5_lois() -> None:
    """Le document doit contenir les 5 lois de la lecture asymétrique."""
    content = DOC.read_text(encoding="utf-8")
    expected_lois = [
        "Loi 1",
        "Loi 2",
        "Loi 3",
        "Loi 4",
        "Loi 5",
    ]
    for loi in expected_lois:
        assert loi in content, f"Loi manquante : {loi}"


def test_document_contains_empirical_data() -> None:
    """Le document doit contenir les données empiriques V9."""
    content = DOC.read_text(encoding="utf-8")
    # Vérifie qu'on cite des données concrètes
    assert "GBPUSD" in content
    assert "M1" in content
    assert "M5" in content
    assert "M15" in content
    assert "H1" in content
    # Vérifie qu'on cite des chiffres
    assert "46.2" in content or "+46" in content  # drift haussier
    assert "13.6" in content  # ratio adverse


def test_document_contains_3_profiles() -> None:
    """Le document doit définir 3 profils de marché."""
    content = DOC.read_text(encoding="utf-8")
    assert "Profil A" in content
    assert "Profil B" in content
    assert "Profil C" in content


def test_document_contains_3_concrete_examples() -> None:
    """Le document doit contenir au moins 3 exemples concrets de trades."""
    content = DOC.read_text(encoding="utf-8")
    assert "Exemple 1" in content
    assert "Exemple 2" in content
    assert "Exemple 3" in content
    # Exemples avec dates/heures réels
    assert "01:50" in content  # spike baissier
    assert "19:35" in content  # mouvement haussier
    assert "15:25" in content  # trade baissier short


def test_document_contains_philosophy_section() -> None:
    """Le document doit ouvrir sur une section philosophique."""
    content = DOC.read_text(encoding="utf-8")
    assert "Philosophie" in content or "philosophie" in content
    assert "asymétrie" in content.lower() or "asymetrique" in content.lower()
    # Métaphore filée
    assert "marathonien" in content or "sprinteur" in content
    assert "escalier" in content.lower() or "coup de massue" in content.lower()


def test_document_references_v9_modules() -> None:
    """Le document doit référencer les modules V9 existants."""
    content = DOC.read_text(encoding="utf-8")
    modules = [
        "v9_speed_bias_analyzer.py",
        "v9_bear_perception.py",
        "v9_bear_strategy.py",
        "v9_movement_analyzer.py",
        "arbiter.py",
    ]
    for mod in modules:
        assert mod in content, f"Module manquant : {mod}"


def test_document_decision_framework() -> None:
    """Le document doit présenter un framework décisionnel."""
    content = DOC.read_text(encoding="utf-8")
    assert "ÉTAPE 1" in content or "ETAPE 1" in content
    assert "ÉTAPE 5" in content or "ETAPE 5" in content
    assert "CONTEXTE" in content or "PROFIL" in content


def test_document_doctrine_compliance() -> None:
    """Le document doit référencer la doctrine V9."""
    content = DOC.read_text(encoding="utf-8")
    # Référence à R6, R18, R25' et au profil de risque
    assert "R6" in content or "défensif" in content.lower()
    assert "R18" in content or "LLM" in content
    assert "R25" in content or "kill switch" in content.lower()