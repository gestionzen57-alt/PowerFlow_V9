"""Tests — SignalFusionEngine (Chantier B DIVERSIFY 2026-07-16).

Couvre les 3 règles de fusion, la précédence, les conflits, les cas non
fusionnables, la robustesse aux entrées dégénérées, et l'intégration
additive dans SignalGenerator._build_active_signal (jamais abaisser la
confiance, jamais retourner la direction).
"""

from __future__ import annotations

from core.v9.signal_fusion_engine import SignalFusionEngine
from core.v9.signal_generator import SignalGenerator, SymbolCurrencies


def _fe() -> SignalFusionEngine:
    return SignalFusionEngine()


def _p(direction, conf, pid="P"):
    return {"principle_id": pid, "direction": direction, "confidence": conf}


# ── Règle double_50 (2 principes ≥ 50) ────────────────────────────────

def test_double_50_two_principles_same_direction():
    r = _fe().fuse([_p("haussiere", 55), _p("haussiere", 55)])
    assert r is not None
    assert r["direction"] == "haussiere"
    assert r["confidence"] == 65
    assert r["fusion_rule"] == "double_min_conf"
    assert r["n_fused"] == 2


def test_double_50_exactly_at_threshold():
    r = _fe().fuse([_p("baissiere", 50), _p("baissiere", 50)])
    assert r["confidence"] == 65
    assert r["direction"] == "baissiere"


def test_two_principles_below_50_no_fusion():
    # 55 + 45 : un seul ≥50, deux ≥40 (pas 3) → aucune règle
    assert _fe().fuse([_p("haussiere", 55), _p("haussiere", 45)]) is None


# ── Règle triple_40 (3 principes ≥ 40) ────────────────────────────────

def test_triple_40_three_principles():
    r = _fe().fuse([_p("haussiere", 45), _p("haussiere", 45), _p("haussiere", 45)])
    assert r["confidence"] == 70
    assert r["fusion_rule"] == "triple_min_conf"
    assert r["n_fused"] == 3


def test_triple_40_exactly_at_threshold():
    r = _fe().fuse([_p("baissiere", 40), _p("baissiere", 40), _p("baissiere", 40)])
    assert r["confidence"] == 70


def test_two_at_40_not_triple():
    # 2 principes à 40 : pas 3 ≥40, pas 2 ≥50 → None
    assert _fe().fuse([_p("haussiere", 40), _p("haussiere", 40)]) is None


# ── Règle boost (1 ≥ 80 + 1 autre ≥ 50) ───────────────────────────────

def test_boost_high_plus_partner():
    r = _fe().fuse([_p("haussiere", 85), _p("haussiere", 55)])
    assert r["confidence"] == 95  # plus fort (85) + 10
    assert r["fusion_rule"] == "boost_high_plus_partner"


def test_boost_two_high_principles():
    r = _fe().fuse([_p("haussiere", 90), _p("haussiere", 85)])
    assert r["confidence"] == 100  # 90 + 10


def test_boost_caps_at_100():
    r = _fe().fuse([_p("baissiere", 95), _p("baissiere", 60)])
    assert r["confidence"] == 100  # 95 + 10 plafonné


def test_boost_not_applicable_when_partner_below_50():
    # 85 + 45 : le "partenaire" à 45 < 50 → pas de boost, pas d'autre règle
    assert _fe().fuse([_p("haussiere", 85), _p("haussiere", 45)]) is None


def test_boost_precedence_over_triple():
    # 85, 55, 45 : boost applicable ET triple_40 applicable → boost gagne
    r = _fe().fuse([_p("haussiere", 85), _p("haussiere", 55), _p("haussiere", 45)])
    assert r["confidence"] == 95
    assert r["fusion_rule"] == "boost_high_plus_partner"


# ── Conflits (directions opposées) ────────────────────────────────────

def test_conflict_opposite_strong_directions():
    assert _fe().fuse([_p("haussiere", 80), _p("baissiere", 80)]) is None


def test_conflict_even_with_majority_one_side():
    # 2 haussiere + 1 baissiere : conflit → None (fusion conservatrice)
    assert _fe().fuse([_p("haussiere", 55), _p("haussiere", 55), _p("baissiere", 45)]) is None


# ── Cas non fusionnables / robustesse ─────────────────────────────────

def test_single_principle_no_fusion():
    assert _fe().fuse([_p("haussiere", 90)]) is None


def test_empty_list_returns_none():
    assert _fe().fuse([]) is None


def test_neutre_and_none_directions_ignored():
    # 1 seul directionnel après filtrage → None
    assert _fe().fuse([_p("haussiere", 80), _p("neutre", 90), _p(None, 90)]) is None


def test_non_numeric_confidence_ignored():
    # confidences non numériques filtrées → 1 seul directionnel valide → None
    assert _fe().fuse([_p("haussiere", 60), _p("haussiere", None), _p("haussiere", "x")]) is None


def test_result_carries_principle_ids():
    r = _fe().fuse([_p("haussiere", 55, "A"), _p("haussiere", 55, "B")])
    assert set(r["principle_ids"]) == {"A", "B"}


def test_custom_thresholds_via_constructor():
    fe = SignalFusionEngine(double_min_conf=30.0, double_confidence=60.0)
    r = fe.fuse([_p("haussiere", 35), _p("haussiere", 35)])
    assert r["confidence"] == 60
    assert r["fusion_rule"] == "double_min_conf"


# ── Intégration SignalGenerator._build_active_signal ──────────────────

def _sg(tmp_path):
    return SignalGenerator(db_path=tmp_path / "sig_fusion.db")


def test_signal_generator_boosts_on_weak_agreement(tmp_path):
    """3 principes faibles (45) concordants sur la base → fusion triple_40
    relève la confiance de 45 (moyenne) à 70."""
    sg = _sg(tmp_path)
    triggered = [
        {"principle_id": "A", "direction": "haussiere", "currency": "GBP", "confidence": 45},
        {"principle_id": "B", "direction": "haussiere", "currency": "GBP", "confidence": 45},
        {"principle_id": "C", "direction": "haussiere", "currency": "GBP", "confidence": 45},
    ]
    signal = sg._build_active_signal(
        "snap-1", "GBPUSD", "M15", SymbolCurrencies("GBP", "USD"),
        "CASSURE", "expl-1", "exploitable", triggered, False,
    )
    assert signal["direction"] == "haussiere"
    assert signal["confiance"] == 70
    assert signal["fusion_rule"] == "triple_min_conf"
    assert signal["fusion_n"] == 3


def test_signal_generator_fusion_never_lowers_confidence(tmp_path):
    """3 principes forts (75) : la moyenne (75) dépasse la fusion triple_40
    (70) → la fusion N'EST PAS appliquée (additif, jamais abaisser)."""
    sg = _sg(tmp_path)
    triggered = [
        {"principle_id": "A", "direction": "haussiere", "currency": "GBP", "confidence": 75},
        {"principle_id": "B", "direction": "haussiere", "currency": "GBP", "confidence": 75},
        {"principle_id": "C", "direction": "haussiere", "currency": "GBP", "confidence": 75},
    ]
    signal = sg._build_active_signal(
        "snap-2", "GBPUSD", "M15", SymbolCurrencies("GBP", "USD"),
        "CASSURE", "expl-2", "exploitable", triggered, False,
    )
    assert signal["confiance"] == 70  # plafond 70 (motion CEO 22/07), was 75
    assert signal["fusion_rule"] is None


def test_signal_generator_fusion_not_applied_on_conflict(tmp_path):
    """Directions opposées (base GBP haussier vs quote USD haussier = baissier
    pour la paire) → conflit → fusion None, confiance = moyenne inchangée."""
    sg = _sg(tmp_path)
    triggered = [
        {"principle_id": "A", "direction": "haussiere", "currency": "GBP", "confidence": 55},
        {"principle_id": "B", "direction": "haussiere", "currency": "USD", "confidence": 55},
    ]
    signal = sg._build_active_signal(
        "snap-3", "GBPUSD", "M15", SymbolCurrencies("GBP", "USD"),
        "CASSURE", "expl-3", "exploitable", triggered, False,
    )
    # GBP haussier → paire haussiere ; USD haussier → paire baissiere : conflit.
    assert signal["fusion_rule"] is None
