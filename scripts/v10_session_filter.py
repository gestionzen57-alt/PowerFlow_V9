#!/usr/bin/env python3
"""
v10_session_filter.py — Filtre ICT Kill Zone pour signaux V10
Sprint 24 — Perplexity GitHub MCP — 2026-08-08 20:51 CEST

Fonction principale : is_in_kill_zone(pair, dt_utc)
Retourne True si l'heure est dans une Kill Zone ICT active pour la paire.
Permet d'exclure les sessions OUTSIDE à faible WR.

Kill Zones ICT :
  LONDON_OPEN  : 07:00-09:00 UTC
  NY_OPEN      : 12:00-14:00 UTC
  LONDON_CLOSE : 15:00-16:00 UTC
  ASIAN        : 00:00-04:00 UTC (JPY pairs priority)

Doctrine : R1-AGIR, R6 fail-open, R9-AUDIT, R10-CAPITAL
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

# Kill Zones par session (heure UTC, inclusive start, exclusive end)
KILL_ZONES: dict[str, list[tuple[int, int]]] = {
    "DEFAULT": [
        (7, 9),    # London Open
        (12, 14),  # NY Open
        (15, 16),  # London Close
    ],
    "JPY": [
        (0, 4),    # Asian KZ (JPY priority)
        (7, 9),    # London Open
        (12, 14),  # NY Open
    ],
}

JPY_PAIRS = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "NZDJPY", "CADJPY", "CHFJPY"}


def get_kill_zones(pair: str) -> list[tuple[int, int]]:
    if pair.upper() in JPY_PAIRS:
        return KILL_ZONES["JPY"]
    return KILL_ZONES["DEFAULT"]


def is_in_kill_zone(pair: str, dt_utc: Optional[datetime] = None) -> bool:
    """True si l'heure UTC est dans une Kill Zone active pour la paire."""
    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)
    hour = dt_utc.hour
    for start, end in get_kill_zones(pair):
        if start <= hour < end:
            return True
    return False


def filter_signals(signals: list[dict]) -> list[dict]:
    """Filtre une liste de signaux, garde uniquement ceux en Kill Zone.
    Chaque signal doit avoir 'pair' et optionnellement 'timestamp_utc'.
    """
    now = datetime.now(timezone.utc)
    kept = []
    for sig in signals:
        pair = sig.get("pair", "")
        ts_raw = sig.get("timestamp_utc")
        if ts_raw:
            try:
                dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except Exception:
                dt = now
        else:
            dt = now
        if is_in_kill_zone(pair, dt):
            kept.append(sig)
    return kept


if __name__ == "__main__":
    import json
    now = datetime.now(timezone.utc)
    test_pairs = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD"]
    result = {
        p: {
            "now_utc": now.strftime("%H:%M"),
            "in_kill_zone": is_in_kill_zone(p, now),
            "kill_zones": get_kill_zones(p),
        }
        for p in test_pairs
    }
    print(json.dumps(result, indent=2))
