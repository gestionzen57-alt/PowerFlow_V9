"""
v10_adaptive_risk_engine.py — CYCLE 12 : Adaptive Risk Engine

C12-OPT1 : Ajuste dynamiquement le risk-per-trade (0.5%→4%) selon
            le régime de marché (trending / ranging / volatile)

Doctrine : R2 additif pur | R6 fail-open | R9 audit | R10 compute-only
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any


# ── Seuils C12-OPT1 ────────────────────────────────────────────────────────
RISK_TRENDING: float = 0.02      # 2% en tendance claire
RISK_RANGING: float = 0.01       # 1% en range
RISK_VOLATILE: float = 0.005     # 0.5% en choc volatil
RISK_MAX: float = 0.04           # plafond absolu
RISK_MIN: float = 0.005          # plancher absolu

REGIME_MAP: dict[str, float] = {
    "trending": RISK_TRENDING,
    "ranging": RISK_RANGING,
    "volatile": RISK_VOLATILE,
    "unknown": RISK_RANGING,
}


@dataclass
class AdaptiveRiskResult:
    risk_pct: float = RISK_RANGING
    regime: str = "unknown"
    adjustment_reason: str = ""
    capped: bool = False
    audit: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "risk_pct": self.risk_pct,
            "regime": self.regime,
            "adjustment_reason": self.adjustment_reason,
            "capped": self.capped,
        }


def compute_adaptive_risk(
    regime: str = "unknown",
    recent_wr: float = 0.50,
    current_dd: float = 0.0,
    *,
    override_risk: float | None = None,
) -> AdaptiveRiskResult:
    """
    Calcule le risk-per-trade adapté au régime.

    Args:
        regime        : 'trending' | 'ranging' | 'volatile' | 'unknown'
        recent_wr     : WR des 20 derniers trades (0-1)
        current_dd    : drawdown courant (0-1, ex: 0.05 = 5%)
        override_risk : si fourni, by-passe le calcul (clampé sur [MIN, MAX])
    """
    result = AdaptiveRiskResult(regime=regime)
    try:
        base = REGIME_MAP.get(regime.lower(), RISK_RANGING)

        if override_risk is not None:
            base = float(override_risk)
            result.adjustment_reason = f"OVERRIDE={base:.3f}"
        else:
            # Modulation WR : +20% si WR > 55%, -20% si WR < 45%
            if recent_wr > 0.55:
                base *= 1.20
                result.adjustment_reason = f"WR_BOOST wr={recent_wr:.1%}"
            elif recent_wr < 0.45:
                base *= 0.80
                result.adjustment_reason = f"WR_CUT wr={recent_wr:.1%}"
            else:
                result.adjustment_reason = f"NEUTRAL wr={recent_wr:.1%}"

            # Modulation DD : réduction linéaire si DD > 3%
            if current_dd > 0.03:
                dd_factor = max(0.5, 1.0 - (current_dd - 0.03) * 10)
                base *= dd_factor
                result.adjustment_reason += f" DD_REDUCE dd={current_dd:.1%}"

        # Clamp [MIN, MAX]
        original = base
        base = max(RISK_MIN, min(RISK_MAX, base))
        if abs(base - original) > 1e-6:
            result.capped = True

        result.risk_pct = round(base, 4)
        result.audit = {"base_before_clamp": original, "final_risk": base}

    except Exception as e:  # R6 fail-open
        warnings.warn(f"[C12] AdaptiveRiskEngine error (fail-open): {e}")
        result.risk_pct = RISK_RANGING
        result.adjustment_reason = f"ERROR_FAIL_OPEN: {e}"

    return result
