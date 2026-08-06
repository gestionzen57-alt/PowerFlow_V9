"""V10 Learning Continuum — tests unitaires (Phase 5, Cognitive Continuum).

Obligations :
  1. test_learn_from_outcome_no_registry
  2. test_learn_from_outcome_resolves
  3. test_drift_by_behavior_no_registry
  4. test_drift_by_behavior_insufficient
  5. test_drift_by_behavior_drifted
  6. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_learning_continuum import (  # noqa: E402
    learn_from_outcome,
    drift_by_behavior,
)
from core.v10.v10_behavior_registry import (  # noqa: E402
    record_behavior,
    resolve_outcome,
    query_coherence,
)


def test_learn_from_outcome_no_registry():
    r = learn_from_outcome(behavior_id=1, is_win=True)
    assert r["learned"] is False
    assert r["reason"] == "no_registry"


def test_learn_from_outcome_resolves(tmp_path):
    db = tmp_path / "learn.db"
    bid = record_behavior(timestamp="t", pair="EURUSD", timeframe="H1",
                          observation_qualification="tension", db_path=db)
    assert bid > 0
    ok = resolve_outcome(behavior_id=bid, is_win=1, pnl_pips=5.0, db_path=db)
    assert ok is True
    coh = query_coherence(observation_qualification="tension", db_path=db, min_n=1)
    assert coh["n"] == 1
    assert coh["wr"] == pytest.approx(1.0)

def test_drift_by_behavior_no_registry():
    r = drift_by_behavior(observation_qualification="tension")
    assert r["drifted"] is False
    assert r["reason"] == "no_registry"


def test_drift_by_behavior_insufficient(tmp_path):
    db = tmp_path / "drift.db"
    record_behavior(timestamp="t", pair="EURUSD", timeframe="H1",
                    observation_qualification="bascule", is_win=1, db_path=db)
    r = drift_by_behavior(observation_qualification="bascule",
                          behavior_registry=__import__(
                              "core.v10.v10_behavior_registry",
                              fromlist=["query_coherence"]),
                          db_path=db, min_n=10)
    # n=1 < 10 → pas de drift (insuffisant)
    assert r["drifted"] is False
    assert "insufficient" in r["reason"]


def test_drift_by_behavior_drifted(tmp_path):
    db = tmp_path / "drift2.db"
    # 10 comportements, 3 wins → WR 0.3 < 0.40 → drift
    for i in range(10):
        record_behavior(timestamp=f"t{i}", pair="EURUSD", timeframe="H1",
                        observation_qualification="rupture",
                        is_win=1 if i < 3 else 0, db_path=db)
    reg = __import__("core.v10.v10_behavior_registry",
                     fromlist=["query_coherence"])
    r = drift_by_behavior(observation_qualification="rupture",
                          behavior_registry=reg, db_path=db, min_n=10)
    assert r["n"] == 10
    assert r["wr"] == pytest.approx(0.3)
    assert r["drifted"] is True


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_learning_continuum.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src


def test_drift_by_behavior_timeframes(tmp_path):
    """Le drift filtre les TF de décision (R9 — hors biais volume M5/M15)."""
    db = tmp_path / "drift_tf.db"
    # 12 comportements M5 (3 wins) + 6 comportements H1 (1 win) → global WR 4/18
    for i in range(12):
        record_behavior(timestamp=f"m{i}", pair="EURUSD", timeframe="M5",
                        observation_qualification="maintien",
                        is_win=1 if i < 3 else 0, db_path=db)
    for i in range(6):
        record_behavior(timestamp=f"h{i}", pair="EURUSD", timeframe="H1",
                        observation_qualification="maintien",
                        is_win=1 if i < 1 else 0, db_path=db)
    reg = __import__("core.v10.v10_behavior_registry",
                     fromlist=["query_coherence"])
    # Sans filtre : 18 comportements, WR 4/18
    all_r = drift_by_behavior(observation_qualification="maintien",
                              behavior_registry=reg, db_path=db, min_n=1)
    assert all_r["n"] == 18
    assert all_r["wr"] == pytest.approx(4 / 18, abs=0.01)
    # Avec filtre M30/H1/H4 : 6 comportements H1, WR 1/6 — biais M5 isolé
    dec_r = drift_by_behavior(observation_qualification="maintien",
                              behavior_registry=reg, db_path=db, min_n=1,
                              timeframes=["M30", "H1", "H4"])
    assert dec_r["n"] == 6
    assert dec_r["wr"] == pytest.approx(1 / 6, abs=0.01)
