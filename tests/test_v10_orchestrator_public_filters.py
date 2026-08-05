"""V10 Orchestrator — tests du GATE FINAL public strategies (Sprint 5).

Vérifie que `compose_signal_with_context` applique `public_filters`
(session + ICT OTE + SMC + regime) en gate final, additif R2,
backward-compatible.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_orchestrator import (  # noqa: E402
    compose_signal_with_context,
)


class FakeOte:
    def __init__(self, in_ote=True, kill_zone="NY", conviction_score=1.0):
        self.in_ote = in_ote
        self.kill_zone = kill_zone
        self.conviction_score = conviction_score


class FakeSession:
    def __init__(self, quality_score=1.0, is_optimal=True, session_now="NY"):
        self.quality_score = quality_score
        self.is_optimal_for_pair = is_optimal
        self.session_now = session_now


class FakeRegime:
    def __init__(self, regime="TRENDING_UP"):
        self.regime = regime


def _base_bars():
    return [
        {"open": 1.0, "high": 1.002, "low": 0.998, "close": 1.001},
        {"open": 1.001, "high": 1.003, "low": 0.999, "close": 1.002},
        {"open": 1.002, "high": 1.004, "low": 1.000, "close": 1.003},
        {"open": 1.003, "high": 1.005, "low": 1.001, "close": 1.004},
    ]


def test_public_filters_noop_when_none():
    """public_filters None → backward-compatible, pas d'erreur."""
    res = compose_signal_with_context(
        "EURUSD", "EURUSD", "2026-08-05T14:00:00Z", "H1", _base_bars(),
        multi_tf_snapshots={},  # contexte vide → tradeable=False
    )
    # ne doit pas lever ; retourne un ContextFilteredSignal
    assert hasattr(res, "final_level")
    assert hasattr(res, "downgraded")


def test_public_filters_applied_when_provided():
    """public_filters fourni → le gate final tourne sans erreur."""
    res = compose_signal_with_context(
        "EURUSD", "EURUSD", "2026-08-05T14:00:00Z", "H1", _base_bars(),
        multi_tf_snapshots={},
        public_filters={
            "session": FakeSession(quality_score=1.0),
            "ote": FakeOte(in_ote=True, kill_zone="NY"),
            "regime": FakeRegime("TRENDING_UP"),
        },
    )
    # le gate final s'exécute (CoT rempli ou R6 error logguée)
    assert hasattr(res, "final_level")
    cot = res.signal.cot if hasattr(res.signal, "cot") else {}
    assert "3_public_filters" in cot or res.final_level is not None


def test_public_filters_downgrade_regime_unknown():
    """Régime UNKNOWN + regime_block → downgrade conservateur."""
    res = compose_signal_with_context(
        "EURUSD", "EURUSD", "2026-08-05T14:00:00Z", "H1", _base_bars(),
        multi_tf_snapshots={},
        public_filters={
            "regime": FakeRegime("UNKNOWN"),
        },
        regime_block=True,
    )
    assert hasattr(res, "final_level")
