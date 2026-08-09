"""
v10_kelly_criterion.py — Cycle 16
Calcul du critère de Kelly complet, fractionné et avec plafond de sécurité.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import statistics


@dataclass
class KellyResult:
    win_rate: float
    avg_win: float
    avg_loss: float
    rr_ratio: float
    full_kelly: float
    half_kelly: float
    quarter_kelly: float
    capped_kelly: float      # plafonné à MAX_KELLY
    recommended: float

    def as_dict(self) -> dict:
        return {
            "win_rate": round(self.win_rate, 4),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "rr": round(self.rr_ratio, 4),
            "full_kelly": round(self.full_kelly, 4),
            "half_kelly": round(self.half_kelly, 4),
            "quarter_kelly": round(self.quarter_kelly, 4),
            "capped_kelly": round(self.capped_kelly, 4),
            "recommended": round(self.recommended, 4),
        }


class KellyCriterion:
    """
    Kelly = (W * R - L) / R
    W = win rate, R = gain moyen / perte moyenne, L = loss rate
    """

    MAX_KELLY = 0.25   # plafond sécurité 25%
    MIN_SAMPLES = 10

    def compute(self, win_rate: float, avg_win: float, avg_loss: float) -> KellyResult:
        avg_loss = abs(avg_loss)
        rr = avg_win / avg_loss if avg_loss > 0 else 1.0
        loss_rate = 1.0 - win_rate
        full_kelly = (win_rate * rr - loss_rate) / rr if rr > 0 else 0.0
        full_kelly = max(0.0, full_kelly)
        half = full_kelly / 2
        quarter = full_kelly / 4
        capped = min(full_kelly, self.MAX_KELLY)
        return KellyResult(
            win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
            rr_ratio=rr, full_kelly=full_kelly, half_kelly=half,
            quarter_kelly=quarter, capped_kelly=capped, recommended=capped,
        )

    def from_trades(self, pnls: List[float]) -> Optional[KellyResult]:
        if len(pnls) < self.MIN_SAMPLES:
            return None
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        if not wins or not losses:
            return None
        wr = len(wins) / len(pnls)
        avg_win = statistics.mean(wins)
        avg_loss = abs(statistics.mean(losses))
        return self.compute(wr, avg_win, avg_loss)
