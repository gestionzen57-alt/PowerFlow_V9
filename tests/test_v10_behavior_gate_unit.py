"""Test Phase 15 — Behavior Context gate in orchestrator (unit tests for gate logic)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_wyckoff_consolidated import WyckoffState, WyckoffConsolidated  # noqa: E402


# ─── Unit tests for behavior gate logic (isolated) ───

def _apply_behavior_gate(setup_level: str, wr: float | None, drift: bool = False, degraded: bool = False) -> str:
    """
    Applique la logique du behavior gate.
    
    Règles :
    - WR < 0.35 → downgrade A2/A3 → A3
    - drift=True + A2 → A3
    - WR >= 0.55 + A3 → upgrade A2
    - A1 jamais modifié
    - None/unknown → inchangé (fail-open)
    - degraded=True → conservative (downgrade A2/A3 to A3)
    """
    if setup_level == "A1":
        return setup_level
    
    # WR None → fail-open, no change
    if wr is None:
        return setup_level
    
    # degraded flag → conservative (downgrade A2/A3 to A3)
    if degraded and setup_level in ("A2", "A3"):
        return "A3"
    
    # WR low → downgrade
    if wr < 0.35 and setup_level in ("A2", "A3"):
        return "A3"
    
    # Drift detected + A2 → downgrade
    if drift and setup_level == "A2":
        return "A3"
    
    # WR high + A3 → upgrade
    if wr >= 0.55 and setup_level == "A3":
        return "A2"
    
    return setup_level


def test_behavior_gate_wr_low_downgrades_a2():
    """1. WR < 0.35 + A2 → A3."""
    assert _apply_behavior_gate("A2", wr=0.28) == "A3"


def test_behavior_gate_wr_low_downgrades_a3():
    """2. WR < 0.35 + A3 → A3."""
    assert _apply_behavior_gate("A3", wr=0.28) == "A3"


def test_behavior_gate_wr_high_upgrades_a3():
    """3. WR >= 0.55 + A3 → A2."""
    assert _apply_behavior_gate("A3", wr=0.60) == "A2"


def test_behavior_gate_wr_high_no_upgrade_a2():
    """4. WR high + A2 → no change (already A2)."""
    assert _apply_behavior_gate("A2", wr=0.60) == "A2"


def test_behavior_gate_drift_downgrades_a2():
    """5. drift=True + A2 → A3."""
    assert _apply_behavior_gate("A2", wr=0.45, drift=True) == "A3"


def test_behavior_gate_drift_no_change_a1():
    """6. drift=True + A1 → A1 (protégé)."""
    assert _apply_behavior_gate("A1", wr=0.20, drift=True) == "A1"


def test_behavior_gate_drift_no_change_a3():
    """7. drift=True + A3 → A3 (no change, rule only for A2)."""
    assert _apply_behavior_gate("A3", wr=0.45, drift=True) == "A3"


def test_behavior_gate_a1_protected():
    """8. A1 never downgraded."""
    assert _apply_behavior_gate("A1", wr=0.20) == "A1"
    assert _apply_behavior_gate("A1", wr=0.20, drift=True) == "A1"
    assert _apply_behavior_gate("A1", wr=0.20, degraded=True) == "A1"


def test_behavior_gate_wr_none_failopen():
    """9. WR=None → no change (fail-open)."""
    assert _apply_behavior_gate("A2", wr=None) == "A2"
    assert _apply_behavior_gate("A3", wr=None) == "A3"


def test_behavior_gate_wr_none_drift_failopen():
    """10. WR=None + drift → no change (fail-open)."""
    assert _apply_behavior_gate("A2", wr=None, drift=True) == "A2"


def test_behavior_gate_degraded_downgrades():
    """11. degraded=True → conservative (downgrade A2/A3)."""
    assert _apply_behavior_gate("A2", wr=0.5, degraded=True) == "A3"
    assert _apply_behavior_gate("A3", wr=0.5, degraded=True) == "A3"


def test_behavior_gate_wr_mid_no_change():
    """11. WR mid-range (0.35-0.55) → no change."""
    assert _apply_behavior_gate("A2", wr=0.45) == "A2"
    assert _apply_behavior_gate("A3", wr=0.45) == "A3"


def test_behavior_gate_a3_wr_boundary():
    """12. A3 + WR=0.55 → upgrade to A2."""
    assert _apply_behavior_gate("A3", wr=0.55) == "A2"


def test_behavior_gate_a2_wr_boundary():
    """13. A2 + WR=0.35 → no change (boundary)."""
    assert _apply_behavior_gate("A2", wr=0.35) == "A2"


def test_behavior_gate_a2_wr_low_boundary():
    """14. A2 + WR=0.349 → downgrade to A3."""
    assert _apply_behavior_gate("A2", wr=0.349) == "A3"


def test_behavior_gate_wr_0_55_exact():
    """15. A3 + WR=0.55 exactly → upgrade."""
    assert _apply_behavior_gate("A3", wr=0.55) == "A2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])