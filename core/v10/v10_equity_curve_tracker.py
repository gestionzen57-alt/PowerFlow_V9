"""
v10_equity_curve_tracker.py — Cycle 15
Suivi de la courbe d'equity avec points d'inflexion, HWM et périodes de recovery.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class EquityPoint:
    index: int
    equity: float
    drawdown: float
    is_hwm: bool  # High Water Mark

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "equity": round(self.equity, 4),
            "drawdown": round(self.drawdown, 4),
            "is_hwm": self.is_hwm,
        }


class EquityCurveTracker:
    """
    Enregistre l'évolution de l'equity et expose des statistiques clés.
    """

    def __init__(self, initial_equity: float = 10_000.0) -> None:
        self._initial = initial_equity
        self._points: List[EquityPoint] = []
        self._hwm: float = initial_equity
        self._equity: float = initial_equity

    def record(self, pnl: float) -> EquityPoint:
        self._equity += pnl
        is_hwm = self._equity >= self._hwm
        if is_hwm:
            self._hwm = self._equity
        dd = (self._hwm - self._equity) / self._hwm if self._hwm > 0 else 0.0
        pt = EquityPoint(
            index=len(self._points),
            equity=self._equity,
            drawdown=dd,
            is_hwm=is_hwm,
        )
        self._points.append(pt)
        return pt

    @property
    def current_equity(self) -> float:
        return self._equity

    @property
    def high_water_mark(self) -> float:
        return self._hwm

    @property
    def current_drawdown(self) -> float:
        return self._points[-1].drawdown if self._points else 0.0

    @property
    def max_drawdown(self) -> float:
        return max((p.drawdown for p in self._points), default=0.0)

    def total_return(self) -> float:
        return (self._equity - self._initial) / self._initial

    def recovery_factor(self) -> float:
        md = self.max_drawdown
        return self.total_return() / md if md > 0 else float("inf")

    def last_n(self, n: int = 20) -> List[dict]:
        return [p.as_dict() for p in self._points[-n:]]

    def reset(self) -> None:
        self._points.clear()
        self._hwm = self._initial
        self._equity = self._initial
