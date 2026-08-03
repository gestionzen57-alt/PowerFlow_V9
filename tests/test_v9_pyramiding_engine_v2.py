"""Tests pour PyramidingEngineV2 (STARS / SUPER_STARS).

Couvre les 5 cas critiques :
1. STARS OFF, n=1 : pas de boost (base)
2. STARS ON, n=3, MTF=1 : boost x1.3
3. SUPER_STARS ON, n=4, MTF=2, zone=naissance : boost x1.5
4. STARS ON, n=3, MTF=0 : pas de boost (MTF insuffisant)
5. NEWS_SHOCK : toujours bloqué
6. Plafond FTMO 2.0 respecté

R7 — tests verts avant commit.
R2 — additif sur PyramidingEngine V1.
"""
import os
import pytest


def _make_engine(stars=None, super_stars=None):
    """Fabrique un PyramidingEngineV2 avec env contrôlée (R6 fail-open)."""
    if stars is not None:
        os.environ["V9_PYRAMIDING_BOOST_STARS"] = "1" if stars else "0"
    if super_stars is not None:
        os.environ["V9_PYRAMIDING_BOOST_SUPER_STARS"] = "1" if super_stars else "0"
    # Recharger le module pour qu'il relise l'env
    import importlib
    import core.v9.v9_pyramiding_engine as mod
    importlib.reload(mod)
    return mod.PyramidingEngineV2()


def test_v1_strict_no_boost_when_disabled():
    """STARS/SUPER_STARS OFF = comportement strictement identique à V1.

    n=3, MTF=2, zone=naissance → V1: 1.0 + 0.3 (3+p) + 0.3 (MTF) + 0.2 (zone) = 1.8
    Pas de boost V2.
    """
    e = _make_engine(stars=False, super_stars=False)
    r = e.evaluate({"nb_principes_actifs": 3}, {"coalition_mtf_score": 2, "zone_type": "naissance"})
    assert r["multiplier"] == 1.8
    assert r["boost_applied"] == 1.0
    assert r["stars_level"] == "base"


def test_stars_boost_applied_n3_mtf1():
    """STARS ON + n=3 + MTF=1 : boost x1.3 → final = 1.3 * 1.3 = 1.69."""
    e = _make_engine(stars=True, super_stars=False)
    r = e.evaluate(
        {"nb_principes_actifs": 3},
        {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RANGE"},
    )
    assert r["multiplier"] == 1.69
    assert r["stars_level"] == "stars"
    assert r["boost_applied"] == 1.3
    assert r["pyramiding_version"] == "2.0"


def test_super_stars_boost_applied_n4_mtf2_naissance():
    """SUPER_STARS ON + n=4 + MTF=2 + zone=naissance.

    V1 base multiplier = 1.0 + 0.3 (3+p) + 0.3 (MTF) + 0.2 (zone) = 1.8 (pas de CASSURE ici).
    V2: 1.8 * 1.5 = 2.7 → capped à 2.0 (BOOST_MAX_FINAL FTMO).
    """
    e = _make_engine(stars=True, super_stars=True)
    r = e.evaluate(
        {"nb_principes_actifs": 4},
        {"coalition_mtf_score": 2, "zone_type": "naissance"},
    )
    # V1 = 1.8, V2 = 1.8 * 1.5 = 2.7 → capped 2.0
    assert r["multiplier"] == 2.0
    assert r["stars_level"] == "super_stars"
    assert r["boost_applied"] == 1.5


def test_stars_requires_mtf_score_1():
    """STARS ON mais MTF=0 : pas de boost (STARS exige MTF >= 1)."""
    e = _make_engine(stars=True, super_stars=False)
    r = e.evaluate(
        {"nb_principes_actifs": 3},
        {"coalition_mtf_score": 0, "zone_type": "range", "regime_type": "RANGE"},
    )
    # V1 base: 1.0 + 0.3 = 1.3, pas de boost V2
    assert r["multiplier"] == 1.3
    assert r["stars_level"] == "base"
    assert r["boost_applied"] == 1.0


def test_news_shock_blocks_pyramiding():
    """NEWS_SHOCK : pyramiding interdit, même avec STARS/SUPER_STARS ON."""
    e = _make_engine(stars=True, super_stars=True)
    r = e.evaluate(
        {"nb_principes_actifs": 5},
        {"coalition_mtf_score": 2, "zone_type": "naissance", "news_phase": "NEWS_SHOCK"},
    )
    assert r["pyramiding_allowed"] is False
    assert r["multiplier"] == 1.0
    assert r["reason"] == "news_shock_block"
    assert r["stars_level"] == "base"


def test_insufficient_principes_no_boost():
    """n=1 (sous le min V1) : pas de pyramiding, pas de boost."""
    e = _make_engine(stars=True, super_stars=True)
    r = e.evaluate(
        {"nb_principes_actifs": 1},
        {"coalition_mtf_score": 2, "zone_type": "naissance"},
    )
    assert r["pyramiding_allowed"] is False
    assert r["multiplier"] == 1.0
    assert r["stars_level"] == "base"


def test_super_stars_requires_specific_zone():
    """SUPER_STARS exige zone=naissance|2e_jambe, pas range. Donc ici STARS s'applique.

    V1 sans regime CASSURE ni zone naissance: 1.0 + 0.3 (3+p) + 0.3 (MTF) = 1.6
    V2 STARS boost x1.3: 1.6 * 1.3 = 2.08, capped à 2.0.
    """
    e = _make_engine(stars=True, super_stars=True)
    r = e.evaluate(
        {"nb_principes_actifs": 4},
        {"coalition_mtf_score": 2, "zone_type": "range", "regime_type": "CASSURE"},
    )
    # Zone=range → pas SUPER_STARS, mais STARS s'applique (3+ principes, MTF=1)
    assert r["stars_level"] == "stars"
    assert r["multiplier"] == 2.0  # 1.6 * 1.3 = 2.08 → capped 2.0


def test_accessor_functions():
    """Les accesseurs lisent bien l'env au runtime."""
    import core.v9.v9_pyramiding_engine as mod
    os.environ["V9_PYRAMIDING_BOOST_STARS"] = "1"
    os.environ["V9_PYRAMIDING_BOOST_SUPER_STARS"] = "0"
    assert mod.pyramiding_boost_stars_enabled() is True
    assert mod.pyramiding_boost_super_stars_enabled() is False
    os.environ["V9_PYRAMIDING_BOOST_STARS"] = "0"
    os.environ["V9_PYRAMIDING_BOOST_SUPER_STARS"] = "1"
    assert mod.pyramiding_boost_stars_enabled() is False
    assert mod.pyramiding_boost_super_stars_enabled() is True
    # Cleanup
    os.environ.pop("V9_PYRAMIDING_BOOST_STARS", None)
    os.environ.pop("V9_PYRAMIDING_BOOST_SUPER_STARS", None)


def test_backward_compat_v1_interface():
    """PyramidingEngineV2 hérite de V1 : toutes les méthodes V1 fonctionnent."""
    from core.v9.pyramiding_engine import PyramidingEngine
    import core.v9.v9_pyramiding_engine as mod
    importlib = __import__("importlib")
    importlib.reload(mod)
    e = mod.PyramidingEngineV2()
    assert isinstance(e, PyramidingEngine)
    # Attributs V1 présents
    assert hasattr(e, "min_principes_pyramiding")
    assert hasattr(e, "max_multiplier")
    assert hasattr(e, "base_multiplier")
    assert e.max_multiplier == 2.0  # Plafond FTMO
