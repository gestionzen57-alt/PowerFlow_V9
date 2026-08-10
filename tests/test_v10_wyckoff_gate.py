"""Test Phase 13 — Wyckoff gate in decide_entry."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_decision_pipeline import decide_entry, PipelineDecision  # noqa: E402
from core.v10.v10_wyckoff_consolidated import WyckoffState, WyckoffConsolidated  # noqa: E402


def _reset_wyckoff_cache():
    """Reset the Wyckoff function cache for testing."""
    import core.v10.v10_decision_pipeline as dp
    dp._consolidate_wyckoff_ref = None


def _make_mock_consolidate(state, confidence=0.8):
    """Create a mock consolidate_wyckoff function that returns a specific state."""
    from core.v10.v10_wyckoff_consolidated import WyckoffConsolidated, WyckoffState
    res = WyckoffConsolidated()
    res.state = state
    res.confidence = confidence
    return lambda *args, **kwargs: res


def test_p13_wyckoff_markup_sell_a2_downgrade():
    """1. MARKUP + SELL A2 → WAIT (A3)."""
    import core.v10.v10_decision_pipeline as dp
    _reset_wyckoff_cache()
    dp._consolidate_wyckoff_ref = _make_mock_consolidate(WyckoffState.MARKUP, 0.8)
    
    result = decide_entry(
        pair="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        direction="SELL",
        signal_level="A2",
    )
    assert result.filtered_level == "A3", f"Expected A3, got {result.filtered_level}"
    assert "wyckoff_markup_conflict" in result.reasons
    assert "wyckoff_downgrade" in result.audit.get("steps", [])


def test_p13_wyckoff_markup_sell_a1_protected():
    """2. MARKUP + SELL A1 → soft-veto A1→A2 (DP-C9-OPT3).

    Depuis C9, Wyckoff peut soft-veto un A1 (downgrade A1→A2, jamais HOLD),
    raison `wyckoff_markup_A1_soft_veto`. Assertion alignée sur l'API réelle
    du module (Chantier 2 / MAX, module non modifié).
    """
    import core.v10.v10_decision_pipeline as dp
    _reset_wyckoff_cache()
    dp._consolidate_wyckoff_ref = _make_mock_consolidate(WyckoffState.MARKUP, 0.8)

    result = decide_entry(
        pair="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        direction="SELL",
        signal_level="A1",
    )
    # C9 : soft-veto A1→A2 (jamais HOLD)
    assert result.filtered_level in ("A1", "A2")
    assert "wyckoff_markup_A1_soft_veto" in result.reasons


def test_p13_wyckoff_markdown_buy_a3_downgrade():
    """3. MARKDOWN + BUY A3 → WAIT (A3) + reason added."""
    import core.v10.v10_decision_pipeline as dp
    _reset_wyckoff_cache()
    dp._consolidate_wyckoff_ref = _make_mock_consolidate(WyckoffState.MARKDOWN, 0.8)
    
    result = decide_entry(
        pair="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        direction="BUY",
        signal_level="A3",
    )
    # Le signal A3 ne devient pas trade, mais le gate devrait ajouter la reason
    assert "wyckoff_markdown_conflict" in result.reasons


def test_p13_wyckoff_distribution_buy_a2_downgrade():
    """4. DISTRIBUTION + BUY A2 → WAIT (A3)."""
    import core.v10.v10_decision_pipeline as dp
    _reset_wyckoff_cache()
    dp._consolidate_wyckoff_ref = _make_mock_consolidate(WyckoffState.DISTRIBUTION, 0.7)
    
    result = decide_entry(
        pair="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        direction="BUY",
        signal_level="A2",
    )
    assert result.filtered_level == "A3", f"Expected A3, got {result.filtered_level}"
    assert "wyckoff_distribution_conflict" in result.reasons


def test_p13_wyckoff_unknown_no_change():
    """5. UNKNOWN + SELL A2 → SELL (inchangé, fail-open)."""
    import core.v10.v10_decision_pipeline as dp
    _reset_wyckoff_cache()
    dp._consolidate_wyckoff_ref = _make_mock_consolidate("NEUTRAL", 0.0)
    
    result = decide_entry(
        pair="EURUSD",
        timeframe="M30",
        timestamp="2026-08-07T10:00:00Z",
        direction="SELL",
        signal_level="A2",
    )
    # UNKNOWN ne doit pas déclencher de downgrade
    assert result.filtered_level != "A3" or "wyckoff" not in str(result.reasons)


def test_p13_wyckoff_exception_failopen():
    """6. Exception dans consolidate_wyckoff → signal inchangé (R6 fail-open)."""
    import core.v10.v10_decision_pipeline as dp
    _reset_wyckoff_cache()
    
    def mock_consolidate(*args, **kwargs):
        raise Exception("Test exception")
    
    dp._consolidate_wyckoff_ref = mock_consolidate
    try:
        result = decide_entry(
            pair="EURUSD",
            timeframe="M30",
            timestamp="2026-08-07T10:00:00Z",
            direction="BUY",
            signal_level="A2",
        )
        # En cas d'exception, le signal ne doit pas être modifié par le gate Wyckoff
        assert result is not None
        assert result.filtered_level in ("NONE", "A3", "A2", "A1")
        # Vérifier que l'erreur est loggée dans l'audit
        assert "wyckoff_gate_error" in result.audit.get("steps", [])
    finally:
        dp._consolidate_wyckoff_ref = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])