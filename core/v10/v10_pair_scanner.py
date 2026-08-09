"""
v10_pair_scanner.py — Cycle 14
Scan dynamique des paires Forex pour identifier les meilleures opportunités
en fonction du score de confluence, de la liquidité et du spread.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


FX_PAIRS_DEFAULT = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "NZDUSD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY",
    "AUDJPY", "EURAUD", "GBPAUD", "CADJPY", "EURNZD",
]


@dataclass
class PairSnapshot:
    pair: str
    confluence_score: float      # 0-100
    spread_pips: float
    liquidity_score: float       # 0-1
    momentum: float              # -1 à +1
    regime: str
    trade_eligible: bool
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "pair": self.pair,
            "confluence": round(self.confluence_score, 2),
            "spread_pips": round(self.spread_pips, 2),
            "liquidity": round(self.liquidity_score, 3),
            "momentum": round(self.momentum, 3),
            "regime": self.regime,
            "eligible": self.trade_eligible,
            "reason": self.reason,
        }


class PairScanner:
    """
    Évalue et classe les paires Forex selon leur attractivité en temps réel.
    """

    MAX_SPREAD_PIPS: float = 2.5
    MIN_CONFLUENCE: float = 60.0
    MIN_LIQUIDITY: float = 0.4

    def __init__(self, pairs: Optional[List[str]] = None) -> None:
        self.pairs = pairs or FX_PAIRS_DEFAULT
        self._snapshots: Dict[str, PairSnapshot] = {}

    def update(self, snap: PairSnapshot) -> None:
        self._snapshots[snap.pair] = snap

    def evaluate(self, snap: PairSnapshot) -> PairSnapshot:
        """Applique les règles d'éligibilité et retourne le snapshot mis à jour."""
        eligible = True
        reasons = []

        if snap.spread_pips > self.MAX_SPREAD_PIPS:
            eligible = False
            reasons.append(f"spread {snap.spread_pips:.2f}>{self.MAX_SPREAD_PIPS}")
        if snap.confluence_score < self.MIN_CONFLUENCE:
            eligible = False
            reasons.append(f"confluence {snap.confluence_score:.1f}<{self.MIN_CONFLUENCE}")
        if snap.liquidity_score < self.MIN_LIQUIDITY:
            eligible = False
            reasons.append(f"liquidity {snap.liquidity_score:.2f}<{self.MIN_LIQUIDITY}")
        if snap.regime in ("choppy", "news_blackout"):
            eligible = False
            reasons.append(f"regime={snap.regime}")

        snap.trade_eligible = eligible
        snap.reason = "; ".join(reasons) if reasons else "OK"
        self.update(snap)
        return snap

    def top_eligible(self, n: int = 3) -> List[PairSnapshot]:
        eligible = [s for s in self._snapshots.values() if s.trade_eligible]
        return sorted(eligible, key=lambda s: s.confluence_score, reverse=True)[:n]

    def all_snapshots(self) -> List[dict]:
        return [s.as_dict() for s in self._snapshots.values()]

    def reset(self) -> None:
        self._snapshots.clear()
