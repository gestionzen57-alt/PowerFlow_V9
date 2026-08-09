"""
v10_monte_carlo.py — Cycle 18
Monte Carlo : VaR 95%, CVaR, probabilité de ruine.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List
import random, math


@dataclass
class MCResult:
    n_simulations: int
    mean_final_equity: float
    std_final_equity: float
    var_95: float
    cvar_95: float
    max_dd_mean: float
    ruin_probability: float
    percentile_5: float
    percentile_95: float

    def as_dict(self) -> dict:
        return {
            "n_sim": self.n_simulations,
            "mean_equity": round(self.mean_final_equity, 2),
            "std_equity": round(self.std_final_equity, 2),
            "var_95": round(self.var_95, 2),
            "cvar_95": round(self.cvar_95, 2),
            "max_dd_mean": round(self.max_dd_mean, 4),
            "ruin_prob": round(self.ruin_probability, 4),
            "p5": round(self.percentile_5, 2),
            "p95": round(self.percentile_95, 2),
        }


class MonteCarloSimulator:
    RUIN_THRESHOLD = 0.50

    def __init__(self, n_simulations: int = 1000, seed: int = 42) -> None:
        self.n_simulations = n_simulations
        self.seed = seed

    def run(self, pnls: List[float], initial_capital: float = 10_000.0) -> MCResult:
        rng = random.Random(self.seed)
        finals, max_dds, ruin_count = [], [], 0
        for _ in range(self.n_simulations):
            shuffled = rng.sample(pnls, len(pnls))
            equity, hwm, max_dd = initial_capital, initial_capital, 0.0
            for pnl in shuffled:
                equity += pnl
                if equity > hwm:
                    hwm = equity
                dd = (hwm - equity) / hwm if hwm > 0 else 0
                max_dd = max(max_dd, dd)
            finals.append(equity)
            max_dds.append(max_dd)
            if equity < initial_capital * self.RUIN_THRESHOLD:
                ruin_count += 1
        finals.sort()
        n = len(finals)
        mean = sum(finals) / n
        std = math.sqrt(sum((f - mean)**2 for f in finals) / n)
        i5 = max(0, int(n * 0.05))
        i95 = min(n - 1, int(n * 0.95))
        var_95 = initial_capital - finals[i5]
        cvar_95 = initial_capital - (sum(finals[:i5]) / i5 if i5 > 0 else finals[0])
        return MCResult(
            n_simulations=self.n_simulations,
            mean_final_equity=mean, std_final_equity=std,
            var_95=var_95, cvar_95=cvar_95,
            max_dd_mean=sum(max_dds) / len(max_dds),
            ruin_probability=ruin_count / self.n_simulations,
            percentile_5=finals[i5], percentile_95=finals[i95],
        )
