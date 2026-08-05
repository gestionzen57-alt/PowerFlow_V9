"""V10 Error Learner — tests unitaires (Sprint 5 autopilote quant).

Obligations Sprint 5 :
  1. test_record_win
  2. test_record_loss_streak
  3. test_drift_detection
  4. test_recalibrate_recommended
  5. test_lesson_recorded
  6. test_state_serialization
  7. test_reset
  8. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_error_learner import (  # noqa: E402
    TradeOutcome,
    ErrorLearnerState,
    ErrorLearner,
    ADWINLikeDrift,
)


def _outcome(win, setup="A1", kz="NY", symbol="EURUSD", pnl=1.0):
    return TradeOutcome(symbol=symbol, setup=setup, kill_zone=kz,
                        win=win, pnl=pnl, timestamp="2026-08-05T10:00:00Z")


def test_record_win():
    learner = ErrorLearner()
    ev = learner.record(_outcome(True))
    assert learner.state.n_trades == 1
    assert learner.state.n_wins == 1
    assert learner.state.current_streak == 1
    assert ev["drift"] is False


def test_record_loss_streak():
    learner = ErrorLearner(losing_streak=3)
    learner.record(_outcome(False))
    learner.record(_outcome(False))
    learner.record(_outcome(False))
    assert learner.state.n_losses == 3
    assert learner.state.current_streak == -3
    assert learner.state.max_losing_streak == 3
    assert learner.state.recalibrate_recommended is True


def test_drift_detection():
    learner = ErrorLearner(drift_window=20, drift_delta=0.3)
    # 15 wins puis 5 losses → WR chute
    for _ in range(15):
        learner.record(_outcome(True))
    for _ in range(5):
        learner.record(_outcome(False))
    assert learner.state.drift_detected is True
    assert learner.state.drift_count >= 1


def test_recalibrate_recommended():
    learner = ErrorLearner(recalibrate_wr=0.4)
    # 10 pertes sur setup "A2"
    for i in range(10):
        learner.record(_outcome(False, setup="A2"))
    assert learner.state.recalibrate_recommended is True
    assert "A2" in learner.state.recalibrate_setups


def test_lesson_recorded():
    learner = ErrorLearner(recalibrate_wr=0.4)
    learner.record(_outcome(False, setup="A2"))
    learner.record(_outcome(False, setup="A2"))
    # losing streak 2 < 5 par défaut → pas de leçon encore
    assert len(learner.state.lessons) == 0
    # force recalibrage via WR setup (10 trades)
    for i in range(8):
        learner.record(_outcome(False, setup="A2"))
    assert len(learner.state.lessons) >= 1
    lesson = learner.state.lessons[-1]
    assert "A2" in lesson["lesson"]


def test_state_serialization():
    learner = ErrorLearner()
    learner.record(_outcome(True))
    learner.record(_outcome(False))
    d = learner.state.as_dict()
    json.dumps(d)  # R9
    assert d["n_trades"] == 2
    assert d["n_wins"] == 1
    assert "per_setup" in d


def test_reset():
    learner = ErrorLearner()
    learner.record(_outcome(True))
    learner.reset()
    assert learner.state.n_trades == 0
    assert learner.state.n_wins == 0
    assert learner.state.per_setup == {}


def test_adwin_like_drift():
    d = ADWINLikeDrift(window=20, delta=0.3)
    for _ in range(15):
        assert d.add(True) is False
    # 5 pertes → WR passe sous la chute de 30pts → drift
    drifted = False
    for _ in range(5):
        if d.add(False):
            drifted = True
    assert drifted is True


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_error_learner.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
