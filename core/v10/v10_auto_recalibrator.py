"""V10 Auto-Recalibrator — boucle R8 (déclenchée par l'error learner).

Ferme la boucle d'apprentissage : quand l'ErrorLearner détecte un drift ou
qu'une re-calibration est recommandée, ce module relance la recalibration
bayésienne R8 (compute_recalibration_by_pair_tf) et produit une décision
DÉPLOYER / REVERT / HOLD.

Boucle R8 (doctrine) :
  Trade clôturé → métrique → si KPI < seuil → re-calibration auto
  → re-test historique → si mieux → déployer → si moins bien → revert.

R6 fail-open : erreur / données insuffisantes → HOLD, jamais de crash.
R9 audit : avant/après WR, seuils, décision, raison.
R10 : zéro ordre réel — la recalibration ne mute JAMAIS les constantes
modules directement (elle écrit un JSON de seuils consommé à runtime via
`load_thresholds_pair_tf_json`).

Doctrine : R1-AGIR (déclenche la recalibration), R2 additif pur,
R4/R8 online learning, R6 fail-open, R7, R9, R10.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Seuil : on ne recalibre que si au moins N pertes par setup
MIN_SETUP_LOSSES = 10


@dataclass
class RecalibDecision:
    timestamp: str = ""
    triggered: bool = False
    reason: str = ""
    setups: List[str] = field(default_factory=list)
    decision: str = "HOLD"        # DEPLOY / REVERT / HOLD
    before_wr: Optional[float] = None
    after_wr: Optional[float] = None
    threshold_path: str = ""
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "triggered": self.triggered,
            "reason": self.reason,
            "setups": self.setups,
            "decision": self.decision,
            "before_wr": self.before_wr,
            "after_wr": self.after_wr,
            "threshold_path": self.threshold_path,
            "audit": dict(self.audit),
        }


def _wr_of_setup(state, setup: str) -> float:
    d = state.per_setup.get(setup, {})
    return float(d.get("wr", 0.0))


def should_recalibrate(state, *, min_losses: int = MIN_SETUP_LOSSES) -> tuple:
    """Décide si une re-calibration est nécessaire d'après l'error learner.

    Returns
    -------
    (triggered, reason, setups)
    """
    if state.drift_detected and state.drift_count > 0:
        return (True, "drift_detected", list(state.recalibrate_setups))
    if state.recalibrate_recommended:
        # Ne trigger que si les setups concernés ont assez de données
        ok_setups = [s for s in state.recalibrate_setups
                     if state.per_setup.get(s, {}).get("n", 0) >= min_losses]
        if ok_setups:
            return (True, "recalibrate_recommended", ok_setups)
    return (False, "no_trigger", [])


def run_auto_recalibration(
    state,
    *,
    db_path: str = "data/v9_forces.db",
    output_path: str = "",
    min_losses: int = MIN_SETUP_LOSSES,
    threshold_current_path: str = "",
) -> RecalibDecision:
    """Exécute la boucle R8 si déclenchée.

    Steps :
      1. should_recalibrate(state) → si non, HOLD.
      2. Relance compute_recalibration_by_pair_tf sur la DB.
      3. Compare WR avant (état learner) / après (recalibré).
      4. Décision : DEPLOY si after_wr >= before_wr, sinon REVERT.
    """
    dec = RecalibDecision(timestamp=datetime.now(timezone.utc).isoformat())

    triggered, reason, setups = should_recalibrate(state, min_losses=min_losses)
    dec.triggered = triggered
    dec.reason = reason
    dec.setups = setups
    if not triggered:
        dec.decision = "HOLD"
        dec.audit = {"reason": "no_trigger", "setups": []}
        return dec

    try:
        from core.v10.v10_bayesian_recalibrator import (
            compute_recalibration_by_pair_tf,
            write_thresholds_pair_tf_json,
        )

        report = compute_recalibration_by_pair_tf(db_path=db_path)
        after_wr = report.get("avg_wr_v10", 0.0) if isinstance(report, dict) \
            else getattr(report, "avg_wr_v10", 0.0)

        # WR avant = moyenne des setups concernés (error learner)
        before_wrs = [_wr_of_setup(state, s) for s in setups]
        before_wr = sum(before_wrs) / len(before_wrs) if before_wrs else 0.0

        dec.before_wr = round(before_wr, 4)
        dec.after_wr = round(after_wr, 4)

        # Persist thresholds
        if not output_path:
            date = datetime.now(timezone.utc).strftime("%Y%m%d")
            output_path = f"config/v10_auto_recalib_{date}.json"
        write_thresholds_pair_tf_json(report, output_path)
        dec.threshold_path = output_path

        dec.decision = "DEPLOY" if after_wr >= before_wr else "REVERT"
        dec.audit = {
            "reason": reason,
            "setups": setups,
            "before_wr": dec.before_wr,
            "after_wr": dec.after_wr,
            "threshold_path": output_path,
        }
    except Exception as exc:
        log.warning("Auto-recalibration échouée (R6 fail-open HOLD): %s", exc)
        dec.decision = "HOLD"
        dec.audit = {"reason": f"error:{type(exc).__name__}", "detail": str(exc)}
    return dec


__all__ = [
    "RecalibDecision",
    "should_recalibrate",
    "run_auto_recalibration",
]
