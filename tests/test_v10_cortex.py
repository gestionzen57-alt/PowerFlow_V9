"""V10 Cortex — tests unitaires (Phase 3, Cognitive Continuum).

Obligations :
  1. test_interpret_no_bridge_r6
  2. test_interpret_with_memory
  3. test_interpret_with_coherence
  4. test_decide_no_pipeline_r6
  5. test_decide_with_pipeline
  6. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_cortex import interpret, decide  # noqa: E402


class _FakeMemory:
    def recall_patterns(self, *a, **k):
        return [{"regime_type": "NEUTRE", "phase": "culmination",
                 "wr": 0.6, "n_observations": 40}]


class _FakeRegistry:
    def query_coherence(self, **k):
        return {"n": 10, "wr": 0.6, "n_wins": 6, "reason": "ok"}

    def record_behavior(self, **k):
        return 1


def test_interpret_no_bridge_r6():
    i = interpret(pair="EURUSD", timeframe="H1", timestamp="t",
                  observation_qualification="tension")
    assert i.memory_recall == []
    assert i.coherence == {}
    assert "r10" in i.audit


def test_interpret_with_memory():
    i = interpret(pair="EURUSD", timeframe="H1", timestamp="t",
                  observation_qualification="culmination",
                  memory_bridge=_FakeMemory())
    assert len(i.memory_recall) == 1
    assert i.memory_recall[0]["wr"] == 0.6
    assert "memory_recall" in i.audit["steps"]


def test_interpret_with_coherence():
    i = interpret(pair="EURUSD", timeframe="H1", timestamp="t",
                  observation_qualification="tension", regime_hmm="TRENDING_UP",
                  behavior_registry=_FakeRegistry())
    assert i.coherence["wr"] == 0.6
    assert "coherence_query" in i.audit["steps"]


def test_decide_no_pipeline_r6():
    d = decide(pair="EURUSD", timeframe="H1", timestamp="t",
               observation_qualification="tension")
    assert d["decision"]["action"] == "WAIT"
    assert d["decision"]["reason"] == "no_pipeline"


def test_decide_with_pipeline():
    def fake_pipeline(pair, tf, ts, direction, level, **kw):
        return {"action": "BUY", "lot_size": 0.01}
    d = decide(pair="EURUSD", timeframe="H1", timestamp="t",
               observation_qualification="tension", direction="long",
               signal_level="A2", decision_pipeline=fake_pipeline,
               behavior_registry=_FakeRegistry())
    assert d["decision"]["action"] == "BUY"
    assert d["memorized"] is True


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_cortex.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
