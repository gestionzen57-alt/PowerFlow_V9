"""V10 Risk Shield — bouclier R10 unifié (portfolio + net exposure + DD) (Sprint 10).

Consolide le garde-fou R10 en une seule décision d'entrée, additif R2
(ne modifie ni v10_portfolio_manager ni v10_net_exposure — les compose).

Gates R10 combinés :
  1. DD quotidien → halt (kill switch).
  2. Position max 2% capital par trade.
  3. Pas de double directement opposée (v10_net_exposure).
  4. Pas de net exposure par devise > max (v10_net_exposure).
  5. Corrélation : pas >3 positions corrélées >0.7 (portfolio_manager).

R6 fail-open : chaque sous-gate peut être None → ignoré sans casser.
R9 audit : liste complète des gates évalués + résultat.
R10 : zéro ordre réel — décision only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class RiskShieldDecision:
    pair: str = ""
    direction: str = ""
    can_enter: bool = True
    blocked_reasons: List[str] = field(default_factory=list)
    gates: Dict[str, bool] = field(default_factory=dict)  # name → passed
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair, "direction": self.direction,
            "can_enter": self.can_enter,
            "blocked_reasons": self.blocked_reasons,
            "gates": dict(self.gates),
            "audit": dict(self.audit),
        }


def evaluate_risk_shield(
    pair: str,
    direction: str,
    *,
    daily_dd_pct: float = 0.0,
    max_daily_dd_pct: float = 10.0,          # R10 kill switch
    max_position_pct: float = 2.0,            # R10 position max
    candidate_risk_pct: float = 0.0,
    positions: Optional[List] = None,
    exposure_gate_result: Optional[object] = None,  # v10_net_exposure.ExposureGate
    portfolio_can_enter: Optional[bool] = None,     # portfolio_manager décision
    portfolio_blocked_reason: str = "",
) -> RiskShieldDecision:
    """Évalue tous les gates R10 et retourne une décision unique.

    Parameters
    ----------
    daily_dd_pct : drawdown quotidien % (déclenche kill switch si ≥ max).
    candidate_risk_pct : risque proposé % capital (doit être ≤ max_position_pct).
    positions : positions ouvertes (optionnel, pour exposure_gate).
    exposure_gate_result : résultat de v10_net_exposure.exposure_gate (ou None).
    portfolio_can_enter : bool du portfolio manager (ou None).
    portfolio_blocked_reason : raison du blocage portfolio.

    R6 : chaque gate None est ignoré → ne bloque pas à tort.
    """
    dec = RiskShieldDecision(pair=pair, direction=direction)
    dec.audit = {"gates_evaluated": []}

    # Gate 1 : DD quotidien (kill switch R10)
    if daily_dd_pct >= max_daily_dd_pct:
        dec.gates["daily_dd"] = False
        dec.can_enter = False
        dec.blocked_reasons.append(
            f"DAILY_DD_HALT ({daily_dd_pct:.2f}% >= {max_daily_dd_pct}%)")
        dec.audit["gates_evaluated"].append("daily_dd")
        return dec
    dec.gates["daily_dd"] = True
    dec.audit["gates_evaluated"].append("daily_dd")

    # Gate 2 : position max % capital
    if candidate_risk_pct > max_position_pct:
        dec.gates["position_size"] = False
        dec.can_enter = False
        dec.blocked_reasons.append(
            f"POSITION_TOO_BIG ({candidate_risk_pct:.2f}% > {max_position_pct}%)")
        dec.audit["gates_evaluated"].append("position_size")
        return dec
    dec.gates["position_size"] = True
    dec.audit["gates_evaluated"].append("position_size")

    # Gate 3 : double opposée + net exposure (v10_net_exposure)
    if exposure_gate_result is not None:
        ok = getattr(exposure_gate_result, "can_enter", True)
        reason = getattr(exposure_gate_result, "blocked_reason", "")
        dec.gates["net_exposure"] = bool(ok)
        dec.audit["gates_evaluated"].append("net_exposure")
        if not ok:
            dec.can_enter = False
            dec.blocked_reasons.append(reason or "NET_EXPOSURE_BLOCKED")

    # Gate 4 : portfolio manager (corrélation + sizing)
    if portfolio_can_enter is not None:
        dec.gates["portfolio"] = bool(portfolio_can_enter)
        dec.audit["gates_evaluated"].append("portfolio")
        if not portfolio_can_enter:
            dec.can_enter = False
            dec.blocked_reasons.append(portfolio_blocked_reason or "PORTFOLIO_BLOCKED")

    dec.audit["n_gates"] = len(dec.audit["gates_evaluated"])
    return dec


__all__ = [
    "RiskShieldDecision",
    "evaluate_risk_shield",
]
