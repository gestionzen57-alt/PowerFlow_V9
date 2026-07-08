"""Tests unitaires — PRICE_LAG_AT_NODE_BIRTH stale guard (Phase 14b CEO).

Verrouillage du fix contre le défaut identifié le 2026-07-08 :
le YAML ne filtrait pas le champ stale, ce qui faisait passer
la trigger rate de 2-4% (baseline) à 70-95% quand le snapshot
de prix devenait stale. Corrigé par ajout d'une condition
`stale == false` en tête du bloc conditions.

Audit H3 confirmé : corrélation stale M5 ↔ triggers (Pearson 0.335
mais bucket à seuil 85%) — quand forces_snapshot.stale=True, pf_mid
reste gelé, tension_score reste ACCUMULATING, les 3 conditions YAML
restent vraies ⇒ trigger systématique avec confiance 96-100.

Le champ `stale` est déjà propagé dans le contexte par
`core.v9.principle_engine._load_shared_context` (ligne 347).
Le fix est purement déclaratif (YAML only), périmètre
principles/* gelé respecté.
"""

from __future__ import annotations

import pytest

from core.v9.principle_engine import (
    evaluate_principle,
    load_principles_from_yaml,
)

PRICE_LAG_ID = "PRICE_LAG_AT_NODE_BIRTH"


def _price_lag_record():
    for p in load_principles_from_yaml():
        if p.principle_id == PRICE_LAG_ID:
            return p
    raise AssertionError(f"{PRICE_LAG_ID} absent du catalogue YAML")


def _ctx(stale: bool, state="ACCUMULATING", tension=1.4):
    return {
        "stale": stale,
        "state": state,
        "tension_score": tension,
        "pf_mid": 1.3355,
        "z_extreme_dir": "UP",
    }


# ── Verrouillage structurel du YAML ──────────────────────────
def test_price_lag_yaml_has_stale_guard_condition():
    """Le YAML DOIT contenir une condition stale==false en première position.

    Verrouillage structurel : si quelqu'un retire la garde sans
    mettre à jour ce test, pytest crie.
    """
    p = _price_lag_record()
    assert p.conditions, "PRICE_LAG doit avoir au moins 1 condition"
    first = p.conditions[0]
    assert first["field"] == "stale", (
        f"première condition doit être stale guard, reçu: {first['field']!r}"
    )
    assert first["op"] == "=="
    assert first["value"] is False


# ── Comportement : stale=True → pas de trigger ───────────────
def test_price_lag_does_not_trigger_when_stale():
    """Le défaut : à stale=True + state=ACCUMULATING + tension=1.4,
    le principe NE DOIT PAS déclencher (avant fix: triggered=True)."""
    p = _price_lag_record()
    result = evaluate_principle(p, _ctx(stale=True))
    assert result["triggered"] is False, (
        f"PRICE_LAG a déclenché sur snapshot stale — guard absent ! "
        f"reason={result['reason']!r}"
    )
    assert result["reason"] == "condition_non_remplie:stale"


# ── Comportement nominal préservé ─────────────────────────────
def test_price_lag_triggers_when_fresh_and_other_conditions_met():
    """Régression : le comportement nominal reste intact (stale=False,
    state=ACCUMULATING, tension=1.4, pf_mid présent)."""
    p = _price_lag_record()
    result = evaluate_principle(p, _ctx(stale=False))
    assert result["triggered"] is True
    assert result["reason"] == "conditions_remplies"


# ── Performance : stale en tête pour court-circuit CPU ───────
def test_price_lag_stale_short_circuits_first():
    """Performance : stale guard doit être évalué EN PREMIER.

    Si on inverse l'ordre, evaluate_principle continue d'évaluer
    les 2 autres conditions (state, tension_score, pf_mid) avant
    de s'arrêter — gaspillage CPU inutile à chaque snapshot stale.

    Le snapshot stale est l'état dominant sur sessions calmes
    (Tokyo été : ~95% stale M5 07-07T21 → 07-08T06).
    """
    p = _price_lag_record()
    first = p.conditions[0]
    assert first["field"] == "stale", (
        "stale guard doit être 1ère condition (court-circuit CPU)"
    )