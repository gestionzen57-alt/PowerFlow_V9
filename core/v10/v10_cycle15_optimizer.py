"""
v10_cycle15_optimizer.py — Cycle 15 Orchestrator
Pipeline : RiskDashboard + EquityCurveTracker + DrawdownAnalyzer +
StreakDetector + SharpeRolling → C15PostprocessResult
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from core.v10.v10_risk_dashboard import RiskDashboard, DashboardSnapshot
from core.v10.v10_equity_curve_tracker import EquityCurveTracker
from core.v10.v10_drawdown_analyzer import DrawdownAnalyzer
from core.v10.v10_streak_detector import StreakDetector
from core.v10.v10_sharpe_rolling import SharpeRolling


@dataclass
class C15Input:
    trades: List[Dict[str, Any]] = field(default_factory=list)
    # Chaque trade: {pnl, win, equity_after, risk_metrics: dict}


@dataclass
class C15Result:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dashboard: Optional[dict] = None
    equity_summary: dict = field(default_factory=dict)
    max_drawdown_event: Optional[dict] = None
    current_streak: Optional[dict] = None
    streak_alert: Optional[str] = None
    rolling_ratios: Optional[dict] = None
    trading_allowed: bool = True

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "trading_allowed": self.trading_allowed,
            "dashboard": self.dashboard,
            "equity_summary": self.equity_summary,
            "max_drawdown_event": self.max_drawdown_event,
            "current_streak": self.current_streak,
            "streak_alert": self.streak_alert,
            "rolling_ratios": self.rolling_ratios,
        }


class C15Optimizer:
    """
    Cycle 15 — Pipeline de surveillance de la santé du système.
    1. Mise à jour dashboard risque
    2. Suivi courbe d'equity
    3. Analyse drawdowns
    4. Détection séries
    5. Ratios glissants Sharpe/Sortino/Calmar
    """

    def __init__(self, initial_equity: float = 10_000.0, sharpe_window: int = 50) -> None:
        self.dashboard = RiskDashboard()
        self.equity_tracker = EquityCurveTracker(initial_equity=initial_equity)
        self.dd_analyzer = DrawdownAnalyzer()
        self.streak = StreakDetector()
        self.sharpe = SharpeRolling(window=sharpe_window)

    def run(self, inp: C15Input) -> C15Result:
        result = C15Result()

        for trade in inp.trades:
            pnl = trade.get("pnl", 0.0)
            win = trade.get("win", pnl > 0)
            equity = trade.get("equity_after", 0.0)
            risk_metrics = trade.get("risk_metrics", {})

            # 1 — Dashboard
            for k, v in risk_metrics.items():
                self.dashboard.update(k, v)

            # 2 — Equity curve
            self.equity_tracker.record(pnl)
            self.dd_analyzer.feed(self.equity_tracker.current_equity)

            # 3 — Streak
            self.streak.record(win, pnl)

            # 4 — Sharpe rolling
            self.sharpe.record(pnl, equity or self.equity_tracker.current_equity)

        # Résultats
        snap = self.dashboard.snapshot()
        result.dashboard = snap.as_dict()
        result.trading_allowed = snap.trading_allowed

        result.equity_summary = {
            "current_equity": round(self.equity_tracker.current_equity, 4),
            "hwm": round(self.equity_tracker.high_water_mark, 4),
            "current_dd": round(self.equity_tracker.current_drawdown, 4),
            "max_dd": round(self.equity_tracker.max_drawdown, 4),
            "total_return": round(self.equity_tracker.total_return(), 4),
            "recovery_factor": round(self.equity_tracker.recovery_factor(), 4),
        }

        mde = self.dd_analyzer.max_drawdown_event()
        result.max_drawdown_event = mde.as_dict() if mde else None

        cs = self.streak.current_streak()
        result.current_streak = cs.as_dict() if cs else None
        result.streak_alert = self.streak.streak_alert()

        result.rolling_ratios = self.sharpe.compute().as_dict()

        return result

    def reset(self) -> None:
        self.dashboard.reset()
        self.equity_tracker.reset()
        self.dd_analyzer.reset()
        self.streak.reset()
        self.sharpe.reset()
