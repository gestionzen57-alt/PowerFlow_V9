"""V10 Grammar V9 Final — portage additif des derniers concepts V9 (Phase R).

Complète le portage des concepts de grammaire V9 dans V10 (additif pur R2,
0 import core/v9/). Concepts portés :
  - CONTEXTE : marché ouvert + session de marché (contexte global).
  - CROISEMENT : bascule détectée + devise dominante (croisement de forces).
  - CROISEMENT_CONFIRMATION : croisement + vitesse (confirmation).
  - GRAVITY_RESPRING : état LEAKING/ACCUMULATING + état précédent (ressort).
  - POWER_ANGLE_BREAK : RUPTURE + tension (cassure de puissance).
  - RAW_NODE_BIRTH : naissance de nœud depuis NEUTRAL.
  - SIGNAL_OPEN : fenêtre ouverte + confiance ≥ 70 (signal prêt).

Chaque concept = fonction pure fail-open R6, retourne un GrammarSignal.

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7, R9 audit, R10.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict

log = logging.getLogger(__name__)


@dataclass
class GrammarSignal:
    concept: str = ""
    detected: bool = False
    direction: str = "NEUTRAL"
    confidence: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "concept": self.concept,
            "detected": self.detected,
            "direction": self.direction,
            "confidence": round(self.confidence, 3),
            "audit": dict(self.audit),
        }


def contexte(marche_ouvert: bool, session_marche: bool) -> GrammarSignal:
    """CONTEXTE : marché ouvert + session de marché."""
    g = GrammarSignal(concept="CONTEXTE")
    if not marche_ouvert or not session_marche:
        g.audit["reason"] = f"marche={marche_ouvert}, session={session_marche}"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.5
    g.audit = {"marche_ouvert": marche_ouvert, "session_marche": session_marche}
    return g


def croisement(bascule_detectee: bool, bascule_devise_dominante: str) -> GrammarSignal:
    """CROISEMENT : bascule détectée + devise dominante."""
    g = GrammarSignal(concept="CROISEMENT")
    if not bascule_detectee or not bascule_devise_dominante:
        g.audit["reason"] = f"bascule={bascule_detectee}, devise={bascule_devise_dominante}"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.6
    g.audit = {"bascule_devise_dominante": bascule_devise_dominante}
    return g


def croisement_confirmation(croisement_detecte: bool, vitesse: float) -> GrammarSignal:
    """CROISEMENT_CONFIRMATION : croisement + vitesse > 0.05."""
    g = GrammarSignal(concept="CROISEMENT_CONFIRMATION")
    if not croisement_detecte or vitesse <= 0.05:
        g.audit["reason"] = f"croisement={croisement_detecte}, vitesse={vitesse}"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.7
    g.audit = {"vitesse": vitesse}
    return g


def gravity_respring(state: str, prev_state: str) -> GrammarSignal:
    """GRAVITY_RESPRING : état LEAKING/ACCUMULATING + état précédent."""
    g = GrammarSignal(concept="GRAVITY_RESPRING")
    if state not in ("LEAKING", "ACCUMULATING") or not prev_state:
        g.audit["reason"] = f"state={state}, prev={prev_state}"
        return g
    g.detected = True
    g.direction = "BULLISH" if state == "ACCUMULATING" else "NEUTRAL"
    g.confidence = 0.6
    g.audit = {"state": state, "prev_state": prev_state}
    return g


def power_angle_break(state: str, tension_score: float) -> GrammarSignal:
    """POWER_ANGLE_BREAK : RUPTURE + tension ≥ 1.0."""
    g = GrammarSignal(concept="POWER_ANGLE_BREAK")
    if state != "RUPTURE" or tension_score < 1.0:
        g.audit["reason"] = f"state={state}, tension={tension_score}"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.7
    g.audit = {"tension_score": tension_score}
    return g


def raw_node_birth(prev_state: str, state: str) -> GrammarSignal:
    """RAW_NODE_BIRTH : naissance de nœud depuis NEUTRAL."""
    g = GrammarSignal(concept="RAW_NODE_BIRTH")
    if prev_state != "NEUTRAL" or state not in ("EARLY_EXTREME", "ACCUMULATING", "LEAKING"):
        g.audit["reason"] = f"prev={prev_state}, state={state}"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.5
    g.audit = {"prev_state": prev_state, "state": state}
    return g


def signal_open(window_statut: str, confiance_qualification: float) -> GrammarSignal:
    """SIGNAL_OPEN : fenêtre ouverte + confiance ≥ 70."""
    g = GrammarSignal(concept="SIGNAL_OPEN")
    if window_statut != "ouverte" or confiance_qualification < 70:
        g.audit["reason"] = f"window={window_statut}, conf={confiance_qualification}"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.6
    g.audit = {"confiance_qualification": confiance_qualification}
    return g


def evaluate_grammar_v9_final(
    *,
    marche_ouvert: bool = True,
    session_marche: bool = True,
    bascule_detectee: bool = False,
    bascule_devise_dominante: str = "",
    croisement_detecte: bool = False,
    vitesse: float = 0.0,
    state: str = "",
    prev_state: str = "",
    tension_score: float = 0.0,
    window_statut: str = "",
    confiance_qualification: float = 0.0,
) -> Dict:
    """Évalue tous les concepts V9 finaux et retourne les détectés."""
    signals = [
        contexte(marche_ouvert, session_marche),
        croisement(bascule_detectee, bascule_devise_dominante),
        croisement_confirmation(croisement_detecte, vitesse),
        gravity_respring(state, prev_state),
        power_angle_break(state, tension_score),
        raw_node_birth(prev_state, state),
        signal_open(window_statut, confiance_qualification),
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
    "contexte",
    "croisement",
    "croisement_confirmation",
    "gravity_respring",
    "power_angle_break",
    "raw_node_birth",
    "signal_open",
    "evaluate_grammar_v9_final",
]
