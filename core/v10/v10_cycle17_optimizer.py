"""
v10_cycle17_optimizer.py — Cycle 17 Orchestrator
Pipeline : SignalValidator + ConfluenceFilter + EntryTiming + ExitManager + TrailStop
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone

from core.v10.v10_signal_validator import SignalValidator, RawSignal
from core.v10.v10_confluence_filter import ConfluenceFilter, ConfluenceVote
from core.v10.v10_entry_timing import EntryTiming, Candle
from core.v10.v10_exit_manager import ExitManager


@dataclass
class C17Input:
    signal: RawSignal
    votes: List[ConfluenceVote]
    candle: Optional[Candle] = None
    swing_high: float = 0.0
    swing_low: float = 0.0
    sl_pips: float = 20.0
    entry_price: float = 0.0


@dataclass
class C17Result:
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    validation: Optional[dict] = None
    confluence: Optional[dict] = None
    entry: Optional[dict] = None
    exit_plan: Optional[dict] = None
    approved: bool = False
    stage_reached: str = "NONE"
    block_reason: str = ""

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "approved": self.approved,
            "stage": self.stage_reached,
            "block_reason": self.block_reason,
            "validation": self.validation,
            "confluence": self.confluence,
            "entry": self.entry,
            "exit_plan": self.exit_plan,
        }


class C17Optimizer:
    def __init__(self) -> None:
        self.validator = SignalValidator()
        self.confluence = ConfluenceFilter()
        self.entry_timing = EntryTiming()
        self.exit_mgr = ExitManager()

    def run(self, inp: C17Input) -> C17Result:
        result = C17Result()

        # 1 — Validation
        val = self.validator.validate(inp.signal)
        result.validation = val.as_dict()
        result.stage_reached = "VALIDATION"
        if not val.valid:
            result.block_reason = val.reason
            return result

        # 2 — Confluence
        conf = self.confluence.evaluate(inp.signal.pair, inp.signal.direction, inp.votes)
        result.confluence = conf.as_dict()
        result.stage_reached = "CONFLUENCE"
        if not conf.approved:
            result.block_reason = conf.reason
            return result

        # 3 — Entry timing
        if inp.candle and inp.swing_high and inp.swing_low:
            entry_dec = self.entry_timing.evaluate(
                inp.signal.pair, inp.signal.direction,
                inp.candle, inp.swing_high, inp.swing_low
            )
            result.entry = entry_dec.as_dict()
            result.stage_reached = "ENTRY_TIMING"
            if entry_dec.entry_type == "WAIT":
                result.block_reason = entry_dec.reason
                return result
            entry_price = entry_dec.entry_price
        else:
            entry_price = inp.entry_price
            result.stage_reached = "ENTRY_TIMING"

        # 4 — Plan de sortie
        plan = self.exit_mgr.build_plan(
            pair=inp.signal.pair,
            direction=inp.signal.direction,
            entry=entry_price,
            sl_pips=inp.sl_pips,
        )
        result.exit_plan = plan.as_dict()
        result.stage_reached = "EXIT_PLAN"
        result.approved = True
        return result

    def reset(self) -> None:
        self.validator.reset()
