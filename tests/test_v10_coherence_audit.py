"""V10 Coherence Audit — tests unitaires (Phase 4, Cognitive Continuum).

Obligations :
  1. test_audit_orphans_detects_delta_flow
  2. test_audit_connected_cortex
  3. test_audit_verdict
  4. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_coherence_audit import audit_orphans  # noqa: E402


def test_audit_orphans_detects_delta_flow():
    """v10_delta_flow est orphelin (importé seulement par __init__)."""
    res = audit_orphans()
    assert "v10_delta_flow" in res["orphans"]
    assert res["verdict"] == "ORPHANS_DETECTED"


def test_audit_connected_cortex():
    """L'audit détecte les modules connectés (structure, smc, etc.)."""
    res = audit_orphans()
    connected = [c["module"] for c in res["connected"]]
    assert "v10_structure" in connected
    assert "v10_smc" in connected


def test_audit_verdict():
    res = audit_orphans()
    assert res["n_orphans"] >= 1
    assert res["n_connected"] >= 1
    assert res["verdict"] in ("COHERENT", "ORPHANS_DETECTED")


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_coherence_audit.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
