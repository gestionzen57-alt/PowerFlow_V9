"""test_p3_consume_extend.py — Tests P3-CONSUME-EXTEND (Hermes, 2026-07-14).

Vérifie que les principes _ADAPTIVE générés par
scripts/generate_adaptive_principles.py :
1. sont chargés par load_principles_from_yaml (registry)
2. évaluent correctement avec P3-WIRE ON (adaptive_*_threshold présents)
3. NE déclenchent PAS avec P3-WIRE OFF (adaptive_*_threshold absents)
   → dégradation gracieuse R6
4. préservent les conditions originales du principe source
5. conservent le scope (timeframes/currencies) source

Doctrine :
- R25' : SHADOW par défaut, pas de promotion ACTIVE ici.
- R26  : tests pytest obligatoires avant commit.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.v9.principle_engine import (
    PrincipleRecord,
    evaluate_condition,
    load_principles_from_yaml,
)

PRINCIPLES_DIR = Path(__file__).resolve().parent.parent / "core" / "v9" / "principles"


# ── Liste des _ADAPTIVE attendus (mirror du générateur, hors SIGNAL_OPEN) ──

EXPECTED_ADAPTIVE = [
    "ADAPTIVE_VOL_GATE",  # pré-existant, livré par P3-CONSUME (5e1b9df)
    # Groupe 1 — node_rule (P3-CONSUME-EXTEND, Hermes 2026-07-14)
    "COALITION_NODE_ADAPTIVE",
    "ANTAGONIST_NODE_ADAPTIVE",
    "ZONE_RETEST_ADAPTIVE",
    "ELASTIC_BREATH_ADAPTIVE",
    "GRAVITY_RESPRING_NODE_ADAPTIVE",
    # Groupe 2 — birth/break pliure-adaptive (Hermes 2026-07-14)
    "POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE",
    "NODE_BIRTH_FAST_ADAPTIVE",
    "RAW_NODE_BIRTH_ADAPTIVE",
    "PRICE_LAG_AT_NODE_BIRTH_ADAPTIVE",
    # Groupe 3 — grammar + signal_open (Hermes 2026-07-14)
    "GRAMMAR_ABSORPTION_ADAPTIVE",
    "GRAMMAR_ANTAGONISME_ADAPTIVE",
    "GRAMMAR_BREAK_ADAPTIVE",
    "GRAMMAR_COALITION_ADAPTIVE",
    "GRAMMAR_CONTEXTE_ADAPTIVE",
    "GRAMMAR_CROISEMENT_ADAPTIVE",
    "GRAMMAR_EXHAUSTION_ADAPTIVE",
    "GRAMMAR_EXTENSION_ADAPTIVE",
    "GRAMMAR_LEADER_FOLLOWER_ADAPTIVE",
    "GRAMMAR_LOCK_ADAPTIVE",
    "GRAMMAR_OPPOSITION_ADAPTIVE",
    "GRAMMAR_PULLBACK_ADAPTIVE",
    "GRAMMAR_REGIME_ADAPTIVE",
    "GRAMMAR_RESPIRATION_ADAPTIVE",
    "GRAMMAR_SQUEEZE_ADAPTIVE",
    "GRAMMAR_TENSION_ADAPTIVE",
    "SIGNAL_OPEN_ADAPTIVE",
]


def _find(principle_id: str, regs: list[PrincipleRecord]) -> PrincipleRecord | None:
    for r in regs:
        if r.principle_id == principle_id:
            return r
    return None


@pytest.fixture(scope="module")
def registry() -> list[PrincipleRecord]:
    return load_principles_from_yaml(PRINCIPLES_DIR)


# ── Test 1 : tous les _ADAPTIVE attendus sont chargés ─────────────────────


def test_all_adaptive_principles_loaded(registry: list[PrincipleRecord]) -> None:
    """Les 6 principes _ADAPTIVE attendus sont dans le registry."""
    missing = [
        pid for pid in EXPECTED_ADAPTIVE if _find(pid, registry) is None
    ]
    assert not missing, f"_ADAPTIVE manquants dans le registry : {missing}"


_ADAPTIVE_PROMOTED_ACTIVE = {
    "ADAPTIVE_VOL_GATE",  # promu ACTIVE 2026-07-14 (motion CEO)
    "GRAMMAR_CONTEXTE_ADAPTIVE",  # promu ACTIVE 2026-07-15 (WR 79.5% vs ACTIVE 44.7%)
    "POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE",  # promu ACTIVE 2026-07-15 (WR 75.0% vs ACTIVE 54.4%)
    "ZONE_RETEST_ADAPTIVE",  # promu ACTIVE 2026-07-15 (WR 66.7% vs ACTIVE 57.3%)
}


def test_adaptive_status_is_shadow(registry: list[PrincipleRecord]) -> None:
    """Tous les *_ADAPTIVE générés sont en SHADOW (R25'), sauf les promus
    ACTIVE listés dans _ADAPTIVE_PROMOTED_ACTIVE (replay benchmark 2026-07-15)."""
    for r in registry:
        if "ADAPTIVE" in r.principle_id:
            if r.principle_id in _ADAPTIVE_PROMOTED_ACTIVE:
                assert r.v9_status == "ACTIVE", (
                    f"{r.principle_id} devrait être ACTIVE (promu), "
                    f"v9_status={r.v9_status}"
                )
            else:
                assert r.v9_status == "SHADOW", (
                    f"{r.principle_id} doit être SHADOW (R25'), "
                    f"v9_status={r.v9_status}"
                )


def test_adaptive_origin_traced(registry: list[PrincipleRecord]) -> None:
    """Tous les _ADAPTIVE ont origin V9-P3-CONSUME-EXTEND (sauf ADAPTIVE_VOL_GATE livré avant)."""
    for r in registry:
        if r.principle_id == "ADAPTIVE_VOL_GATE":
            continue  # origin=V9-P3-CONSUME (commit 5e1b9df)
        if "ADAPTIVE" in r.principle_id:
            assert r.origin == "V9-P3-CONSUME-EXTEND", (
                f"{r.principle_id} doit avoir origin=V9-P3-CONSUME-EXTEND, "
                f"origin={r.origin}"
            )


# ── Test 2 : scope préservé (timeframes identiques au source) ────────────


def test_adaptive_scope_preserved_coalition(registry: list[PrincipleRecord]) -> None:
    """COALITION_NODE_ADAPTIVE garde le scope du source (M5/M15/H1/H4)."""
    src = _find("COALITION_NODE", registry)
    adapt = _find("COALITION_NODE_ADAPTIVE", registry)
    assert src is not None and adapt is not None
    assert adapt.scope_timeframes == src.scope_timeframes, (
        f"scope TF divergent : src={src.scope_timeframes} "
        f"adapt={adapt.scope_timeframes}"
    )


def test_adaptive_scope_preserved_antagonist(registry: list[PrincipleRecord]) -> None:
    """ANTAGONIST_NODE_ADAPTIVE garde le scope H1 (scope étroit source)."""
    src = _find("ANTAGONIST_NODE", registry)
    adapt = _find("ANTAGONIST_NODE_ADAPTIVE", registry)
    assert src is not None and adapt is not None
    assert adapt.scope_timeframes == src.scope_timeframes, (
        f"ANTAGONIST_NODE source est H1-only, "
        f"src={src.scope_timeframes} adapt={adapt.scope_timeframes}"
    )


# ── Test 3 : dégradation gracieuse R6 quand P3-WIRE est OFF ───────────────


def test_adaptive_vol_gate_no_trigger_when_p3_wire_off() -> None:
    """ADAPTIVE_VOL_GATE ne déclenche pas si adaptive_*_threshold absents
    (P3-WIRE OFF) — au moins une des conditions de garde is_not_null est
    False → le principe entier ne déclenche pas (évaluation conjointe)."""
    context_off = {
        "vol_regime": "HIGH",  # OK pour le filtre vol
        # adaptive_coalition_threshold : ABSENT (P3-WIRE OFF)
        # adaptive_antagonism_threshold : ABSENT
        "coalition_strength": 10.0,  # valeurs OK
        "antagonismes_count": 5.0,
        "session_marche": "london",  # OK pour le gate session
    }
    regs = load_principles_from_yaml(PRINCIPLES_DIR)
    adaptive = _find("ADAPTIVE_VOL_GATE", regs)
    assert adaptive is not None

    # Le principe entier ne déclenche que si TOUTES les conditions passent.
    # Avec P3-WIRE OFF, les guards is_not_null sont False, donc le principe
    # entier ne peut pas déclencher (court-circuit logique par AND).
    all_pass = all(evaluate_condition(c, context_off) for c in adaptive.conditions)
    assert all_pass is False, (
        "ADAPTIVE_VOL_GATE ne doit PAS déclencher avec P3-WIRE OFF "
        "(au moins un guard adaptive_*_threshold is_not_null doit être False)"
    )
    # Vérifier explicitement que les guards adaptive_*_threshold sont False
    guard_results = [
        evaluate_condition(c, context_off)
        for c in adaptive.conditions
        if c.get("op") == "is_not_null" and c.get("field", "").startswith("adaptive_")
    ]
    assert all(r is False for r in guard_results), (
        f"Tous les guards adaptive_* doivent être False avec P3-WIRE OFF, "
        f"résultats={guard_results}"
    )


def test_coalition_node_adaptive_no_trigger_when_p3_wire_off() -> None:
    """COALITION_NODE_ADAPTIVE ne déclenche pas si adaptive_coalition_threshold
    absent — la première condition (is_not_null) est False."""
    context_off = {
        "state": "ACCUMULATING",
        "coalition_strength": 0.9,
        "coalition_mtf_score": 4,
        "risk_sentiment": "RISK_ON",
        "coalition_news_allow": True,
        # adaptive_coalition_threshold : ABSENT
    }
    regs = load_principles_from_yaml(PRINCIPLES_DIR)
    adapt = _find("COALITION_NODE_ADAPTIVE", regs)
    assert adapt is not None
    first_cond = adapt.conditions[0]
    assert first_cond["field"] == "adaptive_coalition_threshold"
    assert evaluate_condition(first_cond, context_off) is False


def test_antagonist_node_adaptive_no_trigger_when_p3_wire_off() -> None:
    """ANTAGONIST_NODE_ADAPTIVE gated sur adaptive_antagonism_threshold."""
    context_off = {
        "h1_state": "BAISSIERE",
        "m5_state": "BAISSIERE",
        "h1_dir": "BAISSIERE",
        "m5_dir": "BAISSIERE",
        "antagonismes_count": 30.0,
        # adaptive_antagonism_threshold : ABSENT
    }
    regs = load_principles_from_yaml(PRINCIPLES_DIR)
    adapt = _find("ANTAGONIST_NODE_ADAPTIVE", regs)
    assert adapt is not None
    first_cond = adapt.conditions[0]
    assert first_cond["field"] == "adaptive_antagonism_threshold"
    assert evaluate_condition(first_cond, context_off) is False


# ── Test 4 : déclenchement OK quand P3-WIRE est ON ───────────────────────


def test_coalition_node_adaptive_triggers_when_p3_wire_on() -> None:
    """COALITION_NODE_ADAPTIVE : avec adaptive_coalition_threshold présent
    et conditions source OK, la 1re condition (is_not_null) passe."""
    context_on = {
        "adaptive_coalition_threshold": 5.38,  # P3-WIRE ON
        "state": "ACCUMULATING",
        "coalition_strength": 0.9,  # >= 0.5
        "coalition_mtf_score": 4,  # >= 3
        "risk_sentiment": "RISK_ON",  # not in MIXTE
        "coalition_news_allow": True,  # == True
    }
    regs = load_principles_from_yaml(PRINCIPLES_DIR)
    adapt = _find("COALITION_NODE_ADAPTIVE", regs)
    assert adapt is not None

    # La 1re condition (guard) doit passer
    assert evaluate_condition(adapt.conditions[0], context_on) is True
    # Et toutes les conditions du source doivent aussi passer (régression)
    src_conds = _find("COALITION_NODE", regs).conditions
    for cond in src_conds:
        assert evaluate_condition(cond, context_on) is True, (
            f"condition source ne passe pas avec P3-WIRE ON : {cond}"
        )


def test_adaptive_vol_gate_triggers_when_p3_wire_on() -> None:
    """ADAPTIVE_VOL_GATE : tous guards + conditions OK avec P3-WIRE ON."""
    context_on = {
        "vol_regime": "HIGH",
        "adaptive_coalition_threshold": 5.38,
        "adaptive_antagonism_threshold": 31.39,
        "coalition_strength": 10.0,  # >= 5.38
        "antagonismes_count": 5.0,  # <= 31.39
        "session_marche": "london",
    }
    regs = load_principles_from_yaml(PRINCIPLES_DIR)
    adaptive = _find("ADAPTIVE_VOL_GATE", regs)
    assert adaptive is not None
    for cond in adaptive.conditions:
        assert evaluate_condition(cond, context_on) is True, (
            f"condition devrait être True avec P3-WIRE ON : {cond}"
        )


# ── Test 5 : structure / position des guards (en tête des conditions) ───


def test_adaptive_guards_are_first_conditions() -> None:
    """Les conditions de garde is_not_null sont en tête de la liste conditions."""
    regs = load_principles_from_yaml(PRINCIPLES_DIR)
    for r in regs:
        if not r.principle_id.endswith("_ADAPTIVE"):
            continue
        if r.principle_id == "ADAPTIVE_VOL_GATE":
            continue  # livré avant P3-CONSUME-EXTEND, structure potentiellement différente
        # Vérifier que la première condition est bien un guard is_not_null
        first = r.conditions[0]
        assert first["op"] == "is_not_null", (
            f"{r.principle_id} : la 1re condition doit être un guard "
            f"is_not_null, op={first['op']}"
        )
        assert first["field"].startswith("adaptive_"), (
            f"{r.principle_id} : la 1re condition doit gate un champ "
            f"adaptive_*, field={first['field']}"
        )


# ── Test 6 : au moins une source YAML existe pour chaque _ADAPTIVE ──────


def test_each_adaptive_has_origin_source() -> None:
    """Chaque _ADAPTIVE a un origin source V7 ou V9-P3-CONSUME (jamais None)."""
    regs = load_principles_from_yaml(PRINCIPLES_DIR)
    for r in regs:
        if not r.principle_id.endswith("_ADAPTIVE"):
            continue
        assert r.origin in ("V9-P3-CONSUME", "V9-P3-CONSUME-EXTEND"), (
            f"{r.principle_id} : origin inattendu = {r.origin}"
        )
