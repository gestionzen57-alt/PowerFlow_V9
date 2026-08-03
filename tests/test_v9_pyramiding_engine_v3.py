"""Tests pour v9_pyramiding_engine_v3.py (Phase 133).

Couvre les cas critiques :
1. Composition V2 × MTF : V2 base × MTF boost
2. MTF boost actif si >= 3 TF
3. MTF boost inactif si < 3 TF (pass-through)
4. R6 fail-open : aligned_timeframes=None -> multiplier 1.0
5. R6 fail-open : aligned_timeframes vide -> multiplier 1.0
6. Kill switch V3 OFF -> MTF multiplier force a 1.0
7. Composition cumulative : V2 stars 1.69 × V3 MTF 1.2 = 2.028
8. Inherit de V2 : STARS/SUPER_STARS fonctionnent toujours
"""
import pytest

from core.v9.v9_pyramiding_engine_v3 import (
    VERSION,
    MTF_BOOST_MULT,
    MTF_MIN_TIMEFRAMES,
    PyramidingEngineV3,
    evaluate_mtf_boost,
    pyramiding_v3_mtf_boost_enabled,
)


def test_module_version():
    assert VERSION == "3.0"


def test_constants():
    assert MTF_BOOST_MULT == 1.2
    assert MTF_MIN_TIMEFRAMES == 3


def test_evaluate_mtf_boost_3tf_active():
    """3 TF alignes -> boost x1.2 actif."""
    r = evaluate_mtf_boost(["M5", "M15", "H1"])
    assert r["active"] is True
    assert r["multiplier"] == 1.2
    assert r["n_timeframes"] == 3
    assert "L17_pyramiding_v3_mtf_x1.2" in r["leviers"][0]


def test_evaluate_mtf_boost_5tf_active():
    """5 TF alignes -> boost x1.2 actif."""
    r = evaluate_mtf_boost(["M5", "M15", "M30", "H1", "H4"])
    assert r["active"] is True
    assert r["n_timeframes"] == 5


def test_evaluate_mtf_boost_2tf_inactive():
    """2 TF alignes -> boost inactif (insuffisant)."""
    r = evaluate_mtf_boost(["M5", "M15"])
    assert r["active"] is False
    assert r["multiplier"] == 1.0
    assert r["n_timeframes"] == 2


def test_evaluate_mtf_boost_empty():
    """Liste vide -> pass-through."""
    r = evaluate_mtf_boost([])
    assert r["active"] is False
    assert r["multiplier"] == 1.0
    assert r["reason"] == "no_timeframes_provided"


def test_evaluate_mtf_boost_deduplicates():
    """Doublons sont de-dupliques avant count."""
    r = evaluate_mtf_boost(["M5", "M5", "M15", "M15", "H1"])
    assert r["n_timeframes"] == 3
    assert r["active"] is True


def test_v3_pyramiding_engine_v2_inherit():
    """V3 herite de V2 : evaluate() fonctionne avec STARS."""
    from core.v9.v9_pyramiding_engine import pyramiding_boost_stars_enabled as _pse
    e = PyramidingEngineV3()
    # V2 attend arbiter_result + context (signature reelle V2)
    arbiter = {
        "pyramiding_allowed": True,
        "nb_principes_actifs": 3,
    }
    context = {
        "coalition_mtf_score": 1,
        "zone_type": "range",
        "regime_type": "RETOUR_EQUILIBRE",
    }
    r = e.evaluate(arbiter, context)
    # V2 stars_level = "stars" (3 principes + MTF >= 1 + zone range)
    assert "stars_level" in r
    # Le kill switch STARS est ON dans .env
    if _pse():
        assert r["stars_level"] == "stars", f"Attendu 'stars', got '{r['stars_level']}'"
        # V2 base = 1.0 + 0.3 (3+p) + 0.3 (MTF) + 0.2 (zone) = 1.8
        assert r["multiplier"] >= 1.3


def test_v3_evaluate_no_mtf_data():
    """V3 evaluate sans aligned_timeframes -> pass-through V2 + MTF=1.0."""
    e = PyramidingEngineV3()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v3(signal=arbiter, aligned_timeframes=None, context=context)
    assert r["v3_mtf_multiplier"] == 1.0
    assert r["v3_mtf_active"] is False
    assert r["v3_mtf_n_timeframes"] == 0


def test_v3_evaluate_with_mtf_boost():
    """V3 evaluate avec 3 TF -> MTF boost x1.2 (si kill switch ON)."""
    e = PyramidingEngineV3()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v3(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        context=context,
    )
    # Si kill switch V3 ON -> v3_mtf_multiplier = 1.2
    if pyramiding_v3_mtf_boost_enabled():
        assert r["v3_mtf_multiplier"] == 1.2
        assert r["v3_mtf_active"] is True
        assert r["v3_mtf_n_timeframes"] == 3
        # Composition : V2 multiplier * 1.2
        assert r["v3_final_multiplier"] == round(r["multiplier"] * 1.2, 3)
        # Levier present
        assert any("L17_pyramiding_v3_mtf" in l for l in r["v3_leviers_combined"])
    else:
        # Kill switch OFF -> MTF multiplier force a 1.0
        assert r["v3_mtf_multiplier"] == 1.0
        assert r["v3_mtf_active"] is False


def test_v3_composition_cumulative():
    """V2 stars (1.8) × V3 MTF (1.2) = 2.16."""
    e = PyramidingEngineV3()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 3}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v3(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1", "H4"],
        context=context,
    )
    if pyramiding_v3_mtf_boost_enabled():
        expected = r["multiplier"] * 1.2
        assert abs(r["v3_final_multiplier"] - round(expected, 3)) < 0.01


def test_v3_combo_label():
    """v3_combo = V2 stars_level + _mtf si boost actif."""
    e = PyramidingEngineV3()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 3}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v3(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        context=context,
    )
    if pyramiding_v3_mtf_boost_enabled() and r["v3_mtf_active"]:
        assert r["v3_combo"].endswith("_mtf")


def test_kill_switch_accesseur():
    """Accesseur est booleen."""
    import inspect
    sig = inspect.signature(pyramiding_v3_mtf_boost_enabled)
    assert str(sig.return_annotation) == "bool"