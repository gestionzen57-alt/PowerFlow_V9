"""Tests Mission 4 -- v10_cinematics structure (R6 fail-open).

Doctrine : 3 patterns cinematiques (EXHAUSTION, DIVERGENCE, PLATEAU) en attente
validation Son (SON_INTERPRETATION.md §4.1). Stub R6 fail-open renvoie toujours
flags=False pour ne pas casser le chemin live.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_cinematics import (
    CinematicAnalysis,
    CinematicState,
    analyze_series,
    get_cinematic_state,
    cinematics_verdict,
)


def test_cinematic_analysis_defaults():
    """Dataclass avec defaults R6 fail-open."""
    a = CinematicAnalysis()
    assert a.exhaustion_flag is False
    assert a.divergence_flag is False
    assert a.plateau_flag is False
    assert a.pic_force == 0.0
    assert a.pic_position == -1
    assert a.slope_force == 0.0
    assert a.slope_price == 0.0
    assert a.audit == {}


def test_cinematic_state_defaults():
    """CinematicState avec defaults."""
    s = CinematicState()
    assert s.exhaustion_flag is False
    assert s.divergence_flag is False
    assert s.blocked is False
    assert s.reasons == []
    assert s.audit == {}


def test_analyze_series_stub_returns_neutral():
    """Stub R6 fail-open : aucune detection."""
    forces = [1.0, 2.0, 3.0, 5.0, 4.0, 2.0, 1.0]  # pic au milieu + retombee
    prices = [1.1000, 1.1010, 1.1020, 1.1030, 1.1025, 1.1015, 1.1010]
    a = analyze_series(forces, prices, label="test", pip_size=0.0001)
    # Malgre un pattern classique d'exhaustion, le stub ne detecte rien
    assert a.exhaustion_flag is False
    assert a.divergence_flag is False
    assert a.audit.get("method") == "stub_R6_failopen"
    assert "validation Son" in a.audit.get("reason", "")


def test_analyze_series_empty_data():
    """Donnees vides -> pas de crash."""
    a = analyze_series([], [])
    assert a.exhaustion_flag is False
    assert a.divergence_flag is False


def test_get_cinematic_state_stub_returns_unblocked():
    """Stub -> blocked=False."""
    s = get_cinematic_state(bars_history=[{"open": 1.1, "close": 1.2}])
    assert s.blocked is False
    assert s.exhaustion_flag is False
    assert s.divergence_flag is False


def test_get_cinematic_state_with_direction():
    """Direction propagee dans audit."""
    s = get_cinematic_state(bars_history=None, direction="SELL")
    assert s.audit.get("direction") == "SELL"


def test_cinematics_verdict_stub_allows():
    """Verdict stub -> toujours ALLOW."""
    a = CinematicAnalysis()
    v = cinematics_verdict(a, direction="BUY")
    assert v["action"] == "ALLOW"
    assert v["reasons"] == []


def test_cinematics_verdict_audit_documents_stub():
    """Audit pointe vers SON_INTERPRETATION.md §4.1."""
    v = cinematics_verdict(CinematicAnalysis())
    assert "doc_ref" in v["audit"]
    assert "SON_INTERPRETATION.md" in v["audit"]["doc_ref"]


def test_cinematics_verdict_works_without_direction():
    """Direction par defaut = 'BUY'."""
    v = cinematics_verdict(CinematicAnalysis())
    assert v["audit"]["direction"] == "BUY"


def test_signature_get_cinematic_state():
    """get_cinematic_state accepte bars_history + direction."""
    import inspect
    sig = inspect.signature(get_cinematic_state)
    assert "bars_history" in sig.parameters
    assert "direction" in sig.parameters
    assert sig.parameters["direction"].default == "BUY"
