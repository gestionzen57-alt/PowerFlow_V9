"""
v10_entry_timing.py — Cycle 17
Optimise le timing d'entrée : OTE, candle close, pullback.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open


@dataclass
class EntryDecision:
    pair: str
    direction: str
    entry_price: float
    entry_type: str
    confidence: float
    reason: str

    def as_dict(self) -> dict:
        return {
            "pair": self.pair,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 5),
            "entry_type": self.entry_type,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
        }


class EntryTiming:
    OTE_LOW = 0.618
    OTE_HIGH = 0.786
    MIN_BODY_RATIO = 0.4

    def evaluate(self, pair: str, direction: str, candle: Candle,
                 swing_high: float, swing_low: float) -> EntryDecision:
        swing_range = swing_high - swing_low
        if swing_range <= 0:
            return EntryDecision(pair, direction, candle.close, "WAIT", 0.0, "swing_range=0")
        ote_low_price = swing_high - swing_range * self.OTE_HIGH
        ote_high_price = swing_high - swing_range * self.OTE_LOW
        price = candle.close
        in_ote = ote_low_price <= price <= ote_high_price
        strong_candle = candle.body / candle.range >= self.MIN_BODY_RATIO if candle.range > 0 else False
        correct_dir = (direction == "BUY" and candle.is_bullish) or (direction == "SELL" and not candle.is_bullish)
        if in_ote and strong_candle and correct_dir:
            return EntryDecision(pair, direction, price, "MARKET", 90.0, "OTE+strong_candle")
        elif in_ote:
            return EntryDecision(pair, direction,
                                 ote_low_price if direction == "BUY" else ote_high_price,
                                 "LIMIT", 70.0, "OTE_zone_wait_confirm")
        return EntryDecision(pair, direction, price, "WAIT", 40.0, "hors_OTE")
