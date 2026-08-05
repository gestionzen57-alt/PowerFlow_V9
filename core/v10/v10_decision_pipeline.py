"""V10 Decision Pipeline — décision end-to-end signal → filtres → risque (Sprint 13).

Compose le pipeline décisionnel complet en une seule fonction additif (R2) :
  signal_level (orchestrateur) → stratégies publiques (ICT OTE + SMC +
  regime via filter compositor) → bouclier R10 (DD + position + net exposure
  + corrélation) → DÉCISION finale (BUY/SELL/WAIT/NONE) + lot_size.

Ferme le mandat « tout brancher, lecture cohérente, apprentissage » :
chaque étape est auditée R9, chaque gate fail-open R6, aucune décision
réelle (R10 compute only).

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7, R9, R10.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class PipelineDecision:
    pair: str = ""
    timeframe: str = ""
    timestamp: str = ""
    signal_level: str = "NONE"
    filtered_level: str = "NONE"
    risk_ok: bool = False
    action: str = "WAIT"        # BUY / SELL / WAIT / NONE
    lot_size: float = 0.0
    reasons: List[str] = field(default_factory=list)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair, "timeframe": self.timeframe,
            "timestamp": self.timestamp, "signal_level": self.signal_level,
            "filtered_level": self.filtered_level, "risk_ok": self.risk_ok,
            "action": self.action, "lot_size": round(self.lot_size, 4),
            "reasons": self.reasons, "audit": dict(self.audit),
        }


def decide_entry(
    pair: str,
    timeframe: str,
    timestamp: str,
    direction: str,             # long / short
    signal_level: str,          # A1/A2/A3/NONE
    *,
    # Stratégies publiques (objets déjà calculés, R6 optionnels)
    session=None, ote=None, smc=None, regime=None,
    # Risque
    daily_dd_pct: float = 0.0,
    candidate_risk_pct: float = 1.0,
    max_position_pct: float = 2.0,
    max_daily_dd_pct: float = 10.0,
    positions: Optional[List] = None,
    allow_opposed: bool = False,
    # Portfolio manager (corrélation)
    portfolio_can_enter: Optional[bool] = None,
    portfolio_blocked_reason: str = "",
    capital: float = 100_000.0,
) -> PipelineDecision:
    """Produit la décision finale (action + lot_size).

    Pipeline :
      1. Filtre stratégies publiques (compose_filters) sur signal_level.
      2. Si filtered_level == NONE → action NONE.
      3. Bouclier R10 (evaluate_risk_shield).
      4. Si risk_ok et filtered_level ∈ {A1, A2} → action BUY/SELL + lot.

    R6 fail-open : tout objet None ignoré ; exceptions → WAIT (safe).
    """
    dec = PipelineDecision(
        pair=pair, timeframe=timeframe, timestamp=timestamp,
        signal_level=signal_level)
    dec.audit = {"steps": []}

    # 1. Filtres publics
    try:
        from .v10_filter_compositor import compose_filters
        comp = compose_filters(
            signal_level, symbol=pair, timeframe=timeframe, timestamp=timestamp,
            session=session, ote=ote, smc=smc, regime=regime,
        )
        dec.filtered_level = comp.final_level
        dec.audit["steps"].append("filter_compositor")
        dec.audit["filters_trace"] = [t.as_dict() for t in comp.trace]
    except Exception as exc:
        log.warning("compose_filters échoué (R6): %s", exc)
        dec.filtered_level = signal_level
        dec.audit["steps"].append("filter_compositor_error")
        dec.audit["error"] = type(exc).__name__
        return dec  # WAIT

    if dec.filtered_level == "NONE":
        dec.action = "NONE"
        dec.reasons.append("filtered_NONE")
        dec.audit["steps"].append("no_trade")
        return dec

    # 2. Bouclier R10
    try:
        from .v10_risk_shield import evaluate_risk_shield
        from .v10_net_exposure import exposure_gate
        eg = exposure_gate(
            pair, direction, positions or [],
            max_net_by_ccy=5.0, allow_opposed=allow_opposed)
        shield = evaluate_risk_shield(
            pair, direction,
            daily_dd_pct=daily_dd_pct, max_daily_dd_pct=max_daily_dd_pct,
            candidate_risk_pct=candidate_risk_pct,
            max_position_pct=max_position_pct,
            exposure_gate_result=eg,
            portfolio_can_enter=portfolio_can_enter,
            portfolio_blocked_reason=portfolio_blocked_reason,
        )
        dec.risk_ok = shield.can_enter
        dec.audit["steps"].append("risk_shield")
        dec.audit["risk_gates"] = dict(shield.gates)
        dec.audit["net_exposure"] = dict(eg.net_exposure)
        if not shield.can_enter:
            dec.reasons.extend(shield.blocked_reasons)
    except Exception as exc:
        log.warning("risk_shield échoué (R6): %s", exc)
        dec.audit["steps"].append("risk_shield_error")
        dec.audit["error"] = type(exc).__name__
        return dec  # WAIT

    if not dec.risk_ok:
        dec.action = "WAIT"
        dec.audit["steps"].append("risk_blocked")
        return dec

    # 3. Action finale
    if dec.filtered_level in ("A1", "A2") and signal_level in ("A1", "A2"):
        dec.action = "BUY" if direction in ("long", "buy") else "SELL"
        # lot simplifié : fraction de capital (R10) → ~1 lot par 100k * risk_pct
        dec.lot_size = round(
            (capital * candidate_risk_pct / 100.0) / 100_000.0, 4)
        dec.reasons.append(f"filtered={dec.filtered_level}")
        dec.audit["steps"].append("trade")
    else:
        dec.action = "WAIT"
        dec.reasons.append(f"filtered={dec.filtered_level} (pas A1/A2)")
        dec.audit["steps"].append("not_high_conviction")

    return dec


__all__ = ["PipelineDecision", "decide_entry"]
