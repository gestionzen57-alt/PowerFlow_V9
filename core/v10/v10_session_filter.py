"""
v10_session_filter.py — CYCLE 13 : Session Filter
C13-OPT1 : Filtre les signaux hors des fenêtres de session optimales.
Doctrine : R2 additif pur | R6 fail-open | R9 audit | R10 compute-only
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from datetime import time
from typing import Any

SESSIONS: dict[str, tuple[time, time]] = {
    "tokyo":      (time(0, 0),  time(9, 0)),
    "london":     (time(7, 0),  time(16, 0)),
    "new_york":   (time(13, 0), time(22, 0)),
    "overlap_ln": (time(13, 0), time(16, 0)),
}

LIQUIDITY_SCORES: dict[str, dict[str, int]] = {
    "EURUSD":  {"tokyo": 1, "london": 3, "new_york": 3, "overlap_ln": 3},
    "GBPUSD":  {"tokyo": 1, "london": 3, "new_york": 3, "overlap_ln": 3},
    "USDJPY":  {"tokyo": 3, "london": 2, "new_york": 2, "overlap_ln": 2},
    "EURJPY":  {"tokyo": 3, "london": 2, "new_york": 1, "overlap_ln": 2},
    "XAUUSD":  {"tokyo": 1, "london": 2, "new_york": 3, "overlap_ln": 3},
    "default": {"tokyo": 1, "london": 2, "new_york": 2, "overlap_ln": 3},
}
LIQUIDITY_MIN: int = 2


@dataclass
class SessionFilterResult:
    allowed: bool = True
    active_sessions: list[str] = field(default_factory=list)
    best_session: str = "unknown"
    liquidity_score: int = 0
    block_reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "active_sessions": self.active_sessions,
                "best_session": self.best_session, "liquidity_score": self.liquidity_score,
                "block_reason": self.block_reason}


def check_session(current_utc_time: time, pair: str = "EURUSD", min_liquidity: int = LIQUIDITY_MIN) -> SessionFilterResult:
    result = SessionFilterResult()
    try:
        scores = LIQUIDITY_SCORES.get(pair.upper(), LIQUIDITY_SCORES["default"])
        active: list[str] = []
        best_score = 0
        best_sess = "none"
        for sess, (start, end) in SESSIONS.items():
            in_window = start <= current_utc_time <= end if start <= end else current_utc_time >= start or current_utc_time <= end
            if in_window:
                active.append(sess)
                s = scores.get(sess, 1)
                if s > best_score:
                    best_score = s
                    best_sess = sess
        result.active_sessions = active
        result.best_session = best_sess
        result.liquidity_score = best_score
        if best_score < min_liquidity or not active:
            result.allowed = False
            result.block_reason = f"LOW_LIQUIDITY pair={pair} score={best_score}<{min_liquidity} sessions={active or ['none']}"
    except Exception as e:
        warnings.warn(f"[C13] SessionFilter error (fail-open): {e}")
        result.allowed = True
        result.block_reason = f"ERROR_FAIL_OPEN: {e}"
    return result


# R2 additif (Mission 1 prep) : repair imports
import enum as _enum
class SessionName(str, _enum.Enum):
    TOKYO = 'tokyo'; LONDON = 'london'
    NEW_YORK = 'new_york'; OVERLAP_LN = 'overlap_ln'; UNKNOWN = 'unknown'
class SessionQuality(str, _enum.Enum):
    LOW = 'low'; MEDIUM = 'medium'; HIGH = 'high'
def get_session_quality(current_utc_time, pair='EURUSD'):
    try:
        r = check_session(current_utc_time, pair, min_liquidity=1)
        if r.liquidity_score >= 3: return SessionQuality.HIGH
        if r.liquidity_score >= 2: return SessionQuality.MEDIUM
        return SessionQuality.LOW
    except Exception:
        return SessionQuality.MEDIUM
def apply_session_to_signal(signal_level, pair, current_utc_time=None):
    out = {'level': signal_level, 'session': 'unknown', 'boost': 0.0, 'blocked': False}
    try:
        from datetime import time as _time
        ct = current_utc_time if current_utc_time is not None else _time(12, 0)
        r = check_session(ct, pair, min_liquidity=1)
        out['session'] = r.best_session
        if r.liquidity_score >= 3: out['boost'] = 0.10
        elif r.liquidity_score < 2: out['blocked'] = True
        out['audit'] = r.as_dict()
    except Exception:
        pass
    return out
