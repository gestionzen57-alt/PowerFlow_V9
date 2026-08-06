"""V10 Behavior RAG — tests unitaires (Phase 6, Cognitive Continuum).

Obligations :
  1. test_analogous_no_db_r6
  2. test_analogous_empty
  3. test_analogous_finds_similar
  4. test_analogous_avg_wr
  5. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_behavior_rag import analogous_behaviors  # noqa: E402
from core.v10.v10_behavior_registry import record_behavior  # noqa: E402


def test_analogous_no_db_r6(tmp_path):
    r = analogous_behaviors(observation_qualification="tension",
                            db_path=tmp_path / "absent.db")
    assert r["n_analogies"] == 0
    assert r["avg_wr"] == 0.0


def test_analogous_empty(tmp_path):
    db = tmp_path / "empty.db"
    r = analogous_behaviors(observation_qualification="tension", db_path=db)
    assert r["n_analogies"] == 0


def test_analogous_finds_similar(tmp_path):
    db = tmp_path / "rag.db"
    # 4 comportements tension/TRENDING_UP, 3 wins
    for i in range(4):
        record_behavior(timestamp=f"t{i}", pair="EURUSD", timeframe="H1",
                        observation_qualification="tension",
                        regime_hmm="TRENDING_UP", coalition="EUR_USD",
                        antagonisme="EUR_JPY",
                        is_win=1 if i < 3 else 0, db_path=db)
    r = analogous_behaviors(
        observation_qualification="tension", regime_hmm="TRENDING_UP",
        coalition="EUR_USD", antagonisme="EUR_JPY", db_path=db)
    assert r["n_analogies"] == 4
    assert r["avg_wr"] == pytest.approx(0.75, abs=0.01)  # 3/4
    assert r["best"] is not None


def test_analogous_avg_wr(tmp_path):
    db = tmp_path / "rag2.db"
    # 2 tension wins + 1 bascule loss → avg_wr sur tension = 1.0
    record_behavior(timestamp="a", pair="EURUSD", timeframe="H1",
                    observation_qualification="tension", is_win=1, db_path=db)
    record_behavior(timestamp="b", pair="EURUSD", timeframe="H1",
                    observation_qualification="tension", is_win=1, db_path=db)
    record_behavior(timestamp="c", pair="EURUSD", timeframe="H1",
                    observation_qualification="bascule", is_win=0, db_path=db)
    r = analogous_behaviors(observation_qualification="tension", db_path=db)
    assert r["n_analogies"] == 2
    assert r["avg_wr"] == pytest.approx(1.0)


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_behavior_rag.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
