"""V10 Learning Persistence — tests unitaires (Phase R).

Obligations Phase R :
  1. test_save_load_state
  2. test_save_overwrite
  3. test_load_missing_empty
  4. test_learner_to_dict_roundtrip
  5. test_r6_sqlite_fallback
  6. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_learning_persistence import (  # noqa: E402
    LearningPersistence,
    learner_to_dict,
    dict_to_learner,
)
from core.v10.v10_error_learner import ErrorLearner, TradeOutcome  # noqa: E402


def test_save_load_state(tmp_path):
    db = tmp_path / "test_learn.db"
    p = LearningPersistence(str(db))
    p.save_state("main", {"n_trades": 10, "n_wins": 6, "lessons": ["a"]})
    loaded = p.load_state("main")
    assert loaded["n_trades"] == 10
    assert loaded["n_wins"] == 6
    assert loaded["lessons"] == ["a"]
    p.close()


def test_save_overwrite(tmp_path):
    db = tmp_path / "test_learn2.db"
    p = LearningPersistence(str(db))
    p.save_state("main", {"n_trades": 1})
    p.save_state("main", {"n_trades": 5})
    loaded = p.load_state("main")
    assert loaded["n_trades"] == 5
    p.close()


def test_load_missing_empty(tmp_path):
    db = tmp_path / "test_learn3.db"
    p = LearningPersistence(str(db))
    assert p.load_state("inexistant") == {}
    p.close()


def test_learner_to_dict_roundtrip():
    learner = ErrorLearner()
    learner.record(TradeOutcome(symbol="EURUSD", setup="A2", win=True, pnl=5.0))
    learner.record(TradeOutcome(symbol="EURUSD", setup="A2", win=False, pnl=-3.0))
    data = learner_to_dict(learner)
    assert data["n_trades"] == 2
    assert data["n_wins"] == 1

    restored = dict_to_learner(data)
    assert restored.state.n_trades == 2
    assert restored.state.n_wins == 1
    assert "A2" in restored.state.per_setup


def test_r6_sqlite_fallback():
    p = LearningPersistence(db_path="")
    p.save_state("main", {"n_trades": 3})
    assert p.load_state("main")["n_trades"] == 3
    p.close()


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_learning_persistence.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
