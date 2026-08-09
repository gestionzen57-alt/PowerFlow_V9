"""
v10_execution_scorer.py — CYCLE 13 : Execution Quality Scorer
C13-OPT4 : Score qualité d'exécution post-trade (fill_rate, slippage, latence).
Doctrine : R2 | R6 fail-open | R9 audit
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionRecord:
    pair: str
    requested_price: float
    fill_price: float
    latency_ms: float
    rejected: bool = False
    slippage_estimated_pips: float = 0.0


@dataclass
class ExecutionScoreResult:
    score: float = 1.0
    fill_rate: float = 1.0
    avg_slippage_pips: float = 0.0
    slippage_vs_estimate: float = 0.0
    avg_latency_ms: float = 0.0
    rejection_rate: float = 0.0
    grade: str = "A"
    records_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "fill_rate": self.fill_rate,
                "avg_slippage_pips": self.avg_slippage_pips, "slippage_vs_estimate": self.slippage_vs_estimate,
                "avg_latency_ms": self.avg_latency_ms, "rejection_rate": self.rejection_rate, "grade": self.grade}


def score_execution_batch(records: list[ExecutionRecord], pip_size: float = 0.0001) -> ExecutionScoreResult:
    result = ExecutionScoreResult(records_count=len(records))
    if not records:
        result.grade = "N/A"
        return result
    try:
        filled = [r for r in records if not r.rejected]
        result.fill_rate = len(filled) / len(records)
        result.rejection_rate = 1.0 - result.fill_rate
        if filled:
            slippages = [abs(r.fill_price - r.requested_price) / pip_size for r in filled]
            result.avg_slippage_pips = round(sum(slippages) / len(slippages), 3)
            result.avg_latency_ms = round(sum(r.latency_ms for r in filled) / len(filled), 2)
            avg_est = sum(r.slippage_estimated_pips for r in filled) / len(filled)
            result.slippage_vs_estimate = round(result.avg_slippage_pips - avg_est, 3)
        s = result.fill_rate * 0.4 + max(0, 1 - result.avg_slippage_pips / 5.0) * 0.3 + max(0, 1 - result.avg_latency_ms / 500.0) * 0.3
        result.score = round(min(1.0, max(0.0, s)), 4)
        result.grade = "A" if result.score >= 0.85 else "B" if result.score >= 0.70 else "C" if result.score >= 0.55 else "D"
    except Exception as e:
        warnings.warn(f"[C13] ExecutionScorer error (fail-open): {e}")
        result.grade = "ERROR"
    return result
