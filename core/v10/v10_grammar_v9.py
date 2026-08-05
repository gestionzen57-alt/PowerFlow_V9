"""V10 Grammar V9 — portage additif des concepts de grammaire V9 (Phase R).

Porte les concepts de grammaire V9 manquants dans V10, adaptés à la lecture
V10 (régime HMM + forces natives + market context). Additif pur R2 (0 import
core/v9/), chaque concept est une fonction pure fail-open R6.

Concepts portés (les "meilleurs de V9" étudiés) :
  - LEADER_FOLLOWER : rotation de leadership de devise (coalition).
  - PULLBACK : retracement dans la tendance (bascule faible).
  - TENSION : pliure + tension_score élevé (accumulation de pression).
  - RESPIRATION : zone de respiration (compression → expansion).
  - LOCK : compression + respiration (verrouillage de range).
  - OPPOSITION : antagonismes multiples + bascule (conflit de devises).

Chaque concept retourne un dict {detected, direction, confidence, audit}
consommable par le pipeline de décision V10.

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7, R9 audit, R10.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class GrammarSignal:
    concept: str = ""
    detected: bool = False
    direction: str = "NEUTRAL"   # BULLISH / BEARISH / NEUTRAL
    confidence: float = 0.0     # [0,1]
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "concept": self.concept,
            "detected": self.detected,
            "direction": self.direction,
            "confidence": round(self.confidence, 3),
            "audit": dict(self.audit),
        }


def _bias_from_regime(regime_name: str) -> str:
    """Bias directionnel depuis le régime (aligné V10)."""
    if regime_name in ("TRENDING_UP", "MARKUP", "ACCUMULATION"):
        return "BULLISH"
    if regime_name in ("TRENDING_DOWN", "MARKDOWN", "DISTRIBUTION"):
        return "BEARISH"
    return "NEUTRAL"


def leader_follower(regime_name: str, leader: Optional[str],
                    follower: Optional[str]) -> GrammarSignal:
    """LEADER_FOLLOWER : rotation de leadership de devise.

    Détecté si un leader est identifié ET un follower (devise qui suit).
    Direction = bias du régime. Confiance = 0.7 si leader présent.
    """
    g = GrammarSignal(concept="LEADER_FOLLOWER")
    if not leader or not follower:
        g.audit["reason"] = "no_leader_follower"
        return g
    g.detected = True
    g.direction = _bias_from_regime(regime_name)
    g.confidence = 0.7
    g.audit = {"leader": leader, "follower": follower,
               "regime": regime_name}
    return g


def pullback(regime_name: str, bascule_detectee: bool,
             bascule_intensite: float, trend_direction: str) -> GrammarSignal:
    """PULLBACK : retracement dans la tendance (bascule faible).

    Détecté si pas de bascule forte (intensité ≤ 30) ET tendance claire.
    Direction = sens de la tendance (on trade le retracement vers la tendance).
    """
    g = GrammarSignal(concept="PULLBACK")
    if bascule_detectee and bascule_intensite > 30:
        g.audit["reason"] = "bascule_forte"
        return g
    bias = _bias_from_regime(regime_name)
    if bias == "NEUTRAL":
        g.audit["reason"] = "no_trend"
        return g
    g.detected = True
    g.direction = bias
    g.confidence = 0.6
    g.audit = {"bascule_intensite": bascule_intensite,
               "trend_direction": trend_direction}
    return g


def tension(pliure_detectee: bool, tension_score: float,
            pente: float) -> GrammarSignal:
    """TENSION : pliure + tension_score élevé (accumulation de pression).

    Détecté si pliure ET tension_score ≥ 1.0. Direction = signe de la pente.
    """
    g = GrammarSignal(concept="TENSION")
    if not pliure_detectee or tension_score < 1.0:
        g.audit["reason"] = "no_pliure_or_low_tension"
        return g
    g.detected = True
    g.direction = "BULLISH" if pente >= 0 else "BEARISH"
    g.confidence = min(1.0, tension_score / 2.0)
    g.audit = {"tension_score": tension_score, "pente": pente}
    return g


def respiration(zone_type: str, compression_etat: str) -> GrammarSignal:
    """RESPIRATION : zone de respiration (compression → expansion).

    Détecté si zone_type == 'respiration'. Direction NEUTRAL (attente
    d'expansion). Confiance = 0.5.
    """
    g = GrammarSignal(concept="RESPIRATION")
    if zone_type != "respiration":
        g.audit["reason"] = "not_respiration_zone"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.5
    g.audit = {"compression_etat": compression_etat}
    return g


def lock(compression_etat: str, zone_type: str) -> GrammarSignal:
    """LOCK : compression + respiration (verrouillage de range).

    Détecté si compression_etat == 'compression' ET zone_type == 'respiration'.
    Direction NEUTRAL (range verrouillé). Confiance = 0.6.
    """
    g = GrammarSignal(concept="LOCK")
    if compression_etat != "compression" or zone_type != "respiration":
        g.audit["reason"] = "no_lock_condition"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.6
    g.audit = {"compression_etat": compression_etat, "zone_type": zone_type}
    return g


def opposition(antagonismes_count: int, bascule_intensite: float) -> GrammarSignal:
    """OPPOSITION : antagonismes multiples + bascule (conflit de devises).

    Détecté si antagonismes_count ≥ 2 ET bascule_intensite ≥ 15.
    Direction NEUTRAL (conflit → pas de direction claire). Confiance = 0.5.
    """
    g = GrammarSignal(concept="OPPOSITION")
    if antagonismes_count < 2 or bascule_intensite < 15:
        g.audit["reason"] = "no_opposition"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.5
    g.audit = {"antagonismes_count": antagonismes_count,
               "bascule_intensite": bascule_intensite}
    return g


def evaluate_grammar_v9(
    *,
    regime_name: str = "NEUTRAL",
    leader: Optional[str] = None,
    follower: Optional[str] = None,
    bascule_detectee: bool = False,
    bascule_intensite: float = 0.0,
    trend_direction: str = "",
    pliure_detectee: bool = False,
    tension_score: float = 0.0,
    pente: float = 0.0,
    zone_type: str = "",
    compression_etat: str = "",
    antagonismes_count: int = 0,
) -> Dict:
    """Évalue tous les concepts de grammaire V9 et retourne les détectés.

    Returns
    -------
    dict : {concepts: [GrammarSignal.as_dict()], n_detected, best}
    """
    signals = [
        leader_follower(regime_name, leader, follower),
        pullback(regime_name, bascule_detectee, bascule_intensite, trend_direction),
        tension(pliure_detectee, tension_score, pente),
        respiration(zone_type, compression_etat),
        lock(compression_etat, zone_type),
        opposition(antagonismes_count, bascule_intensite),
    ]
    detected = [s for s in signals if s.detected]
    best = max(detected, key=lambda s: s.confidence) if detected else None
    return {
        "concepts": [s.as_dict() for s in signals],
        "n_detected": len(detected),
        "best": best.as_dict() if best else None,
        "audit": {"r10": "compute only, zero order real"},
    }


__all__ = [
    "GrammarSignal",
    "leader_follower",
    "pullback",
    "tension",
    "respiration",
    "lock",
    "opposition",
    "evaluate_grammar_v9",
]
