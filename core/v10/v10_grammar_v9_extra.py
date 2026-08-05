"""V10 Grammar V9 Extra — portage additif des concepts V9 restants (Phase R).

Complète le portage des concepts de grammaire V9 dans V10 (additif pur R2,
0 import core/v9/). Concepts portés :
  - ADAPTIVE_VOL_GATE : gate de volatilité (seuils adaptatifs si vol élevée).
  - ELASTIC_BREATH : absorption de pullbacks en accumulation (respiration).
  - EXHAUSTION : z-score extrême + état EARLY_EXTREME/RUPTURE (épuisement).
  - VELOCITY_CLIMAX_GUARD : vélocité de forces élevée = emballement (garde).
  - NODE_BIRTH : naissance de nœud (état EARLY_EXTREME/ACCUMULATING/LEAKING).

Chaque concept = fonction pure fail-open R6, retourne un GrammarSignal
consommable par le pipeline de décision V10.

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7, R9 audit, R10.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

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


def adaptive_vol_gate(vol_regime: str, baseline_ok: bool = True) -> GrammarSignal:
    """ADAPTIVE_VOL_GATE : gate de volatilité.

    Détecté si vol_regime ∈ {HIGH, EXTREME} (seuils adaptatifs requis).
    Direction NEUTRAL (gate, pas de direction). Confiance = 0.6.
    """
    g = GrammarSignal(concept="ADAPTIVE_VOL_GATE")
    if vol_regime not in ("HIGH", "EXTREME"):
        g.audit["reason"] = f"vol_regime={vol_regime} (pas d'adaptation requise)"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.6
    g.audit = {"vol_regime": vol_regime, "baseline_ok": baseline_ok}
    return g


def elastic_breath(state: str, absorbed_pullbacks: int) -> GrammarSignal:
    """ELASTIC_BREATH : absorption de pullbacks en accumulation.

    Détecté si state == 'ACCUMULATING' ET absorbed_pullbacks ≥ 1.
    Direction BULLISH (accumulation → expansion haussière). Confiance = 0.6.
    """
    g = GrammarSignal(concept="ELASTIC_BREATH")
    if state != "ACCUMULATING" or absorbed_pullbacks < 1:
        g.audit["reason"] = f"state={state}, pullbacks={absorbed_pullbacks}"
        return g
    g.detected = True
    g.direction = "BULLISH"
    g.confidence = 0.6
    g.audit = {"state": state, "absorbed_pullbacks": absorbed_pullbacks}
    return g


def exhaustion(z_current: float, state: str) -> GrammarSignal:
    """EXHAUSTION : z-score extrême + état d'épuisement.

    Détecté si z_current ≥ 2.0 ET state ∈ {EARLY_EXTREME, RUPTURE}.
    Direction = opposée du mouvement (épuisement → retournement). Confiance = 0.7.
    """
    g = GrammarSignal(concept="EXHAUSTION")
    if z_current < 2.0 or state not in ("EARLY_EXTREME", "RUPTURE"):
        g.audit["reason"] = f"z={z_current}, state={state}"
        return g
    g.detected = True
    # Épuisement → retournement probable (direction opposée au z extrême)
    g.direction = "BEARISH" if z_current > 0 else "BULLISH"
    g.confidence = 0.7
    g.audit = {"z_current": z_current, "state": state}
    return g


def velocity_climax_guard(velocite_moyenne: float,
                          session_marche: bool = True) -> GrammarSignal:
    """VELOCITY_CLIMAX_GUARD : vélocité élevée = emballement (garde).

    Détecté si velocite_moyenne ≥ 0.08 ET session_marche (pas weekend).
    Direction NEUTRAL (garde, pas de direction). Confiance = 0.7.
    """
    g = GrammarSignal(concept="VELOCITY_CLIMAX_GUARD")
    if velocite_moyenne < 0.08 or not session_marche:
        g.audit["reason"] = f"velocite={velocite_moyenne}, session={session_marche}"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.7
    g.audit = {"velocite_moyenne": velocite_moyenne, "session_marche": session_marche}
    return g


def node_birth(state: str) -> GrammarSignal:
    """NODE_BIRTH : naissance de nœud.

    Détecté si state ∈ {EARLY_EXTREME, ACCUMULATING, LEAKING}.
    Direction NEUTRAL (naissance de nœud, pas de direction claire). Confiance = 0.5.
    """
    g = GrammarSignal(concept="NODE_BIRTH")
    if state not in ("EARLY_EXTREME", "ACCUMULATING", "LEAKING"):
        g.audit["reason"] = f"state={state}"
        return g
    g.detected = True
    g.direction = "NEUTRAL"
    g.confidence = 0.5
    g.audit = {"state": state}
    return g


def evaluate_grammar_v9_extra(
    *,
    vol_regime: str = "NORMAL",
    state: str = "",
    absorbed_pullbacks: int = 0,
    z_current: float = 0.0,
    velocite_moyenne: float = 0.0,
    session_marche: bool = True,
) -> Dict:
    """Évalue tous les concepts V9 extra et retourne les détectés.

    Returns
    -------
    dict : {concepts: [GrammarSignal.as_dict()], n_detected, best}
    """
    signals = [
        adaptive_vol_gate(vol_regime),
        elastic_breath(state, absorbed_pullbacks),
        exhaustion(z_current, state),
        velocity_climax_guard(velocite_moyenne, session_marche),
        node_birth(state),
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
    "adaptive_vol_gate",
    "elastic_breath",
    "exhaustion",
    "velocity_climax_guard",
    "node_birth",
    "evaluate_grammar_v9_extra",
]
