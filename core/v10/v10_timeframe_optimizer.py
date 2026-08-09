"""
v10_timeframe_optimizer.py — Cycle 14
Sélectionne le timeframe optimal par paire selon les conditions de marché.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import statistics


TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

TF_WEIGHT: Dict[str, float] = {
    "M1": 0.5,
    "M5": 0.7,
    "M15": 0.85,
    "M30": 0.9,
    "H1": 1.0,
    "H4": 0.95,
    "D1": 0.8,
}


@dataclass
class TFScore:
    timeframe: str
    pair: str
    raw_score: float
    weighted_score: float
    sample_count: int
    recommended: bool

    def as_dict(self) -> dict:
        return {
            "tf": self.timeframe,
            "pair": self.pair,
            "raw": round(self.raw_score, 4),
            "weighted": round(self.weighted_score, 4),
            "samples": self.sample_count,
            "recommended": self.recommended,
        }


class TimeframeOptimizer:
    """
    Stocke les performances historiques par (pair, timeframe)
    et recommande le timeframe optimal.
    """

    def __init__(self) -> None:
        # _perf[pair][tf] = [pnl, ...]
        self._perf: Dict[str, Dict[str, List[float]]] = {}

    def record(self, pair: str, tf: str, pnl: float) -> None:
        self._perf.setdefault(pair, {}).setdefault(tf, []).append(pnl)

    def score_timeframes(self, pair: str) -> List[TFScore]:
        tf_data = self._perf.get(pair, {})
        scores: List[TFScore] = []
        for tf in TIMEFRAMES:
            pnls = tf_data.get(tf, [])
            if not pnls:
                continue
            raw = statistics.mean(pnls)
            weighted = raw * TF_WEIGHT.get(tf, 1.0)
            scores.append(
                TFScore(
                    timeframe=tf,
                    pair=pair,
                    raw_score=raw,
                    weighted_score=weighted,
                    sample_count=len(pnls),
                    recommended=False,
                )
            )
        if scores:
            best = max(scores, key=lambda s: s.weighted_score)
            best.recommended = True
        return scores

    def best_timeframe(self, pair: str) -> Optional[str]:
        scores = self.score_timeframes(pair)
        recommended = [s for s in scores if s.recommended]
        return recommended[0].timeframe if recommended else None

    def all_recommendations(self) -> Dict[str, Optional[str]]:
        return {pair: self.best_timeframe(pair) for pair in self._perf}

    def reset(self) -> None:
        self._perf.clear()
