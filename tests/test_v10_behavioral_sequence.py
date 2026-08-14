"""Tests Mission 3 -- structure vide detect_behavioral_sequence (R6 fail-open).

Doctrine : NE PAS CODER les patterns sans validation Son (SON_INTERPRETATION.md §6).
Tests verifient que la STRUCTURE est stable :
  - 5 patterns enumere dans BehavioralPattern
  - BehavioralSequenceResult dataclass complet
  - detect_behavioral_sequence() retourne UNKNOWN avec confidence=0
  - R6 fail-open : liste vide, None, listes courtes -> tous OK sans crash
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_vsa import (
    BehavioralPattern,
    BehavioralSequenceResult,
    detect_behavioral_sequence,
    VSAState,
)


def test_behavioral_pattern_enum_values():
    """Les 5 patterns sont enumeres (4 Son + 1 UNKNOWN R6)."""
    expected = {
        "accumulation_x2_to_markup",
        "markup_x3plus_to_distribution",
        "neutral_x3plus_to_markup_strong",
        "upthrust_to_markdown",
        "unknown",
    }
    actual = {p.value for p in BehavioralPattern}
    assert actual == expected, f"Patterns manquants: {expected - actual}"


def test_behavioral_sequence_result_defaults():
    """Dataclass avec defaults R6 fail-open."""
    r = BehavioralSequenceResult()
    assert r.pattern == BehavioralPattern.UNKNOWN
    assert r.confidence == 0.0
    assert r.state_history == []
    assert r.n_bars_analyzed == 0
    assert r.audit == {}


def test_detect_empty_history_returns_unknown():
    """Pas d'historique -> UNKNOWN + audit propre."""
    r = detect_behavioral_sequence([])
    assert r.pattern == BehavioralPattern.UNKNOWN
    assert r.confidence == 0.0
    assert r.state_history == []
    assert r.n_bars_analyzed == 0
    assert r.audit.get("method") == "stub_R6_failopen"
    assert "Mission 3" in r.audit.get("reason", "")


def test_detect_none_history_returns_unknown():
    """None -> UNKNOWN sans crash."""
    r = detect_behavioral_sequence(None)
    assert r.pattern == BehavioralPattern.UNKNOWN
    assert r.n_bars_analyzed == 0
    assert r.state_history == []


def test_detect_short_history_returns_unknown():
    """Historique insuffisant -> UNKNOWN, conserve la fenetre."""
    r = detect_behavioral_sequence(["MARKUP"], window=5)
    assert r.pattern == BehavioralPattern.UNKNOWN
    assert r.n_bars_analyzed == 1
    assert r.state_history == ["MARKUP"]


def test_detect_long_history_truncated_to_window():
    """Historique > window -> garde les window derniers."""
    r = detect_behavioral_sequence(
        ["MARKUP"] * 10 + ["ACCUMULATION"] * 5, window=5
    )
    assert r.pattern == BehavioralPattern.UNKNOWN  # stub pour l'instant
    assert r.n_bars_analyzed == 5
    assert len(r.state_history) == 5
    assert r.state_history == ["ACCUMULATION"] * 5


def test_detect_audit_documents_validation_pending():
    """L'audit doit pointer vers SON_INTERPRETATION.md pour validation."""
    r = detect_behavioral_sequence(["MARKUP"])
    assert "doc_ref" in r.audit
    assert "SON_INTERPRETATION.md" in r.audit["doc_ref"]
    assert "validation Son" in r.audit["reason"].lower() or "validation" in r.audit["reason"].lower()


def test_detect_accepts_vsa_state_enum():
    """L'API accepte VSAState enum (pas juste str)."""
    r = detect_behavioral_sequence(
        [VSAState.MARKUP, VSAState.ACCUMULATION, VSAState.MARKUP]
    )
    assert r.pattern == BehavioralPattern.UNKNOWN
    assert r.n_bars_analyzed == 3


def test_signature_window_default():
    """Window par defaut = 5."""
    import inspect
    sig = inspect.signature(detect_behavioral_sequence)
    assert sig.parameters["window"].default == 5


def test_signature_states_history_required():
    """states_history est requis (pas de defaut)."""
    import inspect
    sig = inspect.signature(detect_behavioral_sequence)
    assert sig.parameters["states_history"].default is inspect.Parameter.empty
