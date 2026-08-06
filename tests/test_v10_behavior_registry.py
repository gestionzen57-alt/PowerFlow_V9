"""V10 Behavior Registry — tests unitaires (Phase 2, Cognitive Continuum).

Obligations :
  1. test_record_and_query_coherence
  2. test_query_insufficient_n
  3. test_query_no_db_r6
  4. test_registry_summary
  5. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_behavior_registry import (  # noqa: E402
    record_behavior,
    query_coherence,
    registry_summary,
)


def test_record_and_query_coherence(tmp_path):
    db = tmp_path / "beh.db"
    for i in range(6):
        record_behavior(
            timestamp=f"2026-08-0{i+1}T00:00:00Z", pair="EURUSD", timeframe="H1",
            observation_qualification="tension", regime_hmm="TRENDING_UP",
            coalition="EUR_USD", antagonisme="EUR_JPY",
            is_win=1 if i < 4 else 0, pnl_pips=5.0 if i < 4 else -5.0,
            db_path=db,
        )
    res = query_coherence(
        observation_qualification="tension", regime_hmm="TRENDING_UP",
        coalition="EUR_USD", antagonisme="EUR_JPY", db_path=db,
    )
    assert res["n"] == 6
    assert res["wr"] == pytest.approx(0.667, abs=0.01)  # 4/6
    assert res["reason"] == "ok"


def test_query_insufficient_n(tmp_path):
    db = tmp_path / "beh2.db"
    record_behavior(timestamp="t", pair="EURUSD", timeframe="H1",
                    observation_qualification="bascule", is_win=1, db_path=db)
    res = query_coherence(observation_qualification="bascule", db_path=db)
    assert res["n"] == 1
    assert res["wr"] == 0.0
    assert "insufficient" in res["reason"]


def test_query_no_db_r6(tmp_path):
    res = query_coherence(db_path=tmp_path / "absent.db")
    assert res["n"] == 0
    assert res["reason"] == "no_db"


def test_registry_summary(tmp_path):
    db = tmp_path / "beh3.db"
    record_behavior(timestamp="t", pair="EURUSD", timeframe="H1",
                    observation_qualification="tension", is_win=1, db_path=db)
    s = registry_summary(db_path=db)
    assert s["status"] == "ok"
    assert s["n_behaviors"] == 1
    assert s["n_resolved"] == 1


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_behavior_registry.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
