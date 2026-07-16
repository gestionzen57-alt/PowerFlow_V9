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
from core.v9.principle_engine import load_principles_from_yaml


def test_yaml_loads_53_unique_ids():
    """53 YAMLs au total : 25 ACTIVE + 28 SHADOW (SIGNAL_OPEN CEO +
    ADAPTIVE_VOL_GATE + 26 _ADAPTIVE P3-CONSUME-EXTEND Hermes 2026-07-14)."""
    principles = load_principles_from_yaml()
    ids = [p.principle_id for p in principles]
    assert len(set(ids)) == 53, (
        f"P3-CONSUME-EXTEND : attendu 53 IDs uniques "
        f"(27 source + 26 _ADAPTIVE), obtenu {len(set(ids))}"
    )
    assert "ADAPTIVE_VOL_GATE" in set(ids)
    # Au moins 1 _ADAPTIVE par groupe du générateur
    for must_have in (
        "COALITION_NODE_ADAPTIVE",       # groupe 1 node_rule
        "POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE",  # groupe 2 birth/break
        "GRAMMAR_ABSORPTION_ADAPTIVE",   # groupe 3 grammar
        "SIGNAL_OPEN_ADAPTIVE",          # groupe 3 signal
    ):
        assert must_have in set(ids), f"manque {must_have} du P3-CONSUME-EXTEND"


def test_principle_active_ids_count_is_25():
    """48 ACTIVE depuis le mandat CEO boucle fermée 2026-07-16.
    Promotion massive SHADOW→ACTIVE de tous les principes avec n≥20 + conf≥60.
    5 SHADOW structurels restants (ANTAGONIST_NODE_ADAPTIVE, GRAMMAR_EXHAUSTION_ADAPTIVE,
    GRAMMAR_LOCK_ADAPTIVE, GRAMMAR_RESPIRATION_ADAPTIVE, SIGNAL_OPEN_ADAPTIVE)."""
    assert len(PRINCIPLE_ACTIVE_IDS) == 48, (
        f"Attendu 48 ACTIVE (mandat CEO boucle fermee), "
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
    # 5 SHADOW structurels, les 22 autres sont ACTIVE (mandat CEO)
    stay_shadow = {"ANTAGONIST_NODE_ADAPTIVE", "GRAMMAR_EXHAUSTION_ADAPTIVE",
                   "GRAMMAR_LOCK_ADAPTIVE", "GRAMMAR_RESPIRATION_ADAPTIVE",
                   "SIGNAL_OPEN_ADAPTIVE"}
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
