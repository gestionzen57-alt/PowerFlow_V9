"""
v10_drawdown_analyzer.py — Cycle 15
Analyse approfondie des drawdowns : durée, profondeur, fréquence, recovery time.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DrawdownEvent:
    start_idx: int
    end_idx: Optional[int]
    peak_equity: float
    trough_equity: float
    depth_pct: float
    duration: int  # en barres
    recovered: bool

    def as_dict(self) -> dict:
        return {
            "start": self.start_idx,
            "end": self.end_idx,
            "peak": round(self.peak_equity, 4),
            "trough": round(self.trough_equity, 4),
            "depth_pct": round(self.depth_pct, 4),
            "duration": self.duration,
            "recovered": self.recovered,
        }


class DrawdownAnalyzer:
    """
    Détecte et caractérise chaque période de drawdown dans une série d'equity.
    """

    def __init__(self) -> None:
        self._equities: List[float] = []

    def feed(self, equity: float) -> None:
        self._equities.append(equity)

    def analyze(self) -> List[DrawdownEvent]:
        if len(self._equities) < 2:
            return []
        events: List[DrawdownEvent] = []
        hwm = self._equities[0]
        hwm_idx = 0
        in_dd = False
        trough = hwm
        trough_idx = 0

        for i, eq in enumerate(self._equities):
            if eq >= hwm:
                if in_dd:
                    depth = (hwm - trough) / hwm if hwm > 0 else 0.0
                    events.append(DrawdownEvent(
                        start_idx=hwm_idx,
                        end_idx=i,
                        peak_equity=hwm,
                        trough_equity=trough,
                        depth_pct=depth,
                        duration=i - hwm_idx,
                        recovered=True,
                    ))
                    in_dd = False
                hwm = eq
                hwm_idx = i
            else:
                if not in_dd:
                    in_dd = True
                    trough = eq
                    trough_idx = i
                elif eq < trough:
                    trough = eq
                    trough_idx = i

        # DD non terminé
        if in_dd:
            depth = (hwm - trough) / hwm if hwm > 0 else 0.0
            events.append(DrawdownEvent(
                start_idx=hwm_idx,
                end_idx=None,
                peak_equity=hwm,
                trough_equity=trough,
                depth_pct=depth,
                duration=len(self._equities) - hwm_idx,
                recovered=False,
            ))
        return events

    def max_drawdown_event(self) -> Optional[DrawdownEvent]:
        events = self.analyze()
        return max(events, key=lambda e: e.depth_pct) if events else None

    def avg_depth(self) -> float:
        events = self.analyze()
        return sum(e.depth_pct for e in events) / len(events) if events else 0.0

    def reset(self) -> None:
        self._equities.clear()
