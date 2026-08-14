"""V10 Filter Compositor — tests unitaires (Sprint 4 autopilote quant).

Obligations Sprint 4 :
  1. test_compose_conserves_a1_full_conviction
  2. test_compose_downgrade_a1_outside_zone
  3. test_compose_session_downgrade
  4. test_compose_smc_boost_a3
  5. test_compose_regime_unknown_block
  6. test_compose_r6_none_filters
  7. test_compose_none_level_stays_none
  8. test_trace_serialization
  9. test_r2_additif_no_core_v9
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_filter_compositor import (  # noqa: E402
    FilterTrace,
    CompositorResult,
    compose_filters,
    LEVEL_RANK,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers d'objets filtrants (stubs R6 — pas besoin des vrais modules)
# ─────────────────────────────────────────────────────────────────────
class FakeSession:
    def __init__(self, quality_score=1.0, is_optimal=True, session_now="NY"):
        self.quality_score = quality_score
        self.is_optimal_for_pair = is_optimal
        self.session_now = session_now


class FakeOte:
    def __init__(self, in_ote=True, kill_zone="NY", conviction_score=1.0):
        self.in_ote = in_ote
        self.kill_zone = kill_zone
        self.conviction_score = conviction_score


class FakeSmc:
    def __init__(self, structure="MSS_BULL"):
        self.structure = structure


class FakeRegime:
    def __init__(self, regime="TRENDING_UP"):
        self.regime = regime


# ─────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────
def test_compose_conserves_a1_full_conviction():
    """Session optimale + OTE in + SMC + regime OK → A1 conservé."""
    res = compose_filters(
        "A1", symbol="EURUSD", timeframe="H1", timestamp="2026-08-05T14:00:00Z",
        session=FakeSession(quality_score=1.0),
        ote=FakeOte(in_ote=True, kill_zone="NY"),
        smc=FakeSmc("BOS_BULL"),
        regime=FakeRegime("TRENDING_UP"),
    )
    assert res.final_level == "A1"
    assert res.downgraded is False
    assert res.original_level == "A1"


def test_compose_downgrade_a1_outside_zone():
    """OTE hors zone (in_ote=False) → A1→A2."""
    res = compose_filters(
        "A1", symbol="EURUSD", timeframe="H1",
        ote=FakeOte(in_ote=False, kill_zone="LONDON"),
        session=FakeSession(quality_score=1.0),
    )
    assert res.final_level == "A2"
    assert res.downgraded is True


def test_compose_session_downgrade():
    """Session faible (quality 0.5) → A1→A2."""
    res = compose_filters(
        "A1", symbol="EURUSD", timeframe="H1",
        session=FakeSession(quality_score=0.5),
    )
    assert res.final_level == "A2"
    assert res.downgraded is True


def test_compose_smc_boost_a3():
    """SMC MSS_BULL → boost A3→A2."""
    res = compose_filters(
        "A3", symbol="EURUSD", timeframe="H1",
        smc=FakeSmc("MSS_BULL"),
    )
    assert res.final_level == "A2"
    assert res.downgraded is False  # boost, pas downgrade


def test_compose_regime_unknown_block():
    """Régime UNKNOWN + regime_block=True → A2→A3 (blocage conservateur)."""
    res = compose_filters(
        "A2", symbol="EURUSD", timeframe="H1",
        regime=FakeRegime("UNKNOWN"),
        regime_block=True,
    )
    assert res.final_level == "A3"
    assert res.downgraded is True


def test_compose_regime_unknown_ok_keeps_a2():
    """Régime TRENDING_UP → A2 conservé."""
    res = compose_filters(
        "A2", symbol="EURUSD", timeframe="H1",
        regime=FakeRegime("TRENDING_UP"),
    )
    assert res.final_level == "A2"


def test_compose_r6_none_filters():
    """Tous les filtres None → niveau inchangé (R6 fail-open)."""
    res = compose_filters("A2", symbol="EURUSD", timeframe="H1")
    assert res.final_level == "A2"
    assert res.downgraded is False
    assert res.trace == []


def test_compose_none_level_stays_none():
    """Niveau NONE → reste NONE même avec filtres."""
    res = compose_filters(
        "NONE", symbol="EURUSD", timeframe="H1",
        session=FakeSession(quality_score=0.5),
        ote=FakeOte(in_ote=False),
    )
    assert res.final_level == "NONE"
    assert res.downgraded is False


def test_trace_serialization():
    """Chaque étape trace est JSON-sérialisable (R9)."""
    res = compose_filters(
        "A1", symbol="EURUSD", timeframe="H1",
        session=FakeSession(quality_score=1.0),
        ote=FakeOte(in_ote=True, kill_zone="NY"),
        smc=FakeSmc("BOS_BULL"),
        regime=FakeRegime("TRENDING_UP"),
    )
    d = res.as_dict()
    json.dumps(d)  # R9
    assert d["final_level"] == "A1"
    assert len(d["trace"]) == 4
    filter_names = [t["filter"] for t in d["trace"]]
    assert "session" in filter_names
    assert "ote" in filter_names
    assert "smc" in filter_names
    assert "regime" in filter_names


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_filter_compositor.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src


# ─────────────────────────────────────────────────────────────────────
# P2 AUDIT VSA — Fatman = filtre de contexte, JAMAIS trigger d'entrée
# ─────────────────────────────────────────────────────────────────────
def test_p2_no_fatman_trigger_a3_to_a2():
    """P2 : delta_force (Fatman) NE DOIT PLUS déclencher upgrade A3→A2.

    AVANT : |delta_force|>=0.08 et smc=None boostait A3→A2. Violation doctrine.
    APRÈS : la force est loggée comme contexte mais n'altère pas le level.
    Le seul chemin qui peut promouvoir A3→A2 est le SMC boost (smc != None).
    """
    # Cas 1 : smc=None, delta_force FORT (0.5) — AVANT boost, APRÈS no-op
    res = compose_filters(
        "A3", symbol="EURUSD", timeframe="H1",
        smc=None, delta_force=0.5,
    )
    assert res.final_level == "A3", (
        f"P2 violation : A3 ne doit PAS être promu A2 par delta_force seul. "
        f"Got {res.final_level}"
    )
    # Le delta_force doit être loggé en audit (contexte, pas trigger)
    assert "delta_force_context" in res.audit
    assert res.audit["delta_force_context"] == 0.5
    # Trace ne doit PAS contenir de step smc_delta_force
    trace_names = [t.filter_name for t in res.trace]
    assert "smc_delta_force" not in trace_names


def test_p2_no_fatman_trigger_a2_unchanged():
    """P2 : A2 avec delta_force fort ne doit PAS être modifié (déjà bon niveau)."""
    res = compose_filters(
        "A2", symbol="EURUSD", timeframe="H1",
        smc=None, delta_force=0.5,
    )
    assert res.final_level == "A2"
    assert res.audit.get("delta_force_context") == 0.5


def test_p2_smc_still_works():
    """P2 régression : le SMC boost (smc != None) doit TOUJOURS fonctionner.
    Seul le chemin smc_delta_force est supprimé, pas le SMC normal.
    """
    res = compose_filters(
        "A3", symbol="EURUSD", timeframe="H1",
        smc=FakeSmc("MSS_BULL"),
    )
    assert res.final_level == "A2"  # SMC boost A3→A2 inchangé


def test_p2_fatman_does_not_downgrade():
    """P2 : delta_force négatif fort ne doit PAS downgrader (filtre contexte only)."""
    res = compose_filters(
        "A1", symbol="EURUSD", timeframe="H1",
        smc=None, delta_force=-0.5,
    )
    assert res.final_level == "A1"
    # Pas de downgrade par Fatman — uniquement par session/ote/regime
    assert res.downgraded is False
