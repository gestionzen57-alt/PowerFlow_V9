"""Tests — SIGNAL_OPEN ACTIVE (promu 2026-07-14, audit ZCode motion CEO « go priorité 1 »)."""
from __future__ import annotations
from core.v9.principle_engine import load_principles_from_yaml


def test_signal_open_yaml_exists() -> None:
    """Le YAML SIGNAL_OPEN doit exister (créé CEO 2026-07-10, suite proposition meta-agent)."""
    principles = load_principles_from_yaml()
    ids = {p.principle_id for p in principles}
    assert "SIGNAL_OPEN" in ids, "SIGNAL_OPEN manquant dans le catalogue YAML"


def test_signal_open_is_active() -> None:
    """SIGNAL_OPEN est ACTIVE depuis 2026-07-14 (motion CEO « go priorité 1 »).
    Promu SHADOW→ACTIVE : conditions réelles écrites, champs contexte PROPAGÉS,
    WIN/LOSS ≥ 50 (8423), P3-WIRE activé. R25' maturité structurelle + décision Søn."""
    principles = load_principles_from_yaml()
    so = next((p for p in principles if p.principle_id == "SIGNAL_OPEN"), None)
    assert so is not None
    assert so.v9_status == "ACTIVE", f"Attendu ACTIVE (promu 2026-07-14), got {so.v9_status}"


def test_signal_open_has_conditions() -> None:
    """SIGNAL_OPEN doit avoir ≥ 2 conditions réelles (window_statut, confiance_qualification).

    Note 2026-07-14 (audit ZCode) : la condition `action == preparer_entree` a été
    retirée car le champ `action` n'est jamais posé dans _load_shared_context (DORMANT).
    Les noms de champs ont été corrigés : window_status→window_statut, confiance→
    confiance_qualification (champs réels posés par principle_engine.py).
    """
    principles = load_principles_from_yaml()
    so = next((p for p in principles if p.principle_id == "SIGNAL_OPEN"), None)
    assert so is not None
    assert len(so.conditions) >= 2, (
        f"Attendu ≥ 2 conditions (window_statut, confiance_qualification), "
        f"obtenu {len(so.conditions)}"
    )
    # Vérifie que les noms de champs correspondent aux vrais champs posés
    field_names = {c["field"] for c in so.conditions}
    assert "window_statut" in field_names, f"window_statut manquant : {field_names}"
    assert "confiance_qualification" in field_names, f"confiance_qualification manquant : {field_names}"
    # Aucun champ DORMANT ne doit rester dans les conditions
    assert "action" not in field_names, "action est DORMANT — ne doit pas être dans conditions"
    assert "window_status" not in field_names, "window_status est une typo — corrigé en window_statut"


def test_signal_open_in_active_ids() -> None:
    """SIGNAL_OPEN est dans PRINCIPLE_ACTIVE_IDS depuis 2026-07-14 (promotion CEO)."""
    from core.v9.config import PRINCIPLE_ACTIVE_IDS
    assert "SIGNAL_OPEN" in PRINCIPLE_ACTIVE_IDS, "SIGNAL_OPEN devrait être ACTIVE"

# ── Tests de déclenchement réel (audit ZCode 2026-07-14) ──────────
# Avant : seuls des tests structurels (existe, SHADOW, a conditions).
# Maintenant : vérifie que SIGNAL_OPEN se déclenche réellement avec
# les bons champs (pas juste "ne crash pas").

from core.v9.principle_engine import evaluate_principle


def _get_signal_open():
    principles = load_principles_from_yaml()
    return next(p for p in principles if p.principle_id == "SIGNAL_OPEN")


def test_signal_open_triggers_with_correct_fields():
    """SIGNAL_OPEN doit se déclencher quand window_statut=exploitable
    ET confiance_qualification >= 70 (les vrais champs posés par
    principle_engine._load_shared_context)."""
    p = _get_signal_open()
    context = {
        "window_statut": "exploitable",
        "confiance_qualification": 75,
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is True, (
        f"Devrait déclencher avec window_statut=exploitable + conf=75 : {result}"
    )


def test_signal_open_does_not_trigger_with_low_confidence():
    """SIGNAL_OPEN ne doit PAS se déclencher si confiance_qualification < 70."""
    p = _get_signal_open()
    context = {
        "window_statut": "exploitable",
        "confiance_qualification": 50,
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is False, (
        f"Ne devrait pas déclencher avec conf=50 < 70 : {result}"
    )


def test_signal_open_does_not_trigger_with_non_exploitable_window():
    """SIGNAL_OPEN ne doit PAS se déclencher si window_statut != exploitable."""
    p = _get_signal_open()
    context = {
        "window_statut": "absente",
        "confiance_qualification": 90,
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is False, (
        f"Ne devrait pas déclencher avec window_statut=absente : {result}"
    )


def test_signal_open_does_not_trigger_with_missing_fields():
    """SIGNAL_OPEN ne doit PAS se déclencher si les champs sont absents
    (dégradation gracieuse R6 — None → False, pas d'exception)."""
    p = _get_signal_open()
    context = {}  # aucun champ
    result = evaluate_principle(p, context)
    assert result["triggered"] is False
