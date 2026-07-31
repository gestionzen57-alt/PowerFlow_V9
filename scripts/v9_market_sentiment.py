"""v9_market_sentiment.py — Phase 37 motion CEO 48h autopilote.

Indicateur de sentiment marche base sur distribution trades.
Trade skew haussier vs baissier, win rate directionnel.

Auteur : Hermes (Phase 37 motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.sentiment")


def get_paper_trades_directional(db_path: Path | str, days: int = 7
                                   ) -> dict:
    """Retourne le sentiment base sur trades paper recents."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {"error": "db_missing"}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("""
                SELECT
                    SUM(CASE WHEN direction = 'haussiere' AND pips_net > 0 THEN 1 ELSE 0 END) AS bull_wins,
                    SUM(CASE WHEN direction = 'haussiere' AND pips_net <= 0 THEN 1 ELSE 0 END) AS bull_losses,
                    SUM(CASE WHEN direction = 'baissiere' AND pips_net > 0 THEN 1 ELSE 0 END) AS bear_wins,
                    SUM(CASE WHEN direction = 'baissiere' AND pips_net <= 0 THEN 1 ELSE 0 END) AS bear_losses,
                    SUM(CASE WHEN direction = 'haussiere' THEN pips_net ELSE 0 END) AS bull_pips,
                    SUM(CASE WHEN direction = 'baissiere' THEN pips_net ELSE 0 END) AS bear_pips
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                  AND closed_at > REPLACE(datetime('now', ? || ' days'),
                                          ' ', 'T')
            """, (-days,)).fetchone()
            bull_wins = int(row[0] or 0)
            bull_losses = int(row[1] or 0)
            bear_wins = int(row[2] or 0)
            bear_losses = int(row[3] or 0)
            bull_pips = float(row[4] or 0)
            bear_pips = float(row[5] or 0)
            return {
                "days": days,
                "bull_wins": bull_wins,
                "bull_losses": bull_losses,
                "bear_wins": bear_wins,
                "bear_losses": bear_losses,
                "bull_pips": round(bull_pips, 2),
                "bear_pips": round(bear_pips, 2),
                "n_total": bull_wins + bull_losses + bear_wins + bear_losses,
            }
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        return {"error": str(e)}


def compute_sentiment(directional: dict) -> dict:
    """Calcule sentiment score entre -1 (bearish) et +1 (bullish)."""
    if "error" in directional or directional.get("n_total", 0) == 0:
        return {
            "sentiment": "NEUTRAL",
            "score": 0.0,
            "bias": "NEUTRAL",
            "recommendation": "WAIT_DATA",
        }
    n_total = directional["n_total"]
    bull_pips = directional["bull_pips"]
    bear_pips = directional["bear_pips"]
    total_pips = bull_pips + bear_pips
    if total_pips == 0:
        return {
            "sentiment": "NEUTRAL",
            "score": 0.0,
            "bias": "NEUTRAL",
            "recommendation": "WAIT_DATA",
        }
    # Score = (bull - bear) / total
    score = (bull_pips - bear_pips) / max(abs(total_pips), 1)
    score = max(-1.0, min(1.0, score))
    if score > 0.3:
        sentiment = "BULLISH"
        bias = "LONG"
    elif score < -0.3:
        sentiment = "BEARISH"
        bias = "SHORT"
    else:
        sentiment = "NEUTRAL"
        bias = "WAIT"
    return {
        "sentiment": sentiment,
        "score": round(score, 3),
        "bias": bias,
        "recommendation": bias,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 market sentiment (Phase 37)",
    )
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    directional = get_paper_trades_directional(DB_PATH, days=args.days)
    sentiment = compute_sentiment(directional)

    print("=" * 70)
    print("PHASE 37 — MARKET SENTIMENT")
    print("=" * 70)
    print(f"Fenetre : {args.days}j")
    if "error" in directional:
        print(f"Erreur : {directional['error']}")
        return 1
    print(f"N trades        : {directional['n_total']}")
    print(f"Bull wins/loss  : {directional['bull_wins']}/{directional['bull_losses']}")
    print(f"Bear wins/loss  : {directional['bear_wins']}/{directional['bear_losses']}")
    print(f"Bull pips       : {directional['bull_pips']:+.1f}")
    print(f"Bear pips       : {directional['bear_pips']:+.1f}")
    print()
    print(f"Sentiment       : {sentiment['sentiment']}")
    print(f"Score (-1/+1)   : {sentiment['score']}")
    print(f"Bias            : {sentiment['bias']}")
    print(f"Recommendation  : {sentiment['recommendation']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())