"""
v10_news_guard.py — CYCLE 13 : News Guard
C13-OPT2 : Bloque [-15min, +30min] autour des news HIGH/CRITICAL.
Doctrine : R2 additif pur | R6 fail-open | R9 audit | R10 compute-only
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

NEWS_PRE_WINDOW: int = 15
NEWS_POST_WINDOW: int = 30
HIGH_IMPACT_LABELS = {"HIGH", "CRITICAL", "3", "red"}


@dataclass
class NewsEvent:
    timestamp: datetime
    title: str
    impact: str
    currency: str = ""


@dataclass
class NewsGuardResult:
    allowed: bool = True
    blocked_by: str = ""
    events_checked: int = 0
    upcoming_events: list = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "blocked_by": self.blocked_by,
                "events_checked": self.events_checked, "upcoming_events": self.upcoming_events}


def check_news_window(current_time: datetime, pair: str = "EURUSD",
                     events: list[NewsEvent] | None = None,
                     pre_min: int = NEWS_PRE_WINDOW, post_min: int = NEWS_POST_WINDOW) -> NewsGuardResult:
    result = NewsGuardResult()
    if events is None:
        events = []
    currencies = {pair[:3].upper(), pair[3:6].upper()} if len(pair) >= 6 else set()
    try:
        result.events_checked = len(events)
        for ev in events:
            if ev.impact.upper() not in HIGH_IMPACT_LABELS:
                continue
            if ev.currency and ev.currency.upper() not in currencies:
                continue
            delta_min = (ev.timestamp - current_time).total_seconds() / 60
            if -post_min <= delta_min <= pre_min:
                result.allowed = False
                result.blocked_by = f"NEWS_WINDOW event='{ev.title}' t={ev.timestamp.strftime('%H:%M')} impact={ev.impact} delta={delta_min:+.0f}min"
                break
            if 0 < delta_min <= 120:
                result.upcoming_events.append({"title": ev.title, "in_min": round(delta_min), "impact": ev.impact})
    except Exception as e:
        warnings.warn(f"[C13] NewsGuard error (fail-open): {e}")
        result.allowed = True
        result.blocked_by = f"ERROR_FAIL_OPEN: {e}"
    return result
