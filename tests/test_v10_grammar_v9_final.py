"""V10 Grammar V9 Final — tests unitaires (Phase R).

Obligations :
  1. test_contexte_detected
  2. test_croisement_detected
  3. test_croisement_confirmation_detected
  4. test_gravity_respring_detected
  5. test_power_angle_break_detected
  6. test_raw_node_birth_detected
  7. test_signal_open_detected
  8. test_evaluate_final_all
  9. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10._deprecated.v10_grammar_v9_final import (  # noqa: E402
    GrammarSignal,
    contexte,
    croisement,
    croisement_confirmation,
    gravity_respring,
    power_angle_break,
    raw_node_birth,
    signal_open,
    evaluate_grammar_v9_final,
)


def test_contexte_detected():
    g = contexte(True, True)
    assert g.detected is True
    assert g.direction == "NEUTRAL"


def test_croisement_detected():
    g = croisement(True, "EUR")
    assert g.detected is True
    assert g.confidence == pytest.approx(0.6)


def test_croisement_confirmation_detected():
    g = croisement_confirmation(True, 0.08)
    assert g.detected is True
    assert g.confidence == pytest.approx(0.7)


def test_gravity_respring_detected():
    g = gravity_respring("ACCUMULATING", "NEUTRAL")
    assert g.detected is True
    assert g.direction == "BULLISH"


def test_power_angle_break_detected():
    g = power_angle_break("RUPTURE", 1.5)
    assert g.detected is True
    assert g.confidence == pytest.approx(0.7)


def test_raw_node_birth_detected():
    g = raw_node_birth("NEUTRAL", "ACCUMULATING")
    assert g.detected is True


def test_signal_open_detected():
    g = signal_open("ouverte", 80.0)
    assert g.detected is True
    assert g.confidence == pytest.approx(0.6)


def test_evaluate_final_all():
    res = evaluate_grammar_v9_final(
        marche_ouvert=True, session_marche=True,
        bascule_detectee=True, bascule_devise_dominante="EUR",
        croisement_detecte=True, vitesse=0.08,
        state="ACCUMULATING", prev_state="NEUTRAL",
        tension_score=1.5, window_statut="ouverte", confiance_qualification=80.0,
    )
    assert res["n_detected"] >= 5
    assert res["best"] is not None
    json.dumps(res)  # R9


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/_deprecated/v10_grammar_v9_final.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
