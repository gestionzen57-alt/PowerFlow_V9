"""
v10_volatility_scaler.py — Cycle 16
Ajuste dynamiquement la taille de position en fonction de la volatilité courante
vs volatilité de référence (ATR normalisé).
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Deque
import statistics


@dataclass
class VolScaleResult:
    current_atr: float
    reference_atr: float
    ratio: float          # current / reference
    scale_factor: float   # facteur appliqué au lot
    regime: str           # LOW_VOL | NORMAL | HIGH_VOL | EXTREME

    def as_dict(self) -> dict:
        return {
            "current_atr": round(self.current_atr, 5),
            "reference_atr": round(self.reference_atr, 5),
            "ratio": round(self.ratio, 4),
            "scale_factor": round(self.scale_factor, 4),
            "regime": self.regime,
        }


class VolatilityScaler:
    """
    Normalise la taille de position par rapport à la volatilité historique.
    Plus la volatilité est haute, plus la position est réduite.
    """

    THRESHOLDS = {
        "LOW_VOL": 0.7,
        "NORMAL": 1.3,
        "HIGH_VOL": 2.0,
    }  # ratios current/reference

    SCALE_MAP = {
        "LOW_VOL": 1.2,
        "NORMAL": 1.0,
        "HIGH_VOL": 0.6,
        "EXTREME": 0.3,
    }

    def __init__(self, window: int = 20) -> None:
        self.window = window
        self._atrs: Deque[float] = deque(maxlen=window)

    def feed(self, atr: float) -> None:
        self._atrs.append(atr)

    def scale(self, current_atr: float) -> VolScaleResult:
        if len(self._atrs) < 5:
            return VolScaleResult(current_atr, current_atr, 1.0, 1.0, "NORMAL")
        ref = statistics.mean(self._atrs)
        ratio = current_atr / ref if ref > 0 else 1.0

        if ratio <= self.THRESHOLDS["LOW_VOL"]:
            regime = "LOW_VOL"
        elif ratio <= self.THRESHOLDS["NORMAL"]:
            regime = "NORMAL"
        elif ratio <= self.THRESHOLDS["HIGH_VOL"]:
            regime = "HIGH_VOL"
        else:
            regime = "EXTREME"

        return VolScaleResult(
            current_atr=current_atr,
            reference_atr=ref,
            ratio=ratio,
            scale_factor=self.SCALE_MAP[regime],
            regime=regime,
        )

    def reset(self) -> None:
        self._atrs.clear()
