"""V10 Grammar V9 Extra — tests unitaires (Phase R).

Obligations :
  1. test_adaptive_vol_gate_high
  2. test_adaptive_vol_gate_normal
  3. test_elastic_breath_detected
  4. test_elastic_breath_no
  5. test_exhaustion_detected
  6. test_exhaustion_low_z
  7. test_velocity_climax_detected
  8. test_velocity_climax_low
  9. test_node_birth_detected
  10. test_evaluate_extra_all
  11. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10._deprecated.v10_grammar_v9_extra import (  # noqa: E402
    GrammarSignal,
    adaptive_vol_gate,
    elastic_breath,
    exhaustion,
    velocity_climax_guard,
    node_birth,
    evaluate_grammar_v9_extra,
)


def test_adaptive_vol_gate_high():
    g = adaptive_vol_gate("HIGH")
    assert g.detected is True
    assert g.direction == "NEUTRAL"


def test_adaptive_vol_gate_normal():
    g = adaptive_vol_gate("NORMAL")
    assert g.detected is False


def test_elastic_breath_detected():
    g = elastic_breath("ACCUMULATING", 2)
    assert g.detected is True
    assert g.direction == "BULLISH"


def test_elastic_breath_no():
    g = elastic_breath("MARKUP", 0)
    assert g.detected is False


def test_exhaustion_detected():
    g = exhaustion(2.5, "EARLY_EXTREME")
    assert g.detected is True
    assert g.direction == "BEARISH"  # z>0 → épuisement haussier → retournement baissier


def test_exhaustion_low_z():
    g = exhaustion(1.0, "EARLY_EXTREME")
    assert g.detected is False


def test_velocity_climax_detected():
    g = velocity_climax_guard(0.1, True)
    assert g.detected is True
    assert g.direction == "NEUTRAL"


def test_velocity_climax_low():
    g = velocity_climax_guard(0.02, True)
    assert g.detected is False


def test_node_birth_detected():
    g = node_birth("ACCUMULATING")
    assert g.detected is True
    assert g.direction == "NEUTRAL"


def test_evaluate_extra_all():
    res = evaluate_grammar_v9_extra(
        vol_regime="HIGH", state="ACCUMULATING", absorbed_pullbacks=2,
        z_current=2.5, velocite_moyenne=0.1,
    )
    assert res["n_detected"] >= 3
    assert res["best"] is not None
    json.dumps(res)  # R9


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/_deprecated/v10_grammar_v9_extra.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
