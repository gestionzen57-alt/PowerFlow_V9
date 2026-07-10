"""Tests — SIGNAL_OPEN SHADOW (CEO 2026-07-10, proposition meta-agent validée)."""
from __future__ import annotations
from core.v9.principle_engine import load_principles_from_yaml


def test_signal_open_yaml_exists() -> None:
    """Le YAML SIGNAL_OPEN doit exister (créé CEO 2026-07-10, suite proposition meta-agent)."""
    principles = load_principles_from_yaml()
    ids = {p.principle_id for p in principles}
    assert "SIGNAL_OPEN" in ids, "SIGNAL_OPEN manquant dans le catalogue YAML"


def test_signal_open_is_shadow() -> None:
    """SIGNAL_OPEN est SHADOW (R25' — vocabulaire descriptif, pas promotion ACTIVE)."""
    principles = load_principles_from_yaml()
    so = next((p for p in principles if p.principle_id == "SIGNAL_OPEN"), None)
    assert so is not None
    # Vérifie via le YAML brut que status == SHADOW (le moteur ne matérialise
    # peut-être pas le champ status dans l'objet Principle)
    assert so.v9_status == "SHADOW", f"Attendu SHADOW, got {so.v9_status}"


def test_signal_open_has_conditions() -> None:
    """SIGNAL_OPEN doit avoir ≥ 3 conditions réelles (action, confiance, window_status)."""
    principles = load_principles_from_yaml()
    so = next((p for p in principles if p.principle_id == "SIGNAL_OPEN"), None)
    assert so is not None
    assert len(so.conditions) >= 3, (
        f"Attendu ≥ 3 conditions (action, confiance, window_status), "
        f"obtenu {len(so.conditions)}"
    )


def test_signal_open_not_in_active_ids() -> None:
    """SIGNAL_OPEN reste SHADOW, ne doit PAS être dans PRINCIPLE_ACTIVE_IDS.

    Cohérent avec R25' — promotion CEO requise avant ajout à ACTIVE.
    """
    from core.v9.config import PRINCIPLE_ACTIVE_IDS
    assert "SIGNAL_OPEN" not in PRINCIPLE_ACTIVE_IDS