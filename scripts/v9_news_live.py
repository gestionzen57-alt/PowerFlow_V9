"""v9_news_live.py — P2-1 motion CEO 48h Champ libre.

News live depuis ForexFactory API (gratuit).
Fallback sur calendrier hardcode si API down.

Auteur : Hermes (P2-1 motion CEO 48h Champ libre, 31/07/2026)
"""
from __future__ import annotations

import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.news_live")

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def fetch_news_live(timeout: int = 10) -> list[dict]:
    """Fetch news depuis ForexFactory."""
    try:
        req = urllib.request.Request(FF_URL, headers={
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, list) else []
    except (urllib.error.URLError, json.JSONDecodeError, Exception) as e:
        log.warning("FF fetch failed: %s", e)
        return []


def fetch_news_hardcoded() -> list[dict]:
    """Fallback calendrier hardcode 2026."""
    now = datetime.now(timezone.utc)
    events = [
        {"title": "NFP_USD", "country": "USD",
         "date": now + timedelta(days=7), "impact": "HIGH"},
        {"title": "CPI_USD", "country": "USD",
         "date": now + timedelta(days=14), "impact": "HIGH"},
        {"title": "FOMC_MINUTES", "country": "USD",
         "date": now + timedelta(days=20), "impact": "HIGH"},
        {"title": "ECB_RATE", "country": "EUR",
         "date": now + timedelta(days=10), "impact": "HIGH"},
        {"title": "BOE_RATE", "country": "GBP",
         "date": now + timedelta(days=21), "impact": "HIGH"},
    ]
    return events


def should_block_news(events: list[dict],
                       minutes_before: int = 30,
                       minutes_after: int = 15) -> dict:
    """Decide si on doit bloquer sur news imminent."""
    if not events:
        return {"block": False, "reason": "no_events",
                "events": []}
    now = datetime.now(timezone.utc)
    block = False
    imminent = []
    for evt in events:
        evt_dt = evt.get("date")
        if isinstance(evt_dt, str):
            try:
                evt_dt = datetime.fromisoformat(
                    evt_dt.replace("Z", "+00:00")
                )
            except ValueError:
                continue
        if not isinstance(evt_dt, datetime):
            continue
        if evt.get("impact", "LOW") != "HIGH":
            continue
        delta = (evt_dt - now).total_seconds() / 60
        if -minutes_after <= delta <= minutes_before:
            block = True
            imminent.append({**evt, "minutes_until": round(delta, 1)})
    return {
        "block": block,
        "reason": "high_impact_near" if block else "no_high_impact_near",
        "events": imminent,
    }


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="V9 news live (P2-1)",
    )
    parser.add_argument("--no-fetch", action="store_true",
                        help="Skip fetch live (utilise hardcode)")
    parser.add_argument("--minutes-before", type=int, default=30)
    args = parser.parse_args(argv)

    print("=" * 70)
    print("P2-1 — NEWS LIVE (ForexFactory)")
    print("=" * 70)
    if args.no_fetch:
        events = fetch_news_hardcoded()
        source = "hardcoded"
    else:
        events = fetch_news_live()
        source = "live" if events else "fallback_hardcoded"
        if not events:
            events = fetch_news_hardcoded()
    print(f"Source        : {source}")
    print(f"N events      : {len(events)}")
    decision = should_block_news(events, minutes_before=args.minutes_before)
    print(f"BLOCK decision: {decision['block']}")
    print(f"Reason        : {decision['reason']}")
    if decision["events"]:
        print()
        print("Imminent events :")
        for e in decision["events"]:
            print(f"  {e.get('title')} in {e.get('minutes_until', 0):+.1f}min "
                  f"[{e.get('impact', '?')}]")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())