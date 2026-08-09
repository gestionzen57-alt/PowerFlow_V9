"""
v10_correlation_matrix.py — Cycle 16
Matrice de corrélation entre paires Forex pour limiter l'exposition corrélée.
"""
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Tuple
import statistics


@dataclass
class CorrelationEntry:
    pair_a: str
    pair_b: str
    correlation: float
    high_correlation: bool   # |corr| > threshold

    def as_dict(self) -> dict:
        return {
            "pair_a": self.pair_a,
            "pair_b": self.pair_b,
            "corr": round(self.correlation, 4),
            "high_corr": self.high_correlation,
        }


class CorrelationMatrix:
    """
    Calcule la corrélation de Pearson en fenêtre glissante entre paires.
    """

    HIGH_CORR_THRESHOLD = 0.70

    def __init__(self, window: int = 30) -> None:
        self.window = window
        self._returns: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window))

    def feed(self, pair: str, ret: float) -> None:
        self._returns[pair].append(ret)

    def correlation(self, pair_a: str, pair_b: str) -> Optional[float]:
        a = list(self._returns.get(pair_a, []))
        b = list(self._returns.get(pair_b, []))
        n = min(len(a), len(b))
        if n < 5:
            return None
        a, b = a[-n:], b[-n:]
        mean_a = statistics.mean(a)
        mean_b = statistics.mean(b)
        cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / n
        std_a = statistics.stdev(a)
        std_b = statistics.stdev(b)
        if std_a == 0 or std_b == 0:
            return 0.0
        return cov / (std_a * std_b)

    def full_matrix(self) -> List[CorrelationEntry]:
        pairs = list(self._returns.keys())
        entries = []
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                corr = self.correlation(pairs[i], pairs[j])
                if corr is not None:
                    entries.append(CorrelationEntry(
                        pair_a=pairs[i], pair_b=pairs[j],
                        correlation=corr,
                        high_correlation=abs(corr) >= self.HIGH_CORR_THRESHOLD,
                    ))
        return entries

    def high_corr_pairs(self) -> List[CorrelationEntry]:
        return [e for e in self.full_matrix() if e.high_correlation]

    def reset(self) -> None:
        self._returns.clear()


from typing import Optional  # noqa: E402 (keep at end to avoid circular)
