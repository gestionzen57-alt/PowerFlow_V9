"""
v10_signal_validator.py — Cycle 17
Validation multi-couche des signaux avant envoi au broker.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class RawSignal:
    pair: str
    direction: str
    timeframe: str
    score: float
    source: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ValidationResult:
    signal: RawSignal
    valid: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "pair": self.signal.pair,
            "direction": self.signal.direction,
            "tf": self.signal.timeframe,
            "score": self.signal.score,
            "valid": self.valid,
            "checks": self.checks,
            "reason": self.reason,
        }


class SignalValidator:
    MIN_SCORE = 60.0
    VALID_DIRECTIONS = {"BUY", "SELL"}
    VALID_TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
    DEDUP_WINDOW_SEC = 300

    def __init__(self) -> None:
        self._recent: Dict[str, str] = {}

    def validate(self, signal: RawSignal) -> ValidationResult:
        checks: Dict[str, bool] = {}
        checks["direction"] = signal.direction in self.VALID_DIRECTIONS
        checks["timeframe"] = signal.timeframe in self.VALID_TIMEFRAMES
        checks["score"] = signal.score >= self.MIN_SCORE
        checks["pair_nonempty"] = bool(signal.pair)
        key = f"{signal.pair}:{signal.direction}"
        last = self._recent.get(key)
        if last:
            try:
                from datetime import datetime as dt
                delta = (dt.fromisoformat(signal.timestamp) - dt.fromisoformat(last)).total_seconds()
                checks["dedup"] = delta > self.DEDUP_WINDOW_SEC
            except Exception:
                checks["dedup"] = True
        else:
            checks["dedup"] = True
        valid = all(checks.values())
        if valid:
            self._recent[key] = signal.timestamp
        failed = [k for k, v in checks.items() if not v]
        reason = "OK" if valid else f"FAIL: {', '.join(failed)}"
        return ValidationResult(signal=signal, valid=valid, checks=checks, reason=reason)

    def reset(self) -> None:
        self._recent.clear()
