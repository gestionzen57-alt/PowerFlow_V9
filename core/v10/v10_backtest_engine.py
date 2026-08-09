"""
v10_backtest_engine.py — Cycle 18
Moteur de backtest vectorisé.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import math


@dataclass
class BacktestTrade:
    pair: str
    direction: str
    entry: float
    sl: float
    tp: float
    lot: float
    commission: float = 0.0
    slippage_pips: float = 0.0


@dataclass
class BacktestTradeResult:
    trade: BacktestTrade
    pnl: float
    win: bool
    exit_reason: str
    equity_after: float

    def as_dict(self) -> dict:
        return {
            "pair": self.trade.pair,
            "pnl": round(self.pnl, 4),
            "win": self.win,
            "exit_reason": self.exit_reason,
            "equity": round(self.equity_after, 4),
        }


@dataclass
class BacktestSummary:
    initial_capital: float
    final_capital: float
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe: float
    profit_factor: float

    def as_dict(self) -> dict:
        return {
            "initial": round(self.initial_capital, 2),
            "final": round(self.final_capital, 2),
            "trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 4),
            "total_pnl": round(self.total_pnl, 4),
            "max_dd": round(self.max_drawdown, 4),
            "sharpe": round(self.sharpe, 4),
            "profit_factor": round(self.profit_factor, 4),
        }


class BacktestEngine:
    MAX_DD_STOP = 0.20

    def __init__(self, initial_capital: float = 10_000.0) -> None:
        self.initial_capital = initial_capital

    def run(self, trades: List[BacktestTrade]):
        equity = self.initial_capital
        hwm = equity
        max_dd = 0.0
        results: List[BacktestTradeResult] = []
        returns: List[float] = []
        gross_wins = 0.0
        gross_losses = 0.0
        for trade in trades:
            if equity <= 0:
                break
            sl_dist = abs(trade.entry - trade.sl)
            tp_dist = abs(trade.tp - trade.entry)
            rr = tp_dist / sl_dist if sl_dist > 0 else 1.0
            win = rr >= 1.0
            raw_pnl = trade.lot * 10 * (tp_dist / 0.0001 if win else -sl_dist / 0.0001)
            pnl = raw_pnl - trade.commission - trade.slippage_pips * trade.lot * 10
            equity += pnl
            returns.append(pnl)
            gross_wins += max(pnl, 0) if win else 0
            gross_losses += abs(min(pnl, 0)) if not win else 0
            if equity > hwm:
                hwm = equity
            dd = (hwm - equity) / hwm if hwm > 0 else 0
            max_dd = max(max_dd, dd)
            results.append(BacktestTradeResult(
                trade=trade, pnl=pnl, win=win,
                exit_reason="TP" if win else "SL",
                equity_after=equity,
            ))
            if dd >= self.MAX_DD_STOP:
                break
        total = len(results)
        wins = sum(1 for r in results if r.win)
        wr = wins / total if total > 0 else 0.0
        avg = sum(returns) / len(returns) if returns else 0.0
        std = math.sqrt(sum((r - avg)**2 for r in returns) / len(returns)) if len(returns) > 1 else 0.0
        sharpe = avg / std if std > 0 else 0.0
        pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")
        return BacktestSummary(
            initial_capital=self.initial_capital, final_capital=equity,
            total_trades=total, wins=wins, losses=total - wins,
            win_rate=wr, total_pnl=equity - self.initial_capital,
            max_drawdown=max_dd, sharpe=sharpe, profit_factor=pf,
        ), results
