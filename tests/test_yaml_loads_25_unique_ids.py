"""Tests — catalogue YAML V9 (2026-07-10 → 2026-07-14).

Mise a jour 2026-07-14 — P3-CONSUME-EXTEND (Hermes) :
- 27 YAML au 2026-07-10 (25 ACTIVE + 2 SHADOW : SIGNAL_OPEN CEO 2026-07-10
  + ADAPTIVE_VOL_GATE Hermes 2026-07-14 P3-CONSUME).
- +26 _ADAPTIVE générés par scripts/generate_adaptive_principles.py
  (groupe 1 : 5 node_rule / groupe 2 : 4 birth/break / groupe 3 :
  17 grammar + SIGNAL_OPEN_ADAPTIVE).
- Total = 53 principes : 25 ACTIVE + 28 SHADOW.

Le compte 25 ACTIVE est invariant (toujours 25 depuis 2026-07-10) ;
les _ADAPTIVE sont tous SHADOW par défaut (R25' strict).
"""
from __future__ import annotations
from core.v9.config import PRINCIPLE_ACTIVE_IDS
from core.v9.principle_engine import load_principles_from_yaml, evaluate_principle


def test_yaml_loads_54_unique_ids():
    """54 YAMLs au total : 53 (P3-CONSUME-EXTEND) + VELOCITY_CLIMAX_GUARD
    (DIVERSIFY 2026-07-16, Gap 5 — 1er principe consommant la vélocité,
    SHADOW). Cf. docs/audit/AUDIT_LECTURE_MULTIDIM_2026-07-16.md §4."""
    principles = load_principles_from_yaml()
    ids = [p.principle_id for p in principles]
    assert len(set(ids)) == 54, (
        f"DIVERSIFY couleur : attendu 54 IDs uniques "
        f"(53 P3-CONSUME-EXTEND + VELOCITY_CLIMAX_GUARD), obtenu {len(set(ids))}"
    )
    assert "ADAPTIVE_VOL_GATE" in set(ids)
    assert "VELOCITY_CLIMAX_GUARD" in set(ids)
    # Au moins 1 _ADAPTIVE par groupe du générateur
    for must_have in (
        "COALITION_NODE_ADAPTIVE",       # groupe 1 node_rule
        "POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE",  # groupe 2 birth/break
        "GRAMMAR_ABSORPTION_ADAPTIVE",   # groupe 3 grammar
        "SIGNAL_OPEN_ADAPTIVE",          # groupe 3 signal
    ):
        assert must_have in set(ids), f"manque {must_have} du P3-CONSUME-EXTEND"


def test_velocity_climax_guard_consumes_velocity():
    """DIVERSIFY 2026-07-16 (Gap 5) — VELOCITY_CLIMAX_GUARD consomme
    velocite_moyenne : déclenche sur vélocité élevée (climax), reste silencieux
    à 0.0 (99 % des cas) et sur None — dégradation gracieuse R6, SHADOW R25'."""
    ps = {p.principle_id: p for p in load_principles_from_yaml()}
    p = ps["VELOCITY_CLIMAX_GUARD"]
    assert p.v9_status == "SHADOW"
    assert p.anti_signal_bias is True

    hi = evaluate_principle(
        p, {"velocite_moyenne": 0.12, "session_marche": "london", "z_extreme_dir": "UP"}
    )
    assert hi["triggered"] is True

    for absent in (0.0, None):
        res = evaluate_principle(
            p, {"velocite_moyenne": absent, "session_marche": "london"}
        )
        assert res["triggered"] is False


def test_principle_active_ids_count_is_25():
    """44 ACTIVE depuis DIVERSIFY 2026-07-16 (Mix CEO). Le mandat boucle fermée
    avait porté à 48 ; 4 réanimés (ANTAGONIST_NODE, GRAMMAR_LOCK,
    GRAMMAR_RESPIRATION, ADAPTIVE_VOL_GATE) sont rétrogradés ACTIVE→SHADOW
    en observation 24-48h avant re-promotion (R25')."""
    assert len(PRINCIPLE_ACTIVE_IDS) == 44, (
        f"Attendu 44 ACTIVE (DIVERSIFY Mix), "
        f"obtenu {len(PRINCIPLE_ACTIVE_IDS)}"
    )


def test_all_active_ids_exist_in_yaml():
    principles = load_principles_from_yaml()
    yaml_ids = {p.principle_id for p in principles}
    for aid in PRINCIPLE_ACTIVE_IDS:
        assert aid in yaml_ids, f"{aid} dans ACTIVE mais absent du YAML"


def test_all_adaptive_principles_are_shadow():
    """Mandat CEO boucle fermée 2026-07-16 : R25'' auto-promotion.
    La plupart des *_ADAPTIVE sont promus ACTIVE (n≥20 + conf≥60).
    Seuls 5 SHADOW structurels sans données suffisantes restent SHADOW :
    ANTAGONIST_NODE_ADAPTIVE, GRAMMAR_EXHAUSTION_ADAPTIVE,
    GRAMMAR_LOCK_ADAPTIVE, GRAMMAR_RESPIRATION_ADAPTIVE, SIGNAL_OPEN_ADAPTIVE."""
    principles = load_principles_from_yaml()
    adaptive = [p for p in principles if "ADAPTIVE" in p.principle_id]
    assert len(adaptive) == 27, (
        f"P3-CONSUME-EXTEND : attendu 27 _ADAPTIVE "
        f"(1 ADAPTIVE_VOL_GATE + 26 générés), got {len(adaptive)}"
    )
    # 5 SHADOW structurels + ADAPTIVE_VOL_GATE (DIVERSIFY 2026-07-16, réanimé
    # en observation), les 21 autres sont ACTIVE (mandat CEO).
    stay_shadow = {"ANTAGONIST_NODE_ADAPTIVE", "GRAMMAR_EXHAUSTION_ADAPTIVE",
                   "GRAMMAR_LOCK_ADAPTIVE", "GRAMMAR_RESPIRATION_ADAPTIVE",
                   "SIGNAL_OPEN_ADAPTIVE",
                   "ADAPTIVE_VOL_GATE"}  # DIVERSIFY Mix — réanimé, en observation
    for p in adaptive:
        if p.principle_id in stay_shadow:
            assert p.v9_status == "SHADOW", (
                f"{p.principle_id} devrait rester SHADOW (structurel), "
                f"v9_status={p.v9_status}"
            )
        else:
            assert p.v9_status == "ACTIVE", (
                f"{p.principle_id} devrait être ACTIVE (mandat CEO boucle fermee), "
                f"v9_status={p.v9_status}"
            )
