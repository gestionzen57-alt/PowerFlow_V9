"""
v10_optimization_grid.py — Cycle 18
Grid search avec overfitting guard.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import itertools, math


@dataclass
class GridPoint:
    params: Dict[str, Any]
    metric: float
    rank: int = 0

    def as_dict(self) -> dict:
        return {"params": self.params, "metric": round(self.metric, 4), "rank": self.rank}


@dataclass
class GridResult:
    best: Optional[GridPoint] = None
    top_n: List[GridPoint] = field(default_factory=list)
    total_tested: int = 0
    overfitting_risk: str = "LOW"

    def as_dict(self) -> dict:
        return {
            "best": self.best.as_dict() if self.best else None,
            "top_n": [p.as_dict() for p in self.top_n],
            "total_tested": self.total_tested,
            "overfitting_risk": self.overfitting_risk,
        }


class OptimizationGrid:
    def run(self, param_space: Dict[str, List], metric_fn: Callable[[Dict], float],
            top_n: int = 5) -> GridResult:
        keys = list(param_space.keys())
        points: List[GridPoint] = []
        for combo in itertools.product(*param_space.values()):
            params = dict(zip(keys, combo))
            try:
                m = metric_fn(params)
            except Exception:
                m = 0.0
            points.append(GridPoint(params=params, metric=m))
        points.sort(key=lambda p: p.metric, reverse=True)
        for i, p in enumerate(points):
            p.rank = i + 1
        result = GridResult(total_tested=len(points))
        if not points:
            return result
        result.best = points[0]
        result.top_n = points[:top_n]
        ms = [p.metric for p in points]
        mean_m = sum(ms) / len(ms)
        std_m = math.sqrt(sum((m - mean_m)**2 for m in ms) / len(ms)) if len(ms) > 1 else 0.0
        z = (points[0].metric - mean_m) / std_m if std_m > 0 else 0.0
        result.overfitting_risk = "HIGH" if z > 3 else "MEDIUM" if z > 1.5 else "LOW"
        return result
