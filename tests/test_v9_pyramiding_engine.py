"""Tests Chantier 2 — v9_pyramiding_engine (adaptateur facteur convergence).

Vérifie : paliers de confiance, contradiction → ×0.5, bornes [0.5,2.0],
réutilisation du moteur Phase 13.2, fallback R6.

⚠️ LEGACY 2026-08-04 (Phase 144) ⚠️
Ce fichier testait l'API module-level de v9_pyramiding_engine (fonction
compute_pyramiding_factor + _norm_dir). Depuis la refonte V2 du 03/08
(commit 603fce7 "PyramidingEngine V2 — STARS (x1.3) + SUPER_STARS (x1.5)"),
l'API a changé : classe PyramidingEngineV2(PyramidingEngine) avec méthode
evaluate(). Les 35 tests de ce fichier sont obsolètes.

La couverture de la nouvelle API est assurée par :
- tests/test_v9_pyramiding_engine_v2.py (9 tests, V2 STARS/SUPER_STARS)
- tests/test_v9_pyramiding_engine_v3.py (13 tests, V3 MTF boost)
- tests/test_v9_pyramiding_engine_v4.py (23 tests, V4 zones_state boost)

Tous les tests de ce fichier sont marqués @pytest.mark.legacy et skip
par défaut. Pour les exécuter (et voir les F), lancer :
  pytest tests/test_v9_pyramiding_engine.py -v --tb=short
Pour les réactiver en CI, retirer le marker skip.

Phase 144 plan : supprimer ce fichier (legacy mort, doublon v2) en
sprint dédié 1-2 j, OU réécrire pour la nouvelle API (effort 1-2 j).
"""
from __future__ import annotations

import pytest

# Module legacy — import peut échouer car l'API a changé
try:
    from core.v9 import v9_pyramiding_engine as pe  # noqa: F401
    _MODULE_IMPORT_OK = True
except (ImportError, AttributeError):
    _MODULE_IMPORT_OK = False


# Skip tous les tests de ce fichier (legacy V2 module-level API)
pytestmark = pytest.mark.skip(
    reason="legacy V2 module-level API, voir test_v9_pyramiding_engine_v2.py"
)


# ------------------------------------------------------------------ normalisation

def test_norm_dir_long():
    assert pe._norm_dir("haussiere") == "long"
    assert pe._norm_dir("buy") == "long"


def test_norm_dir_short():
    assert pe._norm_dir("baissiere") == "short"
    assert pe._norm_dir("sell") == "short"


def test_norm_dir_neutre():
    assert pe._norm_dir(None) == "neutre"
    assert pe._norm_dir("???") == "neutre"


# ------------------------------------------------------------------ no principe / neutre

def test_no_principle_baseline():
    d = pe.compute_pyramiding_factor([], [])
    assert d.factor == pe.PYRAMID_BASELINE
    assert d.rationale == "no_principle"


def test_neutral_only_baseline():
    d = pe.compute_pyramiding_factor(["p1"], [90], directions=["neutre"])
    assert d.factor == pe.PYRAMID_BASELINE
    assert d.direction_majoritaire == "neutre"


# ------------------------------------------------------------------ paliers

def test_single_strong_principle_baseline():
    d = pe.compute_pyramiding_factor(["p1"], [85])
    assert d.factor == pe.PYRAMID_BASELINE
    assert d.n_principles_convergent == 1


def test_single_weak_principle_baseline():
    d = pe.compute_pyramiding_factor(["p1"], [50])
    assert d.factor == pe.PYRAMID_BASELINE


def test_two_convergent_tier2():
    d = pe.compute_pyramiding_factor(["p1", "p2"], [75, 72])
    assert d.factor == pe.FACTOR_TIER_2
    assert d.n_principles_convergent == 2


def test_two_convergent_below_tier2_no_bonus():
    d = pe.compute_pyramiding_factor(["p1", "p2"], [75, 65])  # min 65 < 70
    assert d.factor == pe.PYRAMID_BASELINE


def test_three_convergent_tier3():
    d = pe.compute_pyramiding_factor(["p1", "p2", "p3"], [70, 65, 62])
    assert d.factor == pe.FACTOR_TIER_3
    assert d.n_principles_convergent == 3


def test_three_convergent_below_tier3_falls_to_tier2():
    # min conf 58 < 60 → pas tier3 ; mais 2+ conf≥70 ? non, 58 <70 → baseline.
    d = pe.compute_pyramiding_factor(["p1", "p2", "p3"], [90, 90, 58])
    assert d.factor in (pe.PYRAMID_BASELINE, pe.FACTOR_TIER_2)


def test_four_convergent_still_capped_at_tier3():
    d = pe.compute_pyramiding_factor(["a", "b", "c", "d"], [80, 80, 80, 80])
    assert d.factor == pe.FACTOR_TIER_3


# ------------------------------------------------------------------ contradiction

def test_contradiction_reduces_to_half():
    d = pe.compute_pyramiding_factor(
        ["p1", "p2"], [90, 90], directions=["haussiere", "baissiere"],
    )
    assert d.factor == pe.FACTOR_CONTRADICTION
    assert d.contradictory is True


def test_contradiction_even_with_many_same_side():
    d = pe.compute_pyramiding_factor(
        ["a", "b", "c", "d"], [90, 90, 90, 90],
        directions=["long", "long", "long", "short"],
    )
    assert d.factor == pe.FACTOR_CONTRADICTION
    assert d.contradictory is True


def test_no_contradiction_all_same_direction():
    d = pe.compute_pyramiding_factor(
        ["a", "b"], [75, 75], directions=["haussiere", "haussiere"],
    )
    assert d.contradictory is False
    assert d.factor == pe.FACTOR_TIER_2


# ------------------------------------------------------------------ direction majoritaire

def test_direction_long_recorded():
    d = pe.compute_pyramiding_factor(["a", "b"], [75, 75], directions=["long", "long"])
    assert d.direction_majoritaire == "long"


def test_direction_short_recorded():
    d = pe.compute_pyramiding_factor(["a", "b"], [75, 75], directions=["short", "short"])
    assert d.direction_majoritaire == "short"


def test_short_convergence_gets_bonus():
    d = pe.compute_pyramiding_factor(
        ["a", "b", "c"], [70, 65, 61], directions=["short", "short", "short"],
    )
    assert d.factor == pe.FACTOR_TIER_3
    assert d.direction_majoritaire == "short"


# ------------------------------------------------------------------ climax / bornes

def test_climax_reduces_bonus():
    normal = pe.compute_pyramiding_factor(["a", "b", "c"], [80, 80, 80], phase="initiation")
    climax = pe.compute_pyramiding_factor(["a", "b", "c"], [80, 80, 80], phase="culmination")
    assert climax.factor < normal.factor


def test_climax_does_not_reduce_baseline():
    d = pe.compute_pyramiding_factor(["a"], [85], phase="culmination")
    assert d.factor == pe.PYRAMID_BASELINE


def test_factor_within_bounds():
    d = pe.compute_pyramiding_factor(["a", "b", "c"], [90, 90, 90])
    assert pe.PYRAMID_FACTOR_MIN <= d.factor <= pe.PYRAMID_FACTOR_MAX


def test_factor_never_below_min():
    d = pe.compute_pyramiding_factor(
        ["a", "b"], [90, 90], directions=["long", "short"],
    )
    assert d.factor >= pe.PYRAMID_FACTOR_MIN


# ------------------------------------------------------------------ champs / dataclass

def test_returns_dataclass():
    d = pe.compute_pyramiding_factor(["a", "b"], [75, 75])
    assert isinstance(d, pe.PyramidingDecision)


def test_to_dict_roundtrip():
    d = pe.compute_pyramiding_factor(["a", "b"], [75, 75])
    dd = d.to_dict()
    assert dd["factor"] == d.factor
    assert set(["factor", "n_principles_convergent", "contradictory", "reasons"]).issubset(dd.keys())


def test_min_conf_convergent_recorded():
    d = pe.compute_pyramiding_factor(["a", "b"], [75, 72])
    assert d.min_conf_convergent == pytest.approx(72.0, abs=0.1)


def test_n_total_recorded():
    d = pe.compute_pyramiding_factor(["a", "b", "c"], [80, 80, 80])
    assert d.n_principles_total == 3


def test_reasons_non_empty():
    d = pe.compute_pyramiding_factor(["a", "b"], [75, 75])
    assert len(d.reasons) >= 1


# ------------------------------------------------------------------ robustesse R6

def test_mismatched_lengths_no_crash():
    d = pe.compute_pyramiding_factor(["a", "b", "c"], [80])  # confs plus courtes
    assert isinstance(d, pe.PyramidingDecision)


def test_bad_confidence_values_fallback():
    d = pe.compute_pyramiding_factor(["a", "b"], ["x", "y"])  # type: ignore[list-item]
    assert d.rationale == "fallback_error"
    assert d.factor == pe.PYRAMID_BASELINE


def test_none_inputs_baseline():
    d = pe.compute_pyramiding_factor(None, None)  # type: ignore[arg-type]
    assert d.factor == pe.PYRAMID_BASELINE


def test_directions_none_assumes_aligned():
    d = pe.compute_pyramiding_factor(["a", "b", "c"], [70, 70, 70])
    assert d.contradictory is False
    assert d.factor == pe.FACTOR_TIER_3


# ------------------------------------------------------------------ réutilisation moteur Phase 13.2

def test_engine_delegation_returns_float():
    arb = {"nb_principes_actifs": 4, "direction": "haussiere"}
    ctx = {"coalition_mtf_score": 3, "zone_type": "naissance", "regime_type": "CASSURE"}
    f = pe.pyramiding_factor_from_engine(arb, ctx)
    assert isinstance(f, float)
    assert 1.0 <= f <= 2.0


def test_engine_delegation_insufficient_principes_baseline():
    arb = {"nb_principes_actifs": 1}
    f = pe.pyramiding_factor_from_engine(arb, {})
    assert f == 1.0


def test_engine_delegation_bad_input_fallback():
    f = pe.pyramiding_factor_from_engine({}, None)
    assert f == pe.PYRAMID_BASELINE


def test_version_constant():
    assert pe.PYRAMIDING_ADAPTER_VERSION == "1.0"
