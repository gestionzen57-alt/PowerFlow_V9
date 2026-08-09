"""
v10_dynamic_sizing.py — CYCLE 12 : Dynamic Position Sizing

C12-OPT2 : Kelly Criterion (quart-Kelly) + ATR-based sizing + hard-cap

Doctrine : R2 additif pur | R6 fail-open | R10 compute-only
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Any


# ── Constantes ──────────────────────────────────────────────────────────────
KELLY_FRACTION: float = 0.25    # quart-Kelly
LOT_MIN: float = 0.01
LOT_MAX: float = 10.0
DEFAULT_LOT: float = 0.10


@dataclass
class SizingResult:
    lot_size: float = DEFAULT_LOT
    kelly_full: float = 0.0
    kelly_quarter: float = 0.0
    atr_lots: float = 0.0
    method: str = "default"
    capped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "lot_size": self.lot_size,
            "kelly_full": self.kelly_full,
            "kelly_quarter": self.kelly_quarter,
            "atr_lots": self.atr_lots,
            "method": self.method,
            "capped": self.capped,
        }


def compute_lot_size(
    account_balance: float,
    risk_pct: float,
    stop_loss_pips: float,
    pip_value: float = 10.0,
    win_rate: float = 0.50,
    avg_win: float = 1.5,
    avg_loss: float = 1.0,
    atr_pips: float | None = None,
) -> SizingResult:
    """
    Calcule la taille de position optimale.

    Args:
        account_balance : capital en compte
        risk_pct        : risk par trade (0.01 = 1%)
        stop_loss_pips  : distance SL en pips
        pip_value       : valeur d'un pip par lot (défaut 10€)
        win_rate        : WR estimé (0-1)
        avg_win / avg_loss : ratio moyen win/loss
        atr_pips        : ATR en pips (optionnel, active ATR-sizing)
    """
    result = SizingResult()
    try:
        risk_amount = account_balance * risk_pct

        # Méthode 1 : risk fixe sur SL
        if stop_loss_pips > 0 and pip_value > 0:
            risk_lot = risk_amount / (stop_loss_pips * pip_value)
        else:
            risk_lot = DEFAULT_LOT

        # Méthode 2 : Kelly quart
        if win_rate > 0 and avg_loss > 0:
            b = avg_win / avg_loss
            kelly_full = (b * win_rate - (1 - win_rate)) / b
            kelly_q = max(0.0, kelly_full * KELLY_FRACTION)
            result.kelly_full = round(kelly_full, 4)
            result.kelly_quarter = round(kelly_q, 4)
            kelly_lot = account_balance * kelly_q / (stop_loss_pips * pip_value) if stop_loss_pips > 0 else risk_lot
        else:
            kelly_lot = risk_lot

        # Méthode 3 : ATR-based sizing
        if atr_pips and atr_pips > 0:
            atr_lot = risk_amount / (atr_pips * 1.5 * pip_value)
            result.atr_lots = round(atr_lot, 4)
            final_lot = min(risk_lot, kelly_lot, atr_lot)
            result.method = "ATR+Kelly+Risk"
        else:
            final_lot = min(risk_lot, kelly_lot)
            result.method = "Kelly+Risk"

        # Clamp
        original = final_lot
        final_lot = max(LOT_MIN, min(LOT_MAX, round(final_lot, 2)))
        result.capped = abs(final_lot - original) > 0.001
        result.lot_size = final_lot

    except Exception as e:  # R6 fail-open
        warnings.warn(f"[C12] DynamicSizing error (fail-open): {e}")
        result.lot_size = DEFAULT_LOT
        result.method = f"ERROR_FAIL_OPEN: {e}"

    return result
