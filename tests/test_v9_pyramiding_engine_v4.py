"""Tests pour v9_pyramiding_engine_v4.py (Phase 136).

Couvre les cas critiques :
1. Module version + constantes V4
2. Kill switch OFF -> multiplier 1.0 systematique
3. zone_state "naissance" / EARLY_EXTREME -> ×1.2
4. zone_state "2e_jambe" / ACCUMULATING -> ×1.1
5. zone_state "retest" / RUPTURE -> ×1.0 (pass-through)
6. zone_state "range" / NEUTRAL -> ×0.8
7. zone_state inconnue -> ×1.0 (R6 fail-open)
8. zone_state None -> pass-through ×1.0
9. Composition cumulative : V2 stars × V3 MTF × V4 naissance
10. Herite V3 : aligned_timeframes et zone_state combines
11. Legacy alias : "naissance" -> EARLY_EXTREME, etc.
12. case insensitive input
"""
import os

import pytest

from core.v9.kill_switches import get
from core.v9.v9_pyramiding_engine_v4 import (
    LEGACY_ZONES_STATE_ALIAS,
    VERSION,
    ZONES_STATE_MULTIPLIERS,
    PyramidingEngineV4,
    compute_zones_state_multiplier,
    pyramiding_v4_zones_state_enabled,
)


# ── Kill switch isolation ───────────────────────────────────────────
@pytest.fixture
def v4_kill_on(monkeypatch):
    """Active le kill switch V4 pour un seul test (env isole)."""
    monkeypatch.setenv("V9_PYRAMIDING_V4_ZONES_STATE_ENABLED", "1")
    monkeypatch.setenv("V9_PYRAMIDING_V3_MTF_BOOST_ENABLED", "1")
    return monkeypatch


# ── Module + constantes ─────────────────────────────────────────────
def test_module_version():
    assert VERSION == "4.0"


def test_zones_state_multipliers_mapping():
    assert ZONES_STATE_MULTIPLIERS["EARLY_EXTREME"] == 1.2
    assert ZONES_STATE_MULTIPLIERS["ACCUMULATING"] == 1.1
    assert ZONES_STATE_MULTIPLIERS["RUPTURE"] == 1.0
    assert ZONES_STATE_MULTIPLIERS["NEUTRAL"] == 0.8
    assert ZONES_STATE_MULTIPLIERS["LEAKING"] == 1.0  # fail-open


def test_legacy_aliases():
    assert LEGACY_ZONES_STATE_ALIAS["naissance"] == "EARLY_EXTREME"
    assert LEGACY_ZONES_STATE_ALIAS["2e_jambe"] == "ACCUMULATING"
    assert LEGACY_ZONES_STATE_ALIAS["retest"] == "RUPTURE"
    assert LEGACY_ZONES_STATE_ALIAS["range"] == "NEUTRAL"


# ── compute_zones_state_multiplier (fonction pure) ─────────────────
def test_compute_zones_state_naissance():
    assert compute_zones_state_multiplier("EARLY_EXTREME") == 1.2
    assert compute_zones_state_multiplier("naissance") == 1.2


def test_compute_zones_state_2e_jambe():
    assert compute_zones_state_multiplier("ACCUMULATING") == 1.1
    assert compute_zones_state_multiplier("2e_jambe") == 1.1


def test_compute_zones_state_retest_passthrough():
    assert compute_zones_state_multiplier("RUPTURE") == 1.0
    assert compute_zones_state_multiplier("retest") == 1.0


def test_compute_zones_state_range():
    assert compute_zones_state_multiplier("NEUTRAL") == 0.8
    assert compute_zones_state_multiplier("range") == 0.8


def test_compute_zones_state_unknown_fail_open():
    """R6 fail-open : state inconnu -> ×1.0."""
    assert compute_zones_state_multiplier("UNKNOWN_STATE_XYZ") == 1.0


def test_compute_zones_state_none_passthrough():
    """zone_state None -> ×1.0 (pass-through)."""
    assert compute_zones_state_multiplier(None) == 1.0


def test_compute_zones_state_case_insensitive():
    """Insensible a la casse (lowercase, uppercase)."""
    assert compute_zones_state_multiplier("early_extreme") == 1.2
    assert compute_zones_state_multiplier("neutral") == 0.8
    assert compute_zones_state_multiplier("  NEUTRAL  ") == 0.8  # strip espaces


# ── Kill switch + composition V4 ────────────────────────────────────
def test_v4_kill_switch_default_off():
    """Defaut OFF (R25' strict motion CEO). Le .env force a 0."""
    assert get("V9_PYRAMIDING_V4_ZONES_STATE_ENABLED", "0") == "0"


def test_v4_kill_switch_off_passthrough(v4_kill_on):
    """Kill switch OFF -> multiplier V4 force a 1.0 (neutre)."""
    os.environ["V9_PYRAMIDING_V4_ZONES_STATE_ENABLED"] = "0"
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 3}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="EARLY_EXTREME",
        context=context,
    )
    assert r["v4_zones_state_active"] is False
    assert r["v4_zones_state_multiplier"] == 1.2
    assert r["v4_final_multiplier"] == r["v3_final_multiplier"]


def test_v4_zone_state_none_passthrough(v4_kill_on):
    """zone_state None -> V4 pass-through (×1.0) meme si kill switch ON."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state=None,
        context=context,
    )
    assert r["v4_zones_state_normalized"] is None
    assert r["v4_zones_state_active"] is False
    assert r["v4_zones_state_multiplier"] == 1.0


def test_v4_naissance_boost_active(v4_kill_on):
    """zone_state EARLY_EXTREME avec kill ON -> V4 active ×1.2."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="EARLY_EXTREME",
        context=context,
    )
    assert r["v4_zones_state_normalized"] == "EARLY_EXTREME"
    assert r["v4_zones_state_active"] is True
    assert r["v4_zones_state_multiplier"] == 1.2
    assert any("L18_pyramiding_v4_zones" in l for l in r["v4_leviers_combined"])


def test_v4_2e_jambe_boost_active(v4_kill_on):
    """zone_state ACCUMULATING -> ×1.1."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="ACCUMULATING",
        context=context,
    )
    assert r["v4_zones_state_active"] is True
    assert r["v4_zones_state_multiplier"] == 1.1


def test_v4_retest_passthrough(v4_kill_on):
    """zone_state RUPTURE (retest) -> ×1.0 (pass-through)."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="RUPTURE",
        context=context,
    )
    assert r["v4_zones_state_active"] is True
    assert r["v4_zones_state_multiplier"] == 1.0
    assert not any("L18_pyramiding_v4_zones" in l for l in r["v4_leviers_combined"])


def test_v4_range_boost_damping(v4_kill_on):
    """zone_state NEUTRAL (range) -> ×0.8 (damping)."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="NEUTRAL",
        context=context,
    )
    assert r["v4_zones_state_active"] is True
    assert r["v4_zones_state_multiplier"] == 0.8
    assert any("x0.8" in l for l in r["v4_leviers_combined"])


def test_v4_unknown_state_fail_open(v4_kill_on):
    """zone_state inconnue -> V4 inactif (R6 fail-open)."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="UNKNOWN_STATE",
        context=context,
    )
    assert r["v4_zones_state_normalized"] is None
    assert r["v4_zones_state_active"] is False


def test_v4_composition_cumulative_full(v4_kill_on):
    """V2 stars × V3 MTF × V4 naissance : composition multiplicative complete.

    On verifie la R4 multiplicative (V3 × V4 applique sur le multiplier V2)
    sans presumer de la valeur exacte V2.
    """
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 3}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="EARLY_EXTREME",
        context=context,
    )
    v3_mult = r["v3_final_multiplier"]
    expected = round(v3_mult * 1.2, 4)
    assert abs(r["v4_final_multiplier"] - expected) < 0.01


def test_v4_composition_range_damping(v4_kill_on):
    """V3 × V4 range (0.8) : V4 applique un damping sur le resultat V3."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 3}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="NEUTRAL",
        context=context,
    )
    v3_mult = r["v3_final_multiplier"]
    expected = round(v3_mult * 0.8, 4)
    assert abs(r["v4_final_multiplier"] - expected) < 0.01


def test_v4_legacy_alias_in_signal(v4_kill_on):
    """Legacy alias 'naissance' accepte dans le signal V4."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 2}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="naissance",
        context=context,
    )
    assert r["v4_zones_state_normalized"] == "EARLY_EXTREME"
    assert r["v4_zones_state_multiplier"] == 1.2


def test_v4_combo_label_includes_zone(v4_kill_on):
    """v4_combo inclut le tag zone si V4 actif avec mult != 1.0."""
    e = PyramidingEngineV4()
    arbiter = {"pyramiding_allowed": True, "nb_principes_actifs": 3}
    context = {"coalition_mtf_score": 1, "zone_type": "range", "regime_type": "RETOUR_EQUILIBRE"}
    r = e.evaluate_v4(
        signal=arbiter,
        aligned_timeframes=["M5", "M15", "H1"],
        zone_state="EARLY_EXTREME",
        context=context,
    )
    if r["v4_zones_state_active"] and r["v4_zones_state_multiplier"] != 1.0:
        assert "early_extreme" in r["v4_combo"]


def test_v4_kill_switch_accesseur():
    """Accesseur du kill switch est booleen."""
    import inspect
    sig = inspect.signature(pyramiding_v4_zones_state_enabled)
    assert str(sig.return_annotation) == "bool"
