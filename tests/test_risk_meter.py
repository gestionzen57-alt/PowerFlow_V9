"""Tests unitaires — core.v9.risk_meter.RiskMeter.assess()."""

from __future__ import annotations

import pytest

from core.v9.risk_meter import (
    RISK_OFF_DEVISES,
    RISK_ON_DEVISES,
    assess,
)


def _coalition(devises, intensite=60.0, age_bars=1, intensite_trend="stable", stabilite=1.0):
    """Helper : crée une coalition enrichie façon Tâche A."""
    return {
        "devises_alignees": devises,
        "intensite_alignement": intensite,
        "leader": devises[0],
        "rotation_leadership": {"detectee": False, "ancien_leader": None, "nouveau_leader": None},
        "age_bars": age_bars,
        "intensite_trend": intensite_trend,
        "stabilite": stabilite,
    }


def _directions(**kwargs):
    """Helper : directions par devise, défaut 'neutre'."""
    base = {d: "neutre" for d in ["USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD"]}
    base.update({k.upper(): v for k, v in kwargs.items()})
    return base


# ── Constantes institutionnelles ──────────────────────────────

def test_risk_on_devises_constant():
    assert RISK_ON_DEVISES == frozenset({"AUD", "NZD", "CAD", "GBP"})


def test_risk_off_devises_constant():
    assert RISK_OFF_DEVISES == frozenset({"JPY", "CHF", "USD"})


# ── Sentiments de base ────────────────────────────────────────

def test_assess_returns_dict_with_eight_keys():
    result = assess([], _directions())
    assert set(result.keys()) == {
        "risk_sentiment",
        "risk_confidence",
        "risk_on_score",
        "risk_off_score",
        "dominant_bloc",
        "refuge_bloc_direction",
        "procyclique_bloc_direction",
        "persistance_confirmee",
    }


def test_assess_neutral_when_no_coalitions():
    result = assess([], _directions())
    assert result["risk_sentiment"] == "NEUTRE"
    assert result["risk_confidence"] == 40  # base
    assert result["risk_on_score"] == 0.0
    assert result["risk_off_score"] == 0.0
    assert result["persistance_confirmee"] is False


def test_assess_risk_on_procycliques_up_refuges_down():
    """RISK_ON : procycliques haussières + refuges baissières."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=70.0, age_bars=3, stabilite=0.8, intensite_trend="montante"),
        _coalition(["JPY", "CHF"], intensite=30.0, age_bars=2, stabilite=0.6),
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere", JPY="baissiere", CHF="baissiere")

    result = assess(coalitions, directions)

    assert result["risk_sentiment"] == "RISK_ON"
    # base 40 + opposition 20 + age>=5? non + stab>=0.7? oui (0.8) + trend montante? oui +10
    # = 40 + 20 + 0 + 10 + 10 = 80
    assert result["risk_confidence"] == 80
    assert result["risk_on_score"] > 0.0
    # Le bloc refuge est baissier -> score risk_off_score (côté haussier) = 0
    assert result["risk_off_score"] == 0.0
    assert result["refuge_bloc_direction"] == "baissiere"
    assert result["procyclique_bloc_direction"] == "haussiere"
    assert result["persistance_confirmee"] is True  # age_bars=3 >= 3
    assert set(result["dominant_bloc"]) == {"AUD", "NZD", "JPY", "CHF"}


def test_assess_risk_off_refuges_up_procycliques_down():
    """RISK_OFF : refuges haussières + procycliques baissières."""
    coalitions = [
        _coalition(["USD", "JPY"], intensite=75.0, age_bars=5, stabilite=0.9, intensite_trend="montante"),
        _coalition(["AUD", "CAD"], intensite=25.0, age_bars=2, stabilite=0.5),
    ]
    directions = _directions(USD="haussiere", JPY="haussiere", AUD="baissiere", CAD="baissiere")

    result = assess(coalitions, directions)

    assert result["risk_sentiment"] == "RISK_OFF"
    # base 40 + opposition 20 + age>=5? oui +15 + stab>=0.7? oui +10 + trend montante? oui +10
    # = 40 + 20 + 15 + 10 + 10 = 95
    assert result["risk_confidence"] == 95
    assert result["risk_off_score"] > 0.0
    assert result["risk_on_score"] == 0.0
    assert result["persistance_confirmee"] is True  # age=5 >= 3


def test_assess_mixte_only_procycliques_present():
    """MIXTE : seul le bloc procyclique s'exprime, pas d'opposition canonique."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=65.0),
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere")

    result = assess(coalitions, directions)

    # RISK_ON exige AUSSI le bloc refuge baissier. Sans ça = MIXTE.
    assert result["risk_sentiment"] == "MIXTE"
    # base 40, pas d'opposition -> 40 (pas de bonus +20)
    # age=1 < 5 -> pas de +15 ; stab=1.0 >= 0.7 -> +10 ; trend stable -> pas de +10
    # = 40 + 10 = 50
    assert result["risk_confidence"] == 50


def test_assess_mixte_only_refuges_present():
    coalitions = [
        _coalition(["JPY", "CHF"], intensite=65.0),
    ]
    directions = _directions(JPY="haussiere", CHF="haussiere")

    result = assess(coalitions, directions)

    assert result["risk_sentiment"] == "MIXTE"
    assert result["risk_off_score"] > 0.0


def test_assess_risk_on_requires_both_blocks_opposite():
    """Si procyclique haussière mais refuge haussière aussi (les deux
    dans le même sens), ce n'est PAS un RISK_ON : c'est MIXTE."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=70.0),
        _coalition(["JPY", "CHF"], intensite=70.0),
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere", JPY="haussiere", CHF="haussiere")

    result = assess(coalitions, directions)

    # Les deux blocs dans le même sens -> pas d'opposition nette
    assert result["risk_sentiment"] == "MIXTE"


# ── Bonus de confidence ────────────────────────────────────────

def test_assess_confidence_bonus_mtf_emboitement():
    """+5 si emboitement MTF détecté."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=70.0),
        _coalition(["JPY", "CHF"], intensite=30.0),
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere", JPY="baissiere", CHF="baissiere")

    result_no_mtf = assess(coalitions, directions, mtf_emboitement=False)
    result_mtf = assess(coalitions, directions, mtf_emboitement=True)

    assert result_mtf["risk_confidence"] == result_no_mtf["risk_confidence"] + 5


def test_assess_confidence_clamped_to_100():
    """Confidence est clampée entre 0 et 100 même si tous les bonus s'appliquent."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=80.0, age_bars=10, stabilite=1.0, intensite_trend="montante"),
        _coalition(["JPY", "CHF"], intensite=20.0, age_bars=10, stabilite=1.0),
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere", JPY="baissiere", CHF="baissiere")

    result = assess(coalitions, directions, mtf_emboitement=True)

    # base 40 + opposition 20 + age>=5 15 + stab>=0.7 10 + trend montante 10 + emboitement 5 = 100
    assert result["risk_confidence"] == 100
    assert result["persistance_confirmee"] is True  # age=10 >= 3


def test_assess_confidence_clamped_to_0_min():
    """Confidence ne descend jamais sous 0 (clamp)."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=10.0),  # tout faible
    ]
    directions = _directions(AUD="neutre")  # aucune direction utile

    result = assess(coalitions, directions)
    assert result["risk_confidence"] >= 0


# ── Persistance confirmée ─────────────────────────────────────

def test_assess_persistance_requires_age_at_least_3():
    """persistance_confirmee=False si age_bars < 3 même si RISK_ON détecté."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=70.0, age_bars=2),  # age < 3
        _coalition(["JPY", "CHF"], intensite=30.0, age_bars=2),
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere", JPY="baissiere", CHF="baissiere")

    result = assess(coalitions, directions)

    assert result["risk_sentiment"] == "RISK_ON"
    assert result["persistance_confirmee"] is False  # age=2 < 3


def test_assess_persistance_false_for_mixte_or_neutre():
    """persistance_confirmee=False pour sentiments != RISK_ON/RISK_OFF."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=70.0, age_bars=10),  # age>=3 mais
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere")  # pas d'opposition -> MIXTE

    result = assess(coalitions, directions)
    assert result["persistance_confirmee"] is False  # MIXTE


# ── Filtrage coalition mixte ──────────────────────────────────

def test_assess_ignores_coalition_mostly_outside_bloc():
    """Une coalition majoritairement hors du groupe filtre est ignorée."""
    # AUD/JPY : 1 devise procyclique sur 2 -> on ignore (majorité JPY = refuge)
    coalitions = [
        _coalition(["AUD", "JPY"], intensite=80.0, age_bars=3),
    ]
    directions = _directions(AUD="haussiere", JPY="baussiere")  # AUD haussier + JPY baissier

    result = assess(coalitions, directions)

    # La coalition AUD/JPY n'est pas comptée comme procyclique (majorité hors)
    # -> bloc procyclique = None, sentiment NEUTRE
    assert result["risk_sentiment"] == "NEUTRE"


# ── Fallbacks (données manquantes) ────────────────────────────

def test_assess_handles_missing_intensite_alignement():
    coalitions = [
        {
            "devises_alignees": ["AUD", "NZD"],
            "leader": "AUD",
            "age_bars": 3,
            "intensite_trend": "stable",
            "stabilite": 0.7,
            # pas de intensite_alignement
        },
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere")

    # Ne lève pas d'exception -> fallback 0.0
    result = assess(coalitions, directions)
    assert result["risk_sentiment"] == "MIXTE"  # pas de bloc refuge opposé
    assert result["risk_on_score"] == 0.0


def test_assess_handles_missing_direction_for_devise():
    """Si une devise d'une coalition n'a pas de direction, on l'ignore."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=70.0),
    ]
    directions = _directions(AUD="haussiere")  # NZD manque -> "neutre"

    result = assess(coalitions, directions)

    # NZD sans direction explicite -> coalition ignorée
    assert result["risk_sentiment"] == "NEUTRE"


# ── Cohérence avec scènes enrichies (Tâche A) ─────────────────

def test_assess_uses_coalition_enrichment_fields():
    """Le bonus age_bars et intensite_trend provient des champs Tâche A."""
    coalitions = [
        _coalition(
            ["AUD", "NZD"], intensite=70.0,
            age_bars=6,  # >= 5 -> +15
            intensite_trend="montante",  # +10
            stabilite=0.8,  # >= 0.7 -> +10
        ),
        _coalition(["JPY", "CHF"], intensite=30.0),
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere", JPY="baissiere", CHF="baissiere")

    result = assess(coalitions, directions)

    # base 40 + opposition 20 + age>=5 15 + stab 10 + trend 10 = 95
    assert result["risk_confidence"] == 95


def test_assess_dominant_coalition_selection():
    """La coalition dominante = max(age_bars * intensite_alignement)."""
    # Coalition 1 : age=2, intensite=50 -> score 100
    # Coalition 2 : age=5, intensite=70 -> score 350 (dominante)
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=50.0, age_bars=2, stabilite=0.5),
        _coalition(["CAD", "GBP"], intensite=70.0, age_bars=5, stabilite=0.8),
        _coalition(["JPY", "CHF"], intensite=30.0, age_bars=4, stabilite=0.7),  # refuge baissier
    ]
    directions = _directions(
        AUD="haussiere", NZD="haussiere", CAD="haussiere", GBP="haussiere",
        JPY="baissiere", CHF="baissiere",
    )

    result = assess(coalitions, directions)

    # procycliques haussières + refuge baissière = RISK_ON
    # Coalition dominante = CAD/GBP (score 350) -> stab>=0.7 (+10), age>=5 (+15)
    # base 40 + opposition 20 + age 15 + stab 10 = 85
    assert result["risk_sentiment"] == "RISK_ON"
    assert result["risk_confidence"] == 85


# ── Bonus emboitement MTF ─────────────────────────────────────

def test_assess_with_mtf_emboitement_flag():
    """Le flag mtf_emboitement ajoute +5 à la confidence."""
    coalitions = [
        _coalition(["AUD", "NZD"], intensite=70.0),
        _coalition(["JPY", "CHF"], intensite=30.0),
    ]
    directions = _directions(AUD="haussiere", NZD="haussiere", JPY="baissiere", CHF="baissiere")

    r1 = assess(coalitions, directions, mtf_emboitement=False)
    r2 = assess(coalitions, directions, mtf_emboitement=True)

    assert r2["risk_confidence"] - r1["risk_confidence"] == 5