"""
v10_cycle14_optimizer.py — Cycle 14 Orchestrator
Orchestre PerformanceProfiler + HeatmapGenerator + PairScanner +
TimeframeOptimizer + ReportExporter en un pipeline cohérent.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from core.v10.v10_performance_profiler import PerformanceProfiler, TradeRecord
from core.v10.v10_heatmap_generator import HeatmapGenerator
from core.v10.v10_pair_scanner import PairScanner, PairSnapshot
from core.v10.v10_timeframe_optimizer import TimeframeOptimizer
from core.v10.v10_report_exporter import (
    ReportExporter, PerformanceReport, ReportSection
)


@dataclass
class C14Input:
    trades: List[TradeRecord] = field(default_factory=list)
    pair_snapshots: List[PairSnapshot] = field(default_factory=list)


@dataclass
class C14Result:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    top_pairs: List[str] = field(default_factory=list)
    best_timeframes: Dict[str, Optional[str]] = field(default_factory=dict)
    eligible_pairs: List[dict] = field(default_factory=list)
    heatmap_best: Optional[dict] = None
    heatmap_worst: Optional[dict] = None
    report_json: str = ""
    report_text: str = ""

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "top_pairs": self.top_pairs,
            "best_timeframes": self.best_timeframes,
            "eligible_pairs": self.eligible_pairs,
            "heatmap_best": self.heatmap_best,
            "heatmap_worst": self.heatmap_worst,
        }


class C14Optimizer:
    """
    Pipeline Cycle 14 :
    1. Profiling des trades par paire
    2. Heatmap session × paire
    3. Scan et éligibilité des paires live
    4. Optimisation du timeframe par paire
    5. Export rapport complet
    """

    def __init__(self) -> None:
        self.profiler = PerformanceProfiler()
        self.heatmap = HeatmapGenerator()
        self.scanner = PairScanner()
        self.tf_optimizer = TimeframeOptimizer()
        self.exporter = ReportExporter()

    def run(self, inp: C14Input) -> C14Result:
        result = C14Result()

        # 1 — Profiling
        for trade in inp.trades:
            self.profiler.add_trade(trade)
            self.heatmap.record(
                row=trade.pair,
                col=trade.session,
                pnl=trade.pnl,
                win=trade.win,
            )
            self.tf_optimizer.record(trade.pair, trade.timeframe, trade.pnl)

        result.top_pairs = self.profiler.top_pairs(n=5)

        # 2 — Heatmap
        best_cell = self.heatmap.best_cell()
        worst_cell = self.heatmap.worst_cell()
        result.heatmap_best = best_cell.as_dict() if best_cell else None
        result.heatmap_worst = worst_cell.as_dict() if worst_cell else None

        # 3 — Scan paires live
        for snap in inp.pair_snapshots:
            self.scanner.evaluate(snap)
        result.eligible_pairs = [s.as_dict() for s in self.scanner.top_eligible(n=5)]

        # 4 — Timeframe optimal
        result.best_timeframes = self.tf_optimizer.all_recommendations()

        # 5 — Rapport
        report = self._build_report(result)
        result.report_json = self.exporter.to_json(report)
        result.report_text = self.exporter.to_text(report)

        return result

    def _build_report(self, result: C14Result) -> PerformanceReport:
        report = PerformanceReport(cycle="C14")

        # Section top pairs
        top_profiles = self.profiler.profile_all()
        sec_pairs = ReportSection(
            title="Top Pairs",
            metadata={"count": len(result.top_pairs)},
            data=[top_profiles[p] for p in result.top_pairs if p in top_profiles],
        )
        report.add_section(sec_pairs)

        # Section eligible pairs
        sec_elig = ReportSection(
            title="Eligible Pairs",
            metadata={"count": len(result.eligible_pairs)},
            data=result.eligible_pairs,
        )
        report.add_section(sec_elig)

        # Section heatmap
        heatmap_data = []
        if result.heatmap_best:
            heatmap_data.append({"type": "best", **result.heatmap_best})
        if result.heatmap_worst:
            heatmap_data.append({"type": "worst", **result.heatmap_worst})
        sec_heatmap = ReportSection(
            title="Heatmap Summary",
            metadata={},
            data=heatmap_data,
        )
        report.add_section(sec_heatmap)

        # Section timeframes
        tf_data = [
            {"pair": pair, "best_tf": tf or "N/A"}
            for pair, tf in result.best_timeframes.items()
        ]
        sec_tf = ReportSection(
            title="Best Timeframes",
            metadata={"pairs": len(tf_data)},
            data=tf_data,
        )
        report.add_section(sec_tf)

        return report

    def reset(self) -> None:
        self.profiler.reset()
        self.heatmap.reset()
        self.scanner.reset()
        self.tf_optimizer.reset()
