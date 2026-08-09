"""
v10_walk_forward.py — Cycle 18
Walk-Forward Analysis : fenêtres IS/OOS.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, List


@dataclass
class WFWindow:
    window_id: int
    is_start: int
    is_end: int
    oos_start: int
    oos_end: int
    is_metric: float
    oos_metric: float
    efficiency: float

    def as_dict(self) -> dict:
        return {
            "id": self.window_id,
            "is": [self.is_start, self.is_end],
            "oos": [self.oos_start, self.oos_end],
            "is_metric": round(self.is_metric, 4),
            "oos_metric": round(self.oos_metric, 4),
            "efficiency": round(self.efficiency, 4),
        }


@dataclass
class WFResult:
    windows: List[WFWindow] = field(default_factory=list)
    avg_efficiency: float = 0.0
    robust: bool = False

    def as_dict(self) -> dict:
        return {
            "windows": [w.as_dict() for w in self.windows],
            "avg_efficiency": round(self.avg_efficiency, 4),
            "robust": self.robust,
        }


class WalkForward:
    ROBUST_THRESHOLD = 0.55

    def __init__(self, n_windows: int = 5, oos_ratio: float = 0.3) -> None:
        self.n_windows = n_windows
        self.oos_ratio = oos_ratio

    def run(self, data: List, metric_fn: Callable[[List], float]) -> WFResult:
        n = len(data)
        if n < self.n_windows * 10:
            return WFResult()
        window_size = n // self.n_windows
        oos_size = max(1, int(window_size * self.oos_ratio))
        is_size = window_size - oos_size
        result = WFResult()
        for i in range(self.n_windows):
            start = i * window_size
            is_end = start + is_size
            oos_end = min(start + window_size, n)
            if is_end >= oos_end:
                continue
            is_m = metric_fn(data[start:is_end])
            oos_m = metric_fn(data[is_end:oos_end])
            eff = oos_m / is_m if is_m > 0 else 0.0
            result.windows.append(WFWindow(
                window_id=i, is_start=start, is_end=is_end,
                oos_start=is_end, oos_end=oos_end,
                is_metric=is_m, oos_metric=oos_m, efficiency=eff,
            ))
        if result.windows:
            result.avg_efficiency = sum(w.efficiency for w in result.windows) / len(result.windows)
        result.robust = result.avg_efficiency >= self.ROBUST_THRESHOLD
        return result
