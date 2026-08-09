"""
v10_cycle18_optimizer.py — Cycle 18 Orchestrator
Pipeline : BacktestEngine + WalkForward + MonteCarlo + OptimizationGrid + ValidationReport
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
from datetime import datetime, timezone

from core.v10.v10_backtest_engine import BacktestEngine, BacktestTrade
from core.v10.v10_walk_forward import WalkForward
from core.v10.v10_monte_carlo import MonteCarloSimulator
from core.v10.v10_optimization_grid import OptimizationGrid
from core.v10.v10_validation_report import ValidationReportBuilder


@dataclass
class C18Input:
    trades: List[BacktestTrade] = field(default_factory=list)
    pnls_series: List[float] = field(default_factory=list)
    wf_data: List[Any] = field(default_factory=list)
    wf_metric_fn: Optional[Callable] = None
    grid_param_space: Dict[str, List] = field(default_factory=dict)
    grid_metric_fn: Optional[Callable] = None
    initial_capital: float = 10_000.0


@dataclass
class C18Result:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    backtest: Optional[dict] = None
    wfa: Optional[dict] = None
    monte_carlo: Optional[dict] = None
    grid: Optional[dict] = None
    validation: Optional[dict] = None
    live_ready: bool = False

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "live_ready": self.live_ready,
            "backtest": self.backtest,
            "wfa": self.wfa,
            "monte_carlo": self.monte_carlo,
            "grid": self.grid,
            "validation": self.validation,
        }


class C18Optimizer:
    """
    Cycle 18 — Pipeline validation quantitative complète.
    1. Backtest vectorisé
    2. Walk-Forward Analysis
    3. Monte Carlo (VaR, CVaR, ruin prob)
    4. Grid Search (optionnel)
    5. Rapport live-readiness
    """

    def __init__(self) -> None:
        self.bt_engine = BacktestEngine()
        self.wfa = WalkForward(n_windows=5, oos_ratio=0.3)
        self.mc = MonteCarloSimulator(n_simulations=500)
        self.grid = OptimizationGrid()
        self.report_builder = ValidationReportBuilder()

    def run(self, inp: C18Input) -> C18Result:
        result = C18Result()
        self.bt_engine.initial_capital = inp.initial_capital
        summary, trade_results = None, []

        if inp.trades:
            summary, trade_results = self.bt_engine.run(inp.trades)
            result.backtest = summary.as_dict()

        wf_res = None
        if inp.wf_data and inp.wf_metric_fn:
            wf_res = self.wfa.run(inp.wf_data, inp.wf_metric_fn)
            result.wfa = wf_res.as_dict()

        pnls = inp.pnls_series or [r.pnl for r in trade_results]
        mc_res = None
        if pnls:
            mc_res = self.mc.run(pnls, inp.initial_capital)
            result.monte_carlo = mc_res.as_dict()

        if inp.grid_param_space and inp.grid_metric_fn:
            result.grid = self.grid.run(inp.grid_param_space, inp.grid_metric_fn).as_dict()

        metrics: Dict[str, float] = {}
        if summary:
            metrics.update({
                "win_rate": summary.win_rate, "sharpe": summary.sharpe,
                "max_drawdown": summary.max_drawdown, "profit_factor": summary.profit_factor,
            })
        if wf_res:
            metrics["wfa_efficiency"] = wf_res.avg_efficiency
        if mc_res:
            metrics["ruin_prob"] = mc_res.ruin_probability
        if metrics:
            report = self.report_builder.build(metrics)
            result.validation = report.as_dict()
            result.live_ready = report.live_ready

        return result
