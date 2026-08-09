"""
v10_slippage_model.py — CYCLE 13 : Slippage Model
C13-OPT3 : Estime le slippage (pips) et ajuste TP/SL.
Doctrine : R2 | R6 fail-open | R10 compute-only
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass
from typing import Any

SLIPPAGE_BASE_PIPS: float = 0.3
SLIPPAGE_SPREAD_COEF: float = 0.5
SLIPPAGE_VOL_COEF: float = 0.2
SLIPPAGE_MAX_PIPS: float = 5.0


@dataclass
class SlippageResult:
    estimated_pips: float = 0.0
    adjusted_tp_pips: float = 0.0
    adjusted_sl_pips: float = 0.0
    spread_pips: float = 0.0
    model: str = "linear"

    def as_dict(self) -> dict[str, Any]:
        return {"estimated_pips": self.estimated_pips, "adjusted_tp_pips": self.adjusted_tp_pips,
                "adjusted_sl_pips": self.adjusted_sl_pips, "spread_pips": self.spread_pips}


def estimate_slippage(spread_pips: float = 1.0, atr_pips: float = 20.0,
                     atr_baseline_pips: float = 20.0, tp_pips: float = 30.0, sl_pips: float = 20.0) -> SlippageResult:
    result = SlippageResult(spread_pips=spread_pips)
    try:
        vol_ratio = atr_pips / atr_baseline_pips if atr_baseline_pips > 0 else 1.0
        slip = min(SLIPPAGE_BASE_PIPS + spread_pips * SLIPPAGE_SPREAD_COEF + vol_ratio * SLIPPAGE_VOL_COEF, SLIPPAGE_MAX_PIPS)
        result.estimated_pips = round(slip, 2)
        result.adjusted_tp_pips = round(max(1.0, tp_pips - slip), 2)
        result.adjusted_sl_pips = round(sl_pips + slip, 2)
    except Exception as e:
        warnings.warn(f"[C13] SlippageModel error (fail-open): {e}")
        result.estimated_pips = SLIPPAGE_BASE_PIPS
        result.adjusted_tp_pips = tp_pips
        result.adjusted_sl_pips = sl_pips
    return result
