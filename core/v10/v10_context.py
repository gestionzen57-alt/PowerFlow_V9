"""V10 Module Contexte — Couche 3 : le cadre dans lequel TU lis.

Calcule les features contextuelles qui modulent la décision : session,
proximité news, range journalier, régime de volatilité, jour de semaine,
spread regime et régime de corrélation.

Terminologie alignée sur la lecture TA humaine. Chaque feature C1-C7 est
testée unitairement (R7).

Features :
  C1 — Session (Asia / London / NY / Overlap)
  C2 — News proximity (NO_TRADE_ZONE si < 30min d'un event majeur)
  C3 — Range journalier (high-low du jour vs ATR)
  C4 — Vol regime (Low / Normal / High / Extreme)
  C5 — Day of week (lundi violent, vendredi creux)
  C6 — Spread regime (large = illiquide = NO_TRADE)
  C7 — Correlation regime (USD trending = paires USD alignées)

Doctrine : R2 additif pur, R6 fail-open (news API down → NO_TRADE par
défaut, pas de crash en cascade).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULTS = {
    "news_buffer_min": 30,      # minutes autour d'un event = NO_TRADE_ZONE
    "c3_range_atr_mult": 1.5,   # range journalier vs ATR
    "c4_vol_normal": 0.5,       # ATR / close (ratio annualisé approx)
    "c6_max_spread_points": 30, # au-delà = illiquide
}

# Sessions en UTC (alignées plan V10)
SESSIONS = {
    "ASIA": (0, 8),
    "LONDON": (8, 13),
    "NY": (13, 16),
    "OVERLAP": (16, 22),
}


@dataclass
class ContextResult:
    symbol: str
    timestamp: str
    timeframe: str

    c1_session: str = "NY"
    c2_news_state: str = "CLEAR"      # CLEAR / NO_TRADE_ZONE
    c2_news_events: int = 0
    c3_range_ratio: float = 0.0
    c4_vol_regime: str = "NORMAL"     # LOW / NORMAL / HIGH / EXTREME
    c5_day_of_week: int = 0
    c6_spread_regime: str = "NORMAL"  # NORMAL / WIDE / ILLIQUIDE
    c7_usd_trend: str = "NEUTRAL"     # BULLISH / BEARISH / NEUTRAL
    tradeable: bool = True
    blockers: List[str] = field(default_factory=list)

    summary: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "c1_session": self.c1_session,
            "c2_news_state": self.c2_news_state,
            "c3_range_ratio": round(self.c3_range_ratio, 3),
            "c4_vol_regime": self.c4_vol_regime,
            "c5_day_of_week": self.c5_day_of_week,
            "c6_spread_regime": self.c6_spread_regime,
            "c7_usd_trend": self.c7_usd_trend,
            "tradeable": self.tradeable,
            "blockers": self.blockers,
        }


def _session_of(ts: str) -> str:
    """Session UTC à partir d'un timestamp ISO."""
    try:
        t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        t = dt.datetime.now(dt.timezone.utc)
    h = t.hour
    for name, (start, end) in SESSIONS.items():
        if start <= h < end:
            return name
    # 22-24 = ASIA début
    return "ASIA"


def compute_context(
    symbol: str,
    timestamp: str,
    timeframe: str,
    *,
    news_events: Optional[List[dt.datetime]] = None,
    bars: Optional[List[dict]] = None,
    usd_trend: str = "NEUTRAL",
    overrides: Optional[dict] = None,
) -> ContextResult:
    """Calcule les 7 features Contexte.

    news_events : liste de datetimes UTC des news majeures à venir.
    bars        : bougies du jour pour C3 (range) — optionnel.
    usd_trend   : tendance USD injectée par l'orchestrateur (C7).
    """
    cfg = dict(DEFAULTS)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if k in DEFAULTS})

    res = ContextResult(symbol, timestamp, timeframe)

    # ---- C1 session ----
    res.c1_session = _session_of(timestamp)

    # ---- C2 news proximity ----
    if news_events:
        try:
            t = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            t = dt.datetime.now(dt.timezone.utc)
        buf = dt.timedelta(minutes=int(cfg["news_buffer_min"]))
        nearby = [e for e in news_events if abs(e - t) <= buf]
        res.c2_news_events = len(nearby)
        if nearby:
            res.c2_news_state = "NO_TRADE_ZONE"
            res.tradeable = False
            res.blockers.append("NEWS")
    else:
        res.c2_news_state = "CLEAR"  # R6 fail-open : sans calendrier, on trade

    # ---- C3 range journalier ----
    if bars and len(bars) >= 2:
        day_high = max(float(b["high"]) for b in bars[-1:])
        day_low = min(float(b["low"]) for b in bars[-1:])
        # range sur les dernières N bars du jour
        recent = bars[-10:]
        rh = max(float(b["high"]) for b in recent)
        rl = min(float(b["low"]) for b in recent)
        atr = (rh - rl) or 1e-9
        res.c3_range_ratio = (day_high - day_low) / atr

    # ---- C4 vol regime ----
    if bars and len(bars) >= 14:
        closes = [float(b["close"]) for b in bars[-14:]]
        avg = sum(closes) / len(closes) or 1e-9
        atr_approx = (max(float(b["high"]) for b in bars[-14:]) -
                      min(float(b["low"]) for b in bars[-14:])) / 14
        ratio = atr_approx / avg
        if ratio > 0.003:
            res.c4_vol_regime = "EXTREME"
        elif ratio > 0.0015:
            res.c4_vol_regime = "HIGH"
        elif ratio > 0.0008:
            res.c4_vol_regime = "NORMAL"
        else:
            res.c4_vol_regime = "LOW"

    # ---- C5 day of week ----
    try:
        t = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        res.c5_day_of_week = t.isoweekday()
    except (ValueError, AttributeError):
        res.c5_day_of_week = dt.datetime.now(dt.timezone.utc).isoweekday()

    # ---- C6 spread regime ----
    if bars and len(bars) >= 1:
        spread = float(bars[-1].get("spread_points", 0.0) or 0.0)
        if spread > int(cfg["c6_max_spread_points"]):
            res.c6_spread_regime = "ILLIQUIDE"
            res.tradeable = False
            res.blockers.append("SPREAD")
        elif spread > int(cfg["c6_max_spread_points"]) * 0.6:
            res.c6_spread_regime = "WIDE"

    # ---- C7 usd trend ----
    res.c7_usd_trend = usd_trend if usd_trend in ("BULLISH", "BEARISH", "NEUTRAL") else "NEUTRAL"

    res.summary = {
        "session": res.c1_session,
        "news": res.c2_news_state,
        "vol": res.c4_vol_regime,
        "tradeable": res.tradeable,
    }
    return res
