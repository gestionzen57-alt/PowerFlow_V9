"""Tests P3-CONSUME (2026-07-14) — consommation reelle des seuils
adaptatifs par un principe SHADOW (ADAPTIVE_VOL_GATE).

Doctrine :
- R6  : pas de simulation, evaluation reelle du YAML via PrincipleEngine.
- R7  : zero regression sur les tests existants (cf. test_loads_all_*
        qui passent de 26 a 27 principes).
- R25' : ADAPTIVE_VOL_GATE reste SHADOW, pas de promotion ACTIVE sans
        motion CEO.
- R26 : tests verts avant commit.

Module teste : core/v9/principles/ADAPTIVE_VOL_GATE.yaml + integration
via core/v9/principle_engine.evaluate_principle().
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.v9.principle_engine import (
    PrincipleRecord,
    evaluate_condition,
    evaluate_principle,
    load_principles_from_yaml,
)


# ── Catalogue ──────────────────────────────────────────────

def test_adaptive_vol_gate_in_catalogue():
    """Le principe ADAPTIVE_VOL_GATE est charge depuis le YAML."""
    principles = load_principles_from_yaml()
    ids = {p.principle_id for p in principles}
    assert "ADAPTIVE_VOL_GATE" in ids, f"ADAPTIVE_VOL_GATE absent du catalogue ({len(principles)} principes)"


def test_catalogue_count_is_53():
    """54 principes YAML depuis DIVERSIFY couleur 2026-07-16 (Gap 5) :
    53 + VELOCITY_CLIMAX_GUARD (SHADOW, 1er consommateur de vélocité)."""
    principles = load_principles_from_yaml()
    # 22/07: +GRAMMAR_CROISEMENT_CONFIRMATION → 56.
    assert len(principles) == 56, f"attendu 56 (55 + VOLUME_CONFIRMATION), got {len(principles)}"


def test_adaptive_vol_gate_is_shadow_node_rule():
    """ADAPTIVE_VOL_GATE est node_rule. Statut v9 = SHADOW depuis DIVERSIFY
    2026-07-16 (Mix CEO) : réanimé par un fix d'échelle coalition (comparaison
    normalisée 0-1), en observation 24-48h avant re-promotion ACTIVE (R25')."""
    principles = load_principles_from_yaml()
    p = next(p for p in principles if p.principle_id == "ADAPTIVE_VOL_GATE")
    assert p.v9_status == "SHADOW", f"Attendu SHADOW (DIVERSIFY Mix), got {p.v9_status}"
    assert p.kind == "node_rule"


def test_adaptive_vol_gate_uses_value_field_for_adaptive_thresholds():
    """Le principe utilise value_field sur coalition_strength et
    antagonismes_count pour consommer les seuils adaptatifs poses
    par P3-WIRE dans _load_shared_context (commit 1babf14).
    FIX DIVERSIFY 2026-07-16 : coalition compare au seuil NORMALISÉ 0-1
    (adaptive_coalition_threshold_norm), pas au seuil brut."""
    principles = load_principles_from_yaml()
    p = next(p for p in principles if p.principle_id == "ADAPTIVE_VOL_GATE")

    value_field_uses = [
        c for c in p.conditions
        if c.get("value_field") in ("adaptive_coalition_threshold_norm", "adaptive_antagonism_threshold")
    ]
    assert len(value_field_uses) == 2, (
        f"attendu 2 conditions avec value_field adaptive_*, "
        f"got {len(value_field_uses)} : {value_field_uses}"
    )


# ── Evaluation : cas passants ──────────────────────────────

def _build_principle_from_yaml() -> PrincipleRecord:
    """Helper : charge le principe depuis le catalogue."""
    principles = load_principles_from_yaml()
    return next(p for p in principles if p.principle_id == "ADAPTIVE_VOL_GATE")


def test_triggers_when_vol_high_and_adaptive_thresholds_satisfied():
    """vol_regime=HIGH + coalition_strength >= adaptive_coalition_threshold
    + antagonismes_count <= adaptive_antagonism_threshold + session
    non-null -> declenche (kind node_rule)."""
    p = _build_principle_from_yaml()
    context = {
        "vol_regime": "HIGH",
        # FIX DIVERSIFY 2026-07-16 : coalition_strength est un ratio 0-1
        # comparé au seuil normalisé (0.40 * mult HIGH ≈ 0.52).
        "coalition_strength": 0.8,  # >= 0.52 ✓
        "adaptive_coalition_threshold_norm": 0.52,
        # baseline 31.39 * HIGH(1.3) = ~40.8, antagonism 30 <= 40.8 ✓
        "antagonismes_count": 30.0,
        "session_marche": "london",
        # Champs adaptatifs (seraint poses par P3-WIRE en prod).
        "adaptive_coalition_threshold": 7.0,
        "adaptive_antagonism_threshold": 40.8,
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is True, f"devrait declencher : {result}"


def test_triggers_when_vol_extreme():
    """En EXTREME, le multiplicateur est 1.5, donc le seuil normalisé
    est plus grand (0.40 * 1.5 = 0.60). Test que la logique reste correcte."""
    p = _build_principle_from_yaml()
    context = {
        "vol_regime": "EXTREME",
        # FIX DIVERSIFY 2026-07-16 : ratio 0-1 vs seuil normalisé (0.40*1.5=0.60).
        "coalition_strength": 0.85,  # >= 0.60 ✓
        "adaptive_coalition_threshold_norm": 0.60,
        # 31.39 * 1.5 = 47.09
        "antagonismes_count": 40.0,
        "session_marche": "overlap",
        "adaptive_coalition_threshold": 8.07,
        "adaptive_antagonism_threshold": 47.09,
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is True, f"EXTREME devrait declencher : {result}"


# ── Evaluation : cas NON passants ──────────────────────────

def test_does_not_trigger_in_normal_vol_regime():
    """Le principe est filtre sur vol_regime in [HIGH, EXTREME].
    En NORMAL, il ne doit jamais declencher (P3 ne sert qu'en vol elevee)."""
    p = _build_principle_from_yaml()
    context = {
        "vol_regime": "NORMAL",
        "coalition_strength": 100.0,  # super fort, peu importe
        "antagonismes_count": 0.0,
        "session_marche": "london",
        "adaptive_coalition_threshold": 5.0,
        "adaptive_antagonism_threshold": 100.0,
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is False
    assert "vol_regime" in result.get("reason", "") or "NORMAL" in str(context)


def test_does_not_trigger_when_adaptive_thresholds_missing():
    """Si P3-WIRE est OFF, les champs adaptive_*_threshold sont absents
    du context. Les conditions value_field retombent sur None, le
    principe ne declenche pas (degradation gracieuse R6)."""
    p = _build_principle_from_yaml()
    context = {
        "vol_regime": "HIGH",
        "coalition_strength": 7.5,
        "antagonismes_count": 30.0,
        "session_marche": "london",
        # PAS de adaptive_coalition_threshold ni adaptive_antagonism_threshold
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is False, (
        f"sans seuils adaptatifs, le principe ne doit pas declencher : {result}"
    )


def test_does_not_trigger_when_coalition_below_adaptive_threshold():
    """Si coalition_strength < adaptive_coalition_threshold, declin
    (vol haute + coalition faible = pas de signal)."""
    p = _build_principle_from_yaml()
    context = {
        "vol_regime": "HIGH",
        "coalition_strength": 0.3,  # < 0.52 (seuil normalisé)
        "adaptive_coalition_threshold_norm": 0.52,
        "antagonismes_count": 30.0,
        "session_marche": "london",
        "adaptive_coalition_threshold": 7.0,
        "adaptive_antagonism_threshold": 40.8,
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is False


def test_does_not_trigger_when_antagonism_above_adaptive_threshold():
    """Si antagonismes_count > adaptive_antagonism_threshold, declin
    (vol haute + coalition OK mais trop d'antagonisme = pas de signal)."""
    p = _build_principle_from_yaml()
    context = {
        "vol_regime": "HIGH",
        "coalition_strength": 0.8,  # >= 0.52 (coalition OK)
        "adaptive_coalition_threshold_norm": 0.52,
        "antagonismes_count": 50.0,  # > 40.8 (le bloqueur)
        "session_marche": "london",
        "adaptive_coalition_threshold": 7.0,
        "adaptive_antagonism_threshold": 40.8,
    }
    result = evaluate_principle(p, context)
    assert result["triggered"] is False


# ── evaluate_condition direct : sanity check value_field ───

def test_evaluate_condition_value_field_numeric():
    """Sanity check : evaluate_condition gere value_field numerique.
    Meme pattern que ANTAGONIST_NODE.yaml (h1_dir vs m5_dir) mais en
    numerique (coalition_strength vs adaptive_coalition_threshold).

    Note R6/R25' : quand `value_field` reference un champ absent du
    context (target=None), evaluate_condition leve un TypeError sur
    la comparaison (float >= None). Le pattern de defense est en
    AMONT dans le YAML (porte `is_not_null` sur adaptive_coalition_threshold
    AVANT la condition value_field), pas dans evaluate_condition lui-meme.
    C'est un choix assumé du code (R22 - 1 commit par chantier, R8 -
    ne pas modifier core/v9/* sans backup MD5 + DECISIONS_LOG).
    """
    cond = {
        "field": "coalition_strength",
        "op": ">=",
        "value_field": "adaptive_coalition_threshold",
    }
    # Cas passant : les deux champs sont presents.
    assert evaluate_condition(cond, {
        "coalition_strength": 8.0,
        "adaptive_coalition_threshold": 7.0,
    }) is True
    # Cas non passant : la valeur est sous le seuil.
    assert evaluate_condition(cond, {
        "coalition_strength": 6.0,
        "adaptive_coalition_threshold": 7.0,
    }) is False
    # Cas value=None (champ source absent) : retourne False (degradation
    # gracieuse cote value, voir evaluate_condition ligne 195-196).
    assert evaluate_condition(cond, {"adaptive_coalition_threshold": 5.0}) is False
    # Cas target=None (value_field absent) : LEVE TypeError. Le YAML
    # doit proteger en amont avec is_not_null (degradation gracieuse
    # dans le YAML, pas dans le moteur). C'est le pattern documente
    # dans ADAPTIVE_VOL_GATE.yaml (lignes 33-44).
    with pytest.raises(TypeError):
        evaluate_condition(cond, {"coalition_strength": 5.0})
