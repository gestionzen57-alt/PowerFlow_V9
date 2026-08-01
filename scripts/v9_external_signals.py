"""v9_external_signals.py — Phase 47 motion CEO 48h autopilote.

Signaux externes : news economic calendar + COT report + market holidays.
Genere un filtre pre-trade.

Auteur : Hermes (Phase 47 motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.external")


# Calendrier economique simplifie (2026 - simplifie)
ECONOMIC_CALENDAR_2026 = [
    {"date": "2026-08-07", "time_utc": "12:30", "event": "NFP_USD",
     "impact": "HIGH"},
    {"date": "2026-08-13", "time_utc": "18:00", "event": "CPI_USD",
     "impact": "HIGH"},
    {"date": "2026-08-19", "time_utc": "18:00", "event": "FOMC_MINUTES",
     "impact": "HIGH"},
    {"date": "2026-09-04", "time_utc": "12:30", "event": "NFP_USD",
     "impact": "HIGH"},
    {"date": "2026-09-11", "time_utc": "18:00", "event": "CPI_USD",
     "impact": "HIGH"},
    {"date": "2026-09-17", "time_utc": "18:00", "event": "FOMC_RATE_DECISION",
     "impact": "HIGH"},
]


def upcoming_events(hours_ahead: int = 24) -> list[dict]:
    """Evenements a venir dans les N prochaines heures."""
    now = datetime.now(timezone.utc)
    upcoming = []
    for evt in ECONOMIC_CALENDAR_2026:
        try:
            evt_dt = datetime.fromisoformat(
                f"{evt['date']}T{evt['time_utc']}+00:00"
            )
            delta = evt_dt - now
            hours = delta.total_seconds() / 3600
            if -2 <= hours <= hours_ahead:
                upcoming.append({
                    **evt,
                    "hours_until": round(hours, 1),
                })
        except ValueError:
            continue
    return upcoming


def cot_position_signal(net_long_pct: float,
                         threshold_extreme: float = 80.0,
                         threshold_caution: float = 70.0) -> dict:
    """COT report : extreme positioning.

    Si >80% des traders sont longs → potentielle exhaustion (contrarian short).
    Si <20% → potentielle exhaustion (contrarian long).
    """
    if net_long_pct >= threshold_extreme:
        return {
            "signal": "EXTREME_LONG",
            "interpretation": "Exhaustion possible (contrarian SHORT)",
            "action": "REDUCE_LONG_BIAS",
            "score": -0.5,
        }
    elif net_long_pct <= 100 - threshold_extreme:
        return {
            "signal": "EXTREME_SHORT",
            "interpretation": "Exhaustion possible (contrarian LONG)",
            "action": "REDUCE_SHORT_BIAS",
            "score": 0.5,
        }
    elif net_long_pct >= threshold_caution:
        return {
            "signal": "BULLISH_LEAN",
            "interpretation": "Positioning bullish",
            "action": "FAVOR_LONG",
            "score": 0.2,
        }
    elif net_long_pct <= 100 - threshold_caution:
        return {
            "signal": "BEARISH_LEAN",
            "interpretation": "Positioning bearish",
            "action": "FAVOR_SHORT",
            "score": -0.2,
        }
    else:
        return {
            "signal": "NEUTRAL",
            "interpretation": "Positioning equilibre",
            "action": "NO_BIAS",
            "score": 0.0,
        }


def should_block_trade(upcoming: list[dict],
                        cot_score: float,
                        minutes_before_high_impact: int = 30,
                        minutes_after_high_impact: int = 15) -> dict:
    """Decide si on doit bloquer le trade avant/pres news majeures."""
    if not upcoming:
        return {
            "block": False,
            "reason": "no_high_impact_news",
            "events": [],
            "cot_score": cot_score,
        }
    block = False
    events = []
    reasons = []
    for evt in upcoming:
        if evt["impact"] == "HIGH":
            hours = evt["hours_until"]
            if -minutes_after_high_impact / 60 <= hours <= (
                minutes_before_high_impact / 60
            ):
                block = True
                events.append(evt)
                reasons.append(
                    f"{evt['event']} dans {hours:.1f}h (HIGH impact)"
                )
    return {
        "block": block,
        "reason": "; ".join(reasons) if reasons else "no_event_in_window",
        "events": events,
        "cot_score": cot_score,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 external signals (Phase 47)",
    )
    parser.add_argument("--hours-ahead", type=int, default=24)
    parser.add_argument("--cot-net-long", type=float, default=72.0,
                        help="% net long sur COT (50=neutre)")
    parser.add_argument("--decision", action="store_true",
                        help="Decide si bloquer trade")
    args = parser.parse_args(argv)

    upcoming = upcoming_events(args.hours_ahead)
    cot = cot_position_signal(args.cot_net_long)
    if args.decision:
        decision = should_block_trade(upcoming, cot["score"])
    else:
        decision = None

    print("=" * 70)
    print("PHASE 47 — EXTERNAL SIGNALS")
    print("=" * 70)
    print(f"Fenetre          : {args.hours_ahead}h ahead")
    print(f"COT net long     : {args.cot_net_long}%")
    print()
    print(f"COT signal       : {cot['signal']}")
    print(f"  interpret.     : {cot['interpretation']}")
    print(f"  action         : {cot['action']}")
    print(f"  score          : {cot['score']}")
    print()
    print(f"Upcoming events  : {len(upcoming)}")
    for evt in upcoming:
        print(f"  - {evt['event']:25s} in {evt['hours_until']:+.1f}h  "
              f"[{evt['impact']}]")
    if decision is not None:
        print()
        print(f"BLOCK decision   : {decision['block']}")
        print(f"  Reason         : {decision['reason']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())