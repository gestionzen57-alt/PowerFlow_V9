"""V10 Cortex — Moteur d'Interprétation Continue (Phase 3, Cognitive Continuum).

Le point unique où TOUTES les lectures des comportements convergent vers la
décision. Boucle vivante, non figée :
  voir → contextualiser → comprendre → agir → apprendre → mémoriser

Le Cortex agrège :
  - BASE 1 (observation V9) : recall_patterns (mémoire inter-cycles)
  - BASE 2 (interprétation V10) : régime HMM, structure, coalition, antagonisme,
    safe_haven, delta_flow, liquidity_map, Fatman Bible
  - BASE 3 (cohérence) : query_coherence (WR réel d'un contexte)
  - BASE 4 (décision) : decide_entry enrichi
  - BASE 5 (mémoire) : recall + transition

`interpret()` produit une interprétation qualifiée et signifiée (pas une
étiquette froide) + la requête de cohérence (WR réel du contexte).
`decide()` enchaîne interprétation → décision → mémorisation.

R2 additif pur (0 import core/v9/). R6 fail-open. R9 traçable. R10 compute only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class CortexInterpretation:
    pair: str = ""
    timeframe: str = ""
    timestamp: str = ""
    observation_qualification: str = ""
    regime_hmm: str = ""
    coalition: str = ""
    antagonisme: str = ""
    structure_type: str = ""
    safe_haven: str = ""
    memory_recall: List[Dict] = field(default_factory=list)
    coherence: Dict = field(default_factory=dict)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair, "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "observation_qualification": self.observation_qualification,
            "regime_hmm": self.regime_hmm, "coalition": self.coalition,
            "antagonisme": self.antagonisme, "structure_type": self.structure_type,
            "safe_haven": self.safe_haven,
            "memory_recall": self.memory_recall[:5],
            "coherence": dict(self.coherence),
            "audit": dict(self.audit),
        }


def interpret(
    *,
    pair: str,
    timeframe: str,
    timestamp: str,
    observation_qualification: str = "",
    regime_hmm: str = "",
    coalition: str = "",
    antagonisme: str = "",
    structure_type: str = "",
    safe_haven: str = "",
    memory_bridge=None,
    behavior_registry=None,
) -> CortexInterpretation:
    """Interprète un comportement : observation + contexte + mémoire + cohérence.

    R6 fail-open : memory_bridge/behavior_registry None → sections vides.
    R9 : chaque section tracée dans audit.
    """
    interp = CortexInterpretation(
        pair=pair, timeframe=timeframe, timestamp=timestamp,
        observation_qualification=observation_qualification,
        regime_hmm=regime_hmm, coalition=coalition, antagonisme=antagonisme,
        structure_type=structure_type, safe_haven=safe_haven,
    )
    interp.audit["steps"] = []

    # BASE 5 — mémoire inter-cycles (recall)
    if memory_bridge is not None:
        try:
            interp.memory_recall = memory_bridge.recall_patterns(
                pair, timeframe, regime_type=regime_hmm, phase=observation_qualification)
            interp.audit["steps"].append("memory_recall")
        except Exception as exc:
            log.warning("memory_recall échoué (R6): %s", exc)
            interp.audit["steps"].append("memory_recall_error")

    # BASE 3 — cohérence (WR réel du contexte)
    if behavior_registry is not None:
        try:
            interp.coherence = behavior_registry.query_coherence(
                observation_qualification=observation_qualification,
                regime_hmm=regime_hmm, coalition=coalition, antagonisme=antagonisme)
            interp.audit["steps"].append("coherence_query")
        except Exception as exc:
            log.warning("coherence_query échoué (R6): %s", exc)
            interp.audit["steps"].append("coherence_error")

    interp.audit["r10"] = "compute only, zero order real"
    return interp


def decide(
    *,
    pair: str,
    timeframe: str,
    timestamp: str,
    observation_qualification: str = "",
    regime_hmm: str = "",
    coalition: str = "",
    antagonisme: str = "",
    structure_type: str = "",
    safe_haven: str = "",
    direction: str = "long",
    signal_level: str = "A2",
    memory_bridge=None,
    behavior_registry=None,
    decision_pipeline=None,
    **pipeline_kwargs,
) -> Dict:
    """Enchaîne interprétation → décision → mémorisation (boucle vivante).

    Returns dict {interpretation, decision, memorized}.
    R6 fail-open : decision_pipeline None → decision = WAIT (safe).
    """
    interp = interpret(
        pair=pair, timeframe=timeframe, timestamp=timestamp,
        observation_qualification=observation_qualification,
        regime_hmm=regime_hmm, coalition=coalition, antagonisme=antagonisme,
        structure_type=structure_type, safe_haven=safe_haven,
        memory_bridge=memory_bridge, behavior_registry=behavior_registry,
    )

    # Décision via le pipeline enrichi (R6 fail-open)
    decision = {"action": "WAIT", "reason": "no_pipeline"}
    if decision_pipeline is not None:
        try:
            decision = decision_pipeline(
                pair, timeframe, timestamp, direction, signal_level,
                **pipeline_kwargs)
            if hasattr(decision, "as_dict"):
                decision = decision.as_dict()
        except Exception as exc:
            log.warning("decision_pipeline échoué (R6): %s", exc)
            decision = {"action": "WAIT", "reason": "pipeline_error"}

    # Mémorisation (BASE 3) — R6 fail-open
    memorized = False
    if behavior_registry is not None:
        try:
            behavior_registry.record_behavior(
                timestamp=timestamp, pair=pair, timeframe=timeframe,
                observation_qualification=observation_qualification,
                regime_hmm=regime_hmm, coalition=coalition, antagonisme=antagonisme,
                structure_type=structure_type, safe_haven=safe_haven,
                is_win=None, pnl_pips=None,
                source_ref="cortex_decide")
            memorized = True
        except Exception as exc:
            log.warning("mémorisation échouée (R6): %s", exc)

    return {
        "interpretation": interp.as_dict(),
        "decision": decision,
        "memorized": memorized,
        "audit": {"r10": "compute only, zero order real"},
    }


__all__ = ["CortexInterpretation", "interpret", "decide"]
