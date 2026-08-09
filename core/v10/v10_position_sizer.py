"""
v10_position_sizer.py — Cycle 16
Calcul de la taille de position en % du capital selon ATR, risque fixe et Kelly.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class SizingResult:
    pair: str
    risk_pct: float          # % du capital risqué
    lot_size: float          # en lots standard
    sl_pips: float
    tp_pips: float
    rr_ratio: float
    method: str

    def as_dict(self) -> dict:
        return {
            "pair": self.pair,
            "risk_pct": round(self.risk_pct, 4),
            "lot_size": round(self.lot_size, 4),
            "sl_pips": round(self.sl_pips, 2),
            "tp_pips": round(self.tp_pips, 2),
            "rr_ratio": round(self.rr_ratio, 2),
            "method": self.method,
        }


class PositionSizer:
    """
    Calcule la taille de position avec plusieurs méthodes combinables.
    """

    PIP_VALUE_USD = 10.0       # valeur 1 pip pour 1 lot standard en USD
    MAX_RISK_PCT = 0.02        # 2% max par trade
    MIN_LOT = 0.01
    MAX_LOT = 10.0

    def __init__(self, capital: float = 10_000.0) -> None:
        self.capital = capital

    def fixed_risk(self, pair: str, sl_pips: float, tp_pips: float,
                   risk_pct: float = 0.01) -> SizingResult:
        risk_pct = min(risk_pct, self.MAX_RISK_PCT)
        risk_amount = self.capital * risk_pct
        lot = risk_amount / (sl_pips * self.PIP_VALUE_USD)
        lot = max(self.MIN_LOT, min(self.MAX_LOT, round(lot, 2)))
        rr = tp_pips / sl_pips if sl_pips > 0 else 0.0
        return SizingResult(pair=pair, risk_pct=risk_pct, lot_size=lot,
                            sl_pips=sl_pips, tp_pips=tp_pips, rr_ratio=rr, method="fixed_risk")

    def atr_based(self, pair: str, atr_pips: float, tp_pips: float,
                  atr_multiplier: float = 1.5, risk_pct: float = 0.01) -> SizingResult:
        sl_pips = atr_pips * atr_multiplier
        return self.fixed_risk(pair, sl_pips, tp_pips, risk_pct)

    def kelly_adjusted(self, pair: str, sl_pips: float, tp_pips: float,
                       kelly_fraction: float, risk_pct_cap: float = 0.02) -> SizingResult:
        risk_pct = min(kelly_fraction, risk_pct_cap)
        return self.fixed_risk(pair, sl_pips, tp_pips, risk_pct)

    def update_capital(self, new_capital: float) -> None:
        self.capital = new_capital
