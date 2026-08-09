"""
v10_feed_handler.py — Cycle 19
Gestionnaire de flux prix : buffer de ticks, OHLCV, détection de gaps.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class Tick:
    pair: str
    bid: float
    ask: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def as_dict(self) -> dict:
        return {
            "pair": self.pair, "bid": round(self.bid, 5),
            "ask": round(self.ask, 5), "mid": round(self.mid, 5),
            "spread_pips": round(self.spread / 0.0001, 1),
            "ts": self.timestamp,
        }


@dataclass
class OHLCV:
    pair: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: str

    def as_dict(self) -> dict:
        return {
            "pair": self.pair, "tf": self.timeframe,
            "open": self.open, "high": self.high,
            "low": self.low, "close": self.close,
            "volume": self.volume, "ts": self.timestamp,
        }


class FeedHandler:
    """
    Reçoit les ticks, maintient un buffer OHLCV rolling et détecte les gaps.
    """
    MAX_TICKS = 1000
    GAP_THRESHOLD_PIPS = 20.0

    def __init__(self) -> None:
        self._ticks: Dict[str, Deque[Tick]] = {}
        self._last_price: Dict[str, float] = {}
        self._gap_alerts: List[str] = []

    def on_tick(self, tick: Tick) -> Optional[str]:
        if tick.pair not in self._ticks:
            self._ticks[tick.pair] = deque(maxlen=self.MAX_TICKS)
        self._ticks[tick.pair].append(tick)

        # Détection gap
        last = self._last_price.get(tick.pair)
        alert = None
        if last is not None:
            gap_pips = abs(tick.mid - last) / 0.0001
            if gap_pips >= self.GAP_THRESHOLD_PIPS:
                alert = f"GAP {tick.pair}: {gap_pips:.1f} pips"
                self._gap_alerts.append(alert)
        self._last_price[tick.pair] = tick.mid
        return alert

    def latest_tick(self, pair: str) -> Optional[Tick]:
        buf = self._ticks.get(pair)
        return buf[-1] if buf else None

    def spread_ok(self, pair: str, max_spread_pips: float = 3.0) -> bool:
        t = self.latest_tick(pair)
        return t is not None and t.spread / 0.0001 <= max_spread_pips

    def recent_ticks(self, pair: str, n: int = 10) -> List[dict]:
        buf = self._ticks.get(pair, deque())
        return [t.as_dict() for t in list(buf)[-n:]]

    def gap_alerts(self) -> List[str]:
        return list(self._gap_alerts)

    def reset(self) -> None:
        self._ticks.clear()
        self._last_price.clear()
        self._gap_alerts.clear()
