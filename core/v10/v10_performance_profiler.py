"""
v10_performance_profiler.py — Cycle 14
Profiling détaillé des performances par paire, session, timeframe et régime.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import statistics


@dataclass
class TradeRecord:
    pair: str
    session: str
    timeframe: str
    regime: str
    pnl: float
    duration_min: float
    win: bool
    score: float


@dataclass
class ProfileSnapshot:
    pair: str
    total_trades: int
    win_rate: float
    avg_pnl: float
    avg_duration: float
    sharpe_approx: float
    best_session: str
    best_timeframe: str
    worst_regime: str

    def as_dict(self) -> dict:
        return {
            "pair": self.pair,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "avg_pnl": round(self.avg_pnl, 4),
            "avg_duration": round(self.avg_duration, 2),
            "sharpe_approx": round(self.sharpe_approx, 4),
            "best_session": self.best_session,
            "best_timeframe": self.best_timeframe,
            "worst_regime": self.worst_regime,
        }


class PerformanceProfiler:
    """
    Agrège les trades et produit des snapshots de performance par paire.
    """

    def __init__(self) -> None:
        self._records: List[TradeRecord] = []

    def add_trade(self, record: TradeRecord) -> None:
        self._records.append(record)

    def profile_pair(self, pair: str) -> Optional[ProfileSnapshot]:
        trades = [r for r in self._records if r.pair == pair]
        if not trades:
            return None

        wins = [t for t in trades if t.win]
        pnls = [t.pnl for t in trades]
        win_rate = len(wins) / len(trades)
        avg_pnl = statistics.mean(pnls)
        avg_dur = statistics.mean(t.duration_min for t in trades)

        # Sharpe approximé
        if len(pnls) > 1:
            std = statistics.stdev(pnls)
            sharpe = avg_pnl / std if std > 0 else 0.0
        else:
            sharpe = 0.0

        # Meilleure session
        session_pnl: Dict[str, List[float]] = {}
        for t in trades:
            session_pnl.setdefault(t.session, []).append(t.pnl)
        best_session = max(session_pnl, key=lambda s: statistics.mean(session_pnl[s]))

        # Meilleur timeframe
        tf_pnl: Dict[str, List[float]] = {}
        for t in trades:
            tf_pnl.setdefault(t.timeframe, []).append(t.pnl)
        best_tf = max(tf_pnl, key=lambda s: statistics.mean(tf_pnl[s]))

        # Pire régime
        regime_pnl: Dict[str, List[float]] = {}
        for t in trades:
            regime_pnl.setdefault(t.regime, []).append(t.pnl)
        worst_regime = min(regime_pnl, key=lambda s: statistics.mean(regime_pnl[s]))

        return ProfileSnapshot(
            pair=pair,
            total_trades=len(trades),
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            avg_duration=avg_dur,
            sharpe_approx=sharpe,
            best_session=best_session,
            best_timeframe=best_tf,
            worst_regime=worst_regime,
        )

    def profile_all(self) -> Dict[str, dict]:
        pairs = {r.pair for r in self._records}
        result = {}
        for p in pairs:
            snap = self.profile_pair(p)
            if snap:
                result[p] = snap.as_dict()
        return result

    def top_pairs(self, n: int = 5) -> List[str]:
        profiles = self.profile_all()
        sorted_pairs = sorted(profiles, key=lambda p: profiles[p]["sharpe_approx"], reverse=True)
        return sorted_pairs[:n]

    def reset(self) -> None:
        self._records.clear()
