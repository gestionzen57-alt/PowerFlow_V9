"""v9_sentiment_blacklister.py — Phase 40C motion CEO 48h autopilote.

Lever L15 : sentiment-based blacklister.
Si le sentiment global est BEARISH (score < -0.5), blacklist toutes
les positions LONG jusqu'a inversion du sentiment.

Auteur : Hermes (Phase 40C motion CEO 48h, 31/07/2026)
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

log = logging.getLogger("v9.sent_bl")


def get_recent_sentiment(db_path: Path | str, days: int = 7) -> dict:
    """Recupere sentiment recent (Phase 37)."""
    from scripts.v9_market_sentiment import (
        get_paper_trades_directional, compute_sentiment,
    )
    directional = get_paper_trades_directional(db_path, days=days)
    sentiment = compute_sentiment(directional)
    return {"directional": directional, "sentiment": sentiment}


def get_open_paper_trades(db_path: Path | str) -> list[dict]:
    """Retourne les paper trades ouverts (non fermes)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT id, symbol, direction, opened_at, pips_net
                FROM v9_paper_trades
                WHERE closed_at IS NULL
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def apply_l15_blacklist(db_path: Path | str,
                         sentiment_data: dict,
                         score_threshold: float = -0.5) -> dict:
    """Applique L15 : si sentiment < threshold, blacklist LONG.

    Returns : dict avec n_blacklisted + liste des trade_ids affectes.
    """
    sentiment = sentiment_data.get("sentiment", {})
    score = sentiment.get("score", 0.0)
    sentiment_label = sentiment.get("sentiment", "NEUTRAL")
    if score >= score_threshold:
        return {
            "applied": False,
            "sentiment": sentiment_label,
            "score": score,
            "n_blacklisted": 0,
            "trade_ids": [],
            "reason": f"Sentiment {sentiment_label} (score {score:.3f}) > threshold",
        }
    # Sentiment bearish → blacklist LONG
    db_path = Path(db_path)
    if not db_path.exists():
        return {
            "applied": False,
            "sentiment": sentiment_label,
            "score": score,
            "n_blacklisted": 0,
            "trade_ids": [],
            "reason": "DB missing",
        }
    open_trades = get_open_paper_trades(db_path)
    long_trades = [t for t in open_trades if t.get("direction") == "haussiere"]
    trade_ids = [t["id"] for t in long_trades]
    return {
        "applied": True,
        "sentiment": sentiment_label,
        "score": score,
        "n_blacklisted": len(trade_ids),
        "trade_ids": trade_ids,
        "reason": f"Sentiment BEARISH (score {score:.3f} < {score_threshold}) - "
                  f"{len(trade_ids)} LONG trades blacklisted",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 sentiment blacklister L15 (Phase 40C)",
    )
    parser.add_argument("--days", type=int, default=7,
                        help="Fenetre sentiment (defaut 7j)")
    parser.add_argument("--threshold", type=float, default=-0.5,
                        help="Score seuil blacklist (defaut -0.5)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    sentiment_data = get_recent_sentiment(DB_PATH, days=args.days)
    result = apply_l15_blacklist(DB_PATH, sentiment_data,
                                   score_threshold=args.threshold)

    print("=" * 70)
    print("PHASE 40C — LEVIER L15 SENTIMENT BLACKLISTER")
    print("=" * 70)
    print(f"Fenetre sentiment   : {args.days}j")
    print(f"Seuil score         : {args.threshold}")
    print()
    sentiment = sentiment_data.get("sentiment", {})
    directional = sentiment_data.get("directional", {})
    print(f"Sentiment           : {sentiment.get('sentiment', 'NEUTRAL')}")
    print(f"Score               : {sentiment.get('score', 0):.3f}")
    print(f"N trades ouverts    : {directional.get('n_total', 0)}")
    print()
    if result["applied"]:
        print(f">>> BLACKLIST APPLIED")
        print(f"    {result['n_blacklisted']} LONG trades blacklisted")
        print(f"    Reason : {result['reason']}")
    else:
        print(f">>> NO BLACKLIST")
        print(f"    Reason : {result['reason']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())