"""
v10_sharpe_rolling.py — Cycle 15
Calcul du Sharpe ratio en fenêtre glissante avec Sortino et Calmar optionnels.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional
import math


@dataclass
class RollingRatios:
    window: int
    sharpe: float
    sortino: float
    calmar: float
    avg_return: float
    volatility: float
    n_samples: int

    def as_dict(self) -> dict:
        return {
            "window": self.window,
            "sharpe": round(self.sharpe, 4),
            "sortino": round(self.sortino, 4),
            "calmar": round(self.calmar, 4),
            "avg_return": round(self.avg_return, 6),
            "volatility": round(self.volatility, 6),
            "samples": self.n_samples,
        }


class SharpeRolling:
    """
    Fenêtre glissante pour Sharpe, Sortino et Calmar.
    rf_per_bar : taux sans risque par barre (défaut 0).
    """

    def __init__(self, window: int = 50, rf_per_bar: float = 0.0) -> None:
        self.window = window
        self.rf = rf_per_bar
        self._returns: Deque[float] = deque(maxlen=window)
        self._max_equity: float = 0.0
        self._min_equity: float = float("inf")
        self._equity: float = 0.0

    def record(self, pnl: float, equity: float) -> None:
        self._returns.append(pnl)
        self._equity = equity
        self._max_equity = max(self._max_equity, equity)
        self._min_equity = min(self._min_equity, equity)

    def compute(self) -> RollingRatios:
        rets = list(self._returns)
        n = len(rets)
        if n < 2:
            return RollingRatios(self.window, 0.0, 0.0, 0.0, 0.0, 0.0, n)

        avg = sum(rets) / n
        variance = sum((r - avg) ** 2 for r in rets) / (n - 1)
        vol = math.sqrt(variance)

        # Sharpe
        sharpe = (avg - self.rf) / vol if vol > 0 else 0.0

        # Sortino (downside deviation)
        neg = [r for r in rets if r < self.rf]
        if neg:
            down_var = sum((r - self.rf) ** 2 for r in neg) / len(neg)
            down_std = math.sqrt(down_var)
            sortino = (avg - self.rf) / down_std if down_std > 0 else 0.0
        else:
            sortino = sharpe  # aucune perte

        # Calmar
        max_dd = (self._max_equity - self._min_equity) / self._max_equity if self._max_equity > 0 else 0.0
        calmar = avg / max_dd if max_dd > 0 else 0.0

        return RollingRatios(
            window=self.window,
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
            avg_return=avg,
            volatility=vol,
            n_samples=n,
        )

    def reset(self) -> None:
        self._returns.clear()
        self._max_equity = 0.0
        self._min_equity = float("inf")
        self._equity = 0.0
