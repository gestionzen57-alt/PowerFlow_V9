"""V10 Auto-Recalibrator — tests unitaires (Sprint 7 autopilote quant).

Obligations Sprint 7 :
  1. test_should_recalibrate_drift
  2. test_should_recalibrate_recommended_enough_data
  3. test_should_recalibrate_no_trigger
  4. test_should_recalibrate_recommended_not_enough
  5. test_run_auto_recalibration_no_trigger_hold
  6. test_run_auto_recalibration_error_hold
  7. test_decision_serialization
  8. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_auto_recalibrator import (  # noqa: E402
    RecalibDecision,
    should_recalibrate,
    run_auto_recalibration,
)


class FakeState:
    def __init__(self, drift=False, drift_count=0, recal_recommended=False,
                 recal_setups=None, per_setup=None):
        self.drift_detected = drift
        self.drift_count = drift_count
        self.recalibrate_recommended = recal_recommended
        self.recalibrate_setups = recal_setups or []
        self.per_setup = per_setup or {}


def test_should_recalibrate_drift():
    st = FakeState(drift=True, drift_count=2, recal_setups=["A2"])
    trig, reason, setups = should_recalibrate(st)
    assert trig is True
    assert reason == "drift_detected"
    assert setups == ["A2"]


def test_should_recalibrate_recommended_enough_data():
    st = FakeState(
        recal_recommended=True, recal_setups=["A1"],
        per_setup={"A1": {"n": 15, "wr": 0.3}},
    )
    trig, reason, setups = should_recalibrate(st, min_losses=10)
    assert trig is True
    assert reason == "recalibrate_recommended"
    assert setups == ["A1"]


def test_should_recalibrate_no_trigger():
    st = FakeState()
    trig, reason, setups = should_recalibrate(st)
    assert trig is False
    assert reason == "no_trigger"


def test_should_recalibrate_recommended_not_enough():
    st = FakeState(
        recal_recommended=True, recal_setups=["A1"],
        per_setup={"A1": {"n": 5, "wr": 0.3}},  # < min_losses=10
    )
    trig, reason, setups = should_recalibrate(st, min_losses=10)
    assert trig is False
    assert reason == "no_trigger"


def test_run_auto_recalibration_no_trigger_hold():
    st = FakeState()
    dec = run_auto_recalibration(st, db_path="data/v9_forces.db")
    assert dec.triggered is False
    assert dec.decision == "HOLD"


def test_run_auto_recalibration_error_hold():
    # drift déclenché mais DB invalide → R6 fail-open : pas de crash,
    # décision bornée (REVERT si report vide/avg_wr=0 → après < avant).
    st = FakeState(drift=True, drift_count=1, recal_setups=["A1"],
                   per_setup={"A1": {"n": 15, "wr": 0.3}})
    dec = run_auto_recalibration(st, db_path="/nonexistent/db.sqlite")
    assert dec.triggered is True
    # R6 fail-open : le recalibrator retourne un report vide (avg_wr=0)
    # plutôt que de lever → after_wr(0) < before_wr(0.3) → REVERT (safe).
    assert dec.decision in ("HOLD", "REVERT")


def test_decision_serialization():
    dec = RecalibDecision(timestamp="t", triggered=True, reason="drift",
                          setups=["A2"], decision="DEPLOY",
                          before_wr=0.4, after_wr=0.55,
                          threshold_path="config/x.json")
    d = dec.as_dict()
    json.dumps(d)  # R9
    assert d["decision"] == "DEPLOY"
    assert d["before_wr"] == 0.4


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_auto_recalibrator.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
