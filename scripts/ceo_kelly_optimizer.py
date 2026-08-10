"""CEO-OPT1 : Kelly fractionnel adaptatif — ATR-vol + WR rolling.

Formule : f* = (WR - (1-WR)/RR) * kelly_fraction * atr_scale
R6 fail-open : retourne fraction minimale si données manquantes.
R10 : compute only, 0 ordre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# Constantes CEO
KELLY_FRACTION = 0.25          # Demi-Kelly — règle institutionnelle
MIN_KELLY = 0.005              # Floor : 0.5% du capital
MAX_KELLY = 0.04               # Cap : 4% max par trade
ATR_NEUTRAL_PIPS = 15.0        # ATR de référence M15 EURUSD
WR_WINDOW_DEFAULT = 20         # Fenêtre rolling WR


@dataclass
class KellyResult:
    fraction: float             # Fraction Kelly [0.005, 0.04]
    wr_used: float              # WR rolling utilisé
    rr_used: float              # R:R utilisé
    atr_scale: float            # Facteur ATR
    kelly_raw: float            # Kelly pur avant clamp
    method: str                 # 'adaptive' | 'floor' | 'fallback'
    rationale: str = ""

    def as_dict(self) -> dict:
        return {
            "fraction": round(self.fraction, 4),
            "wr_used": round(self.wr_used, 4),
            "rr_used": round(self.rr_used, 2),
            "atr_scale": round(self.atr_scale, 3),
            "kelly_raw": round(self.kelly_raw, 4),
            "method": self.method,
            "rationale": self.rationale,
        }


def compute_adaptive_kelly(
    recent_trades: list[dict],           # [{result:'WIN'|'LOSS', pnl_pips:float}]
    atr_current: Optional[float] = None,
    rr_target: float = 1.5,
    window: int = WR_WINDOW_DEFAULT,
) -> KellyResult:
    """Calcule la fraction Kelly adaptative.

    R6 fail-open : retourne fraction floor si données insuffisantes.
    """
    # --- WR rolling ---
    if not recent_trades or len(recent_trades) < 10:
        return KellyResult(
            fraction=MIN_KELLY,
            wr_used=0.5,
            rr_used=rr_target,
            atr_scale=1.0,
            kelly_raw=0.0,
            method="floor",
            rationale="insufficient_trades (<10) — floor applied",
        )

    window_trades = recent_trades[-window:]
    wins = sum(1 for t in window_trades if t.get("result") == "WIN")
    wr = wins / len(window_trades)

    # --- Kelly pur ---
    # f* = p - q/b   avec p=WR, q=1-WR, b=R:R
    kelly_raw = wr - (1 - wr) / max(rr_target, 0.5)

    if kelly_raw <= 0:
        return KellyResult(
            fraction=MIN_KELLY,
            wr_used=wr,
            rr_used=rr_target,
            atr_scale=1.0,
            kelly_raw=kelly_raw,
            method="floor",
            rationale=f"kelly_raw={kelly_raw:.4f} <= 0 — no edge detected, floor applied",
        )

    # --- Scale ATR ---
    atr_scale = 1.0
    if atr_current is not None and atr_current > 0:
        # Volatilité élevée → réduire taille
        atr_scale = min(1.2, max(0.6, ATR_NEUTRAL_PIPS / atr_current))

    # --- Fraction finale ---
    fraction = kelly_raw * KELLY_FRACTION * atr_scale
    fraction = max(MIN_KELLY, min(MAX_KELLY, fraction))

    return KellyResult(
        fraction=fraction,
        wr_used=wr,
        rr_used=rr_target,
        atr_scale=atr_scale,
        kelly_raw=kelly_raw,
        method="adaptive",
        rationale=(
            f"WR={wr:.2%} RR={rr_target} ATR_scale={atr_scale:.2f} "
            f"Kelly_raw={kelly_raw:.4f} → {fraction:.4f}"
        ),
    )


__all__ = ["KellyResult", "compute_adaptive_kelly", "KELLY_FRACTION", "MIN_KELLY", "MAX_KELLY"]
