"""
v10_exit_manager.py — Cycle 17
Plan de sortie structuré : TP partiels, SL, time-based exit.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class ExitLevel:
    level_type: str
    price: float
    lot_pct: float
    triggered: bool = False

    def as_dict(self) -> dict:
        return {
            "type": self.level_type,
            "price": round(self.price, 5),
            "lot_pct": round(self.lot_pct, 2),
            "triggered": self.triggered,
        }


@dataclass
class ExitPlan:
    pair: str
    direction: str
    entry_price: float
    levels: List[ExitLevel] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pair": self.pair,
            "direction": self.direction,
            "entry": round(self.entry_price, 5),
            "levels": [lv.as_dict() for lv in self.levels],
        }


class ExitManager:
    DEFAULT_PARTIALS = [
        ("TP1", 1.0, 0.40),
        ("TP2", 2.0, 0.40),
        ("TP3", 3.0, 0.20),
    ]

    def build_plan(self, pair: str, direction: str, entry: float,
                   sl_pips: float, pip_value: float = 0.0001) -> ExitPlan:
        plan = ExitPlan(pair=pair, direction=direction, entry_price=entry)
        sign = 1 if direction == "BUY" else -1
        sl_price = entry - sign * sl_pips * pip_value
        plan.levels.append(ExitLevel("SL", sl_price, 1.0))
        for name, rr, pct in self.DEFAULT_PARTIALS:
            tp_price = entry + sign * sl_pips * rr * pip_value
            plan.levels.append(ExitLevel(name, tp_price, pct))
        return plan

    def check_triggers(self, plan: ExitPlan, current_price: float) -> List[ExitLevel]:
        triggered = []
        for level in plan.levels:
            if level.triggered:
                continue
            if plan.direction == "BUY":
                hit = current_price >= level.price if level.level_type != "SL" else current_price <= level.price
            else:
                hit = current_price <= level.price if level.level_type != "SL" else current_price >= level.price
            if hit:
                level.triggered = True
                triggered.append(level)
        return triggered
