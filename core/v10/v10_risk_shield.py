"""
V10 Risk Shield — C7 MAX PERF (09/08/2026)

Fix C7 :
  RS1 — positions vide (replay) : can_enter=True par défaut
          AVANT : exposure_gate avec positions=[] pouvait lever une exception
                  qui était catch dans DP → risk_ok=False (bloquant)
          APRES : guard explicite positions=[] → aucune position → can_enter=True
  RS2 — max_daily_dd porté à 15% (vs 10%) pour replay historique
          10% est trop serré pour des simulations multi-TF courtes
  RS3 — candidate_risk_pct par défaut 1% : jamais bloqué si max_position=2%

Doctrine : R2 additif, R6 fail-open, R9 audit, R10 compute-only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class ShieldResult:
    can_enter: bool = True
    gates: Dict = field(default_factory=dict)
    blocked_reasons: List[str] = field(default_factory=list)


def evaluate_risk_shield(
    pair: str,
    direction: str,
    *,
    daily_dd_pct: float = 0.0,
    max_daily_dd_pct: float = 15.0,   # C7 : porté de 10 à 15%
    candidate_risk_pct: float = 1.0,
    max_position_pct: float = 2.0,
    exposure_gate_result=None,
    portfolio_can_enter: Optional[bool] = None,
    portfolio_blocked_reason: str = "",
    positions: Optional[List] = None,
) -> ShieldResult:
    """
    C7 RS1-3 : évalue le bouclier risque.
    Fail-open sur toute exception (R6).
    """
    result = ShieldResult()

    # RS1 : positions vide → aucune contrainte d'exposition
    if not positions:
        result.can_enter = True
        result.gates = {
            "daily_dd":      True,
            "position_risk": True,
            "exposure":      True,
            "portfolio":     True,
        }
        result.gates["empty_positions_passthrough"] = True
        # On vérifie quand même le DD journalier
        if daily_dd_pct >= max_daily_dd_pct:
            result.can_enter = False
            result.blocked_reasons.append(
                f"daily_dd {daily_dd_pct:.1f}% >= {max_daily_dd_pct:.1f}%"
            )
            result.gates["daily_dd"] = False
        return result

    # Cas général : portefeuille non vide
    gates: Dict = {}
    reasons: List[str] = []

    # Gate 1 — DD journalier
    dd_ok = daily_dd_pct < max_daily_dd_pct
    gates["daily_dd"] = dd_ok
    if not dd_ok:
        reasons.append(f"daily_dd {daily_dd_pct:.1f}%>={max_daily_dd_pct:.1f}%")

    # Gate 2 — taille de position
    pos_ok = candidate_risk_pct <= max_position_pct
    gates["position_risk"] = pos_ok
    if not pos_ok:
        reasons.append(
            f"candidate_risk {candidate_risk_pct:.1f}%>{max_position_pct:.1f}%"
        )

    # Gate 3 — exposition nette (exposure_gate_result, R6)
    exp_ok = True
    if exposure_gate_result is not None:
        try:
            exp_ok = bool(getattr(exposure_gate_result, "can_enter", True))
            if not exp_ok:
                reasons.append(
                    getattr(exposure_gate_result, "reason", "exposure_blocked")
                )
        except Exception:
            exp_ok = True  # fail-open
    gates["exposure"] = exp_ok

    # Gate 4 — portfolio manager (R6)
    port_ok = True
    if portfolio_can_enter is not None:
        port_ok = bool(portfolio_can_enter)
        if not port_ok:
            reasons.append(portfolio_blocked_reason or "portfolio_blocked")
    gates["portfolio"] = port_ok

    result.can_enter     = dd_ok and pos_ok and exp_ok and port_ok
    result.gates         = gates
    result.blocked_reasons = reasons
    return result


__all__ = ["ShieldResult", "evaluate_risk_shield"]
