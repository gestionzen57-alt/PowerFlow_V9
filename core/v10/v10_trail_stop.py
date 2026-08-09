"""
v10_trail_stop.py — Cycle 17
Trailing stop : ATR-based, break-even automatique.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class TrailState:
    pair: str
    direction: str
    entry_price: float
    current_stop: float
    best_price: float
    in_breakeven: bool
    trail_mode: str

    def as_dict(self) -> dict:
        return {
            "pair": self.pair,
            "direction": self.direction,
            "entry": round(self.entry_price, 5),
            "stop": round(self.current_stop, 5),
            "best": round(self.best_price, 5),
            "breakeven": self.in_breakeven,
            "mode": self.trail_mode,
        }


class TrailStop:
    BREAKEVEN_TRIGGER_R = 1.0
    ATR_TRAIL_TRIGGER_R = 1.5
    ATR_TRAIL_MULT = 1.2

    def __init__(self, pair: str, direction: str, entry: float,
                 initial_stop: float, risk_pips: float,
                 pip_value: float = 0.0001) -> None:
        self.state = TrailState(
            pair=pair, direction=direction,
            entry_price=entry, current_stop=initial_stop,
            best_price=entry, in_breakeven=False, trail_mode="INITIAL",
        )
        self._risk_price = risk_pips * pip_value

    def update(self, current_price: float, atr: Optional[float] = None) -> TrailState:
        sign = 1 if self.state.direction == "BUY" else -1
        price_gain = sign * (current_price - self.state.entry_price)
        r_multiple = price_gain / self._risk_price if self._risk_price > 0 else 0.0
        if sign * current_price > sign * self.state.best_price:
            self.state.best_price = current_price
        if not self.state.in_breakeven and r_multiple >= self.BREAKEVEN_TRIGGER_R:
            self.state.current_stop = self.state.entry_price
            self.state.in_breakeven = True
            self.state.trail_mode = "BREAKEVEN"
        if atr and r_multiple >= self.ATR_TRAIL_TRIGGER_R:
            new_stop = self.state.best_price - sign * atr * self.ATR_TRAIL_MULT
            if sign * new_stop > sign * self.state.current_stop:
                self.state.current_stop = new_stop
                self.state.trail_mode = "ATR"
        return self.state

    def is_stopped(self, current_price: float) -> bool:
        sign = 1 if self.state.direction == "BUY" else -1
        return sign * current_price <= sign * self.state.current_stop
