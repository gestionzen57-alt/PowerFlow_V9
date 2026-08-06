"""V10 Learning Continuum — apprentissage continu par comportement (Phase 5, Cognitive Continuum).

Ferme la boucle vivante "voir → apprendre" : chaque interprétation du Cortex
est confrontée au RÉSULTAT réel (win/loss), et le registre d'interprétation
(BASE 3) est mis à jour pour que la compréhension s'affine à chaque cycle.

`learn_from_outcome()` : enregistre le résultat d'une interprétation dans le
registre (v10_behaviors) → la requête de cohérence (WR réel par contexte)
devient de plus en plus précise à chaque cycle.

`drift_by_behavior()` : détecte si un comportement spécifique (qualification ×
régime) a dérivé (WR glissant < seuil) — le drift par comportement, pas juste
par setup global. C'est la lecture fine qui manquait.

R2 additif pur (0 import core/v9/). R6 fail-open. R9 traçable. R10 compute only.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Seuil de drift par comportement (WR glissant sous lequel on alerte)
DRIFT_WR_THRESHOLD = 0.40
MIN_N_FOR_DRIFT = 10


def learn_from_outcome(
    *,
    behavior_id: int,
    is_win: bool,
    pnl_pips: float = 0.0,
    behavior_registry=None,
) -> Dict:
    """Enregistre le résultat d'une interprétation dans le registre.

    R6 fail-open : behavior_registry None → {learned: False}.
    R9 : traçable.
    """
    if behavior_registry is None:
        return {"learned": False, "reason": "no_registry"}
    try:
        # Le registre actuel n'a pas d'UPDATE par id — on ré-enregistre
        # via une méthode dédiée si dispo, sinon on loggue.
        if hasattr(behavior_registry, "resolve_outcome"):
            behavior_registry.resolve_outcome(
                behavior_id=behavior_id, is_win=1 if is_win else 0,
                pnl_pips=pnl_pips)
            return {"learned": True, "behavior_id": behavior_id}
        return {"learned": False, "reason": "no_resolve_method"}
    except Exception as exc:
        log.warning("learn_from_outcome échoué (R6): %s", exc)
        return {"learned": False, "reason": "error"}


def drift_by_behavior(
    *,
    observation_qualification: str,
    regime_hmm: str = "",
    behavior_registry=None,
    db_path=None,
    wr_threshold: float = DRIFT_WR_THRESHOLD,
    min_n: int = MIN_N_FOR_DRIFT,
) -> Dict:
    """Détecte le drift d'un comportement spécifique (WR glissant < seuil).

    Returns dict {behavior, wr, n, drifted, reason}.
    R6 fail-open : registry None → {drifted: False}.
    """
    if behavior_registry is None:
        return {"drifted": False, "reason": "no_registry"}
    # R6 : db_path par défaut → la DB standard du registre
    if db_path is None:
        from core.v10.v10_behavior_registry import DEFAULT_DB
        db_path = DEFAULT_DB
    try:
        coh = behavior_registry.query_coherence(
            observation_qualification=observation_qualification,
            regime_hmm=regime_hmm, min_n=min_n, db_path=db_path)
        n = coh.get("n", 0)
        wr = coh.get("wr", 0.0)
        if n < min_n:
            return {"behavior": observation_qualification, "wr": wr, "n": n,
                    "drifted": False, "reason": f"insufficient_n_{n}"}
        drifted = wr < wr_threshold
        return {"behavior": observation_qualification, "wr": wr, "n": n,
                "drifted": drifted,
                "reason": "drift" if drifted else "healthy"}
    except Exception as exc:
        log.warning("drift_by_behavior échoué (R6): %s", exc)
        return {"drifted": False, "reason": "error"}


__all__ = ["learn_from_outcome", "drift_by_behavior",
           "DRIFT_WR_THRESHOLD", "MIN_N_FOR_DRIFT"]
