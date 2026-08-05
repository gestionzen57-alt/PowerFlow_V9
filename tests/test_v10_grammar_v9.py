"""V10 Grammar V9 — tests unitaires (Phase R).

Obligations :
  1. test_leader_follower_detected
  2. test_leader_follower_no_leader
  3. test_pullback_detected
  4. test_pullback_bascule_forte
  5. test_tension_detected
  6. test_tension_low
  7. test_respiration_detected
  8. test_lock_detected
  9. test_opposition_detected
  10. test_evaluate_grammar_all
  11. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_grammar_v9 import (  # noqa: E402
    GrammarSignal,
    leader_follower,
    pullback,
    tension,
    respiration,
    lock,
    opposition,
    evaluate_grammar_v9,
)


def test_leader_follower_detected():
    g = leader_follower("TRENDING_UP", "EUR", "USD")
    assert g.detected is True
    assert g.direction == "BULLISH"
    assert g.confidence == pytest.approx(0.7)


def test_leader_follower_no_leader():
    g = leader_follower("TRENDING_UP", None, "USD")
    assert g.detected is False


def test_pullback_detected():
    g = pullback("TRENDING_UP", False, 10.0, "up")
    assert g.detected is True
    assert g.direction == "BULLISH"


def test_pullback_bascule_forte():
    g = pullback("TRENDING_UP", True, 50.0, "up")
    assert g.detected is False


def test_tension_detected():
    g = tension(True, 1.5, 0.3)
    assert g.detected is True
    assert g.direction == "BULLISH"
    assert g.confidence == pytest.approx(0.75)


def test_tension_low():
    g = tension(True, 0.5, 0.3)
    assert g.detected is False


def test_respiration_detected():
    g = respiration("respiration", "compression")
    assert g.detected is True
    assert g.direction == "NEUTRAL"


def test_lock_detected():
    g = lock("compression", "respiration")
    assert g.detected is True
    assert g.direction == "NEUTRAL"


def test_opposition_detected():
    g = opposition(3, 20.0)
    assert g.detected is True
    assert g.direction == "NEUTRAL"


def test_evaluate_grammar_all():
    res = evaluate_grammar_v9(
        regime_name="TRENDING_UP", leader="EUR", follower="USD",
        pliure_detectee=True, tension_score=1.5, pente=0.3,
        antagonismes_count=3, bascule_intensite=20.0,
    )
    assert res["n_detected"] >= 2
    assert res["best"] is not None
    json.dumps(res)  # R9


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_grammar_v9.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
