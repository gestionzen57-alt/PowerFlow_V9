"""v9_price_action_context.py — Phase 54 motion CEO no-limit.

Module de comprehension cote (price action context) :
- Structure : swing highs/lows, trendlines, S/R
- Patterns : engulfing, doji, hammer, shooting star
- S/R dynamiques : support/resistance clusters
- Contexte : location dans la range, position vs VWAP-like

Auteur : Hermes (Phase 54 motion CEO no-limit, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.price_action")


# === SWING DETECTION ===

def detect_swings(highs: list[float], lows: list[float],
                    order: int = 5) -> dict:
    """Detecte swing highs et swing lows."""
    if len(highs) < order * 2 + 1:
        return {"swing_highs": [], "swing_lows": [], "n_swings": 0}
    swing_highs = []
    swing_lows = []
    for i in range(order, len(highs) - order):
        # Swing high : max local
        if highs[i] == max(highs[i - order:i + order + 1]):
            swing_highs.append({
                "index": i,
                "price": float(highs[i]),
            })
        # Swing low : min local
        if lows[i] == min(lows[i - order:i + order + 1]):
            swing_lows.append({
                "index": i,
                "price": float(lows[i]),
            })
    return {
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "n_swings": len(swing_highs) + len(swing_lows),
    }


# === CANDLE PATTERNS ===

def detect_pattern(opens: list[float], highs: list[float],
                     lows: list[float], closes: list[float]) -> dict:
    """Detecte patterns de bougies sur la derniere bougie."""
    if not closes or len(closes) < 1:
        return {"pattern": "NONE", "reason": "no_data"}
    o = opens[-1]
    h = highs[-1]
    l = lows[-1]
    c = closes[-1]
    body = abs(c - o)
    total_range = h - l
    if total_range == 0:
        return {"pattern": "DOJI", "strength": 0.5,
                "note": "no range"}
    body_pct = body / total_range
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    # Doji : body tres petit
    if body_pct < 0.1:
        return {
            "pattern": "DOJI",
            "strength": round(1.0 - body_pct, 3),
            "note": "indecision",
        }
    # Hammer : long lower wick, small body haut
    if lower_wick > 2 * body and upper_wick < body:
        return {
            "pattern": "HAMMER",
            "strength": round(lower_wick / total_range, 3),
            "note": "bullish reversal",
        }
    # Shooting star : long upper wick, small body bas
    if upper_wick > 2 * body and lower_wick < body:
        return {
            "pattern": "SHOOTING_STAR",
            "strength": round(upper_wick / total_range, 3),
            "note": "bearish reversal",
        }
    # Bullish engulfing : vert qui avale rouge
    if len(opens) >= 2 and len(closes) >= 2:
        prev_o = opens[-2]
        prev_c = closes[-2]
        if prev_c < prev_o and c > o and c >= prev_o and o <= prev_c:
            return {
                "pattern": "BULLISH_ENGULFING",
                "strength": round(body / total_range, 3),
                "note": "bullish reversal",
            }
        if prev_c > prev_o and c < o and c <= prev_o and o >= prev_c:
            return {
                "pattern": "BEARISH_ENGULFING",
                "strength": round(body / total_range, 3),
                "note": "bearish reversal",
            }
    # Marubozu : full body no wicks
    if body_pct > 0.9:
        pattern = "MARUBOZU_BULLISH" if c > o else "MARUBOZU_BEARISH"
        return {"pattern": pattern, "strength": body_pct,
                "note": "strong momentum"}
    return {"pattern": "NONE", "body_pct": round(body_pct, 3)}


# === SUPPORT / RESISTANCE CLUSTERS ===

def find_sr_clusters(highs: list[float], lows: list[float],
                        threshold_pct: float = 0.005) -> dict:
    """Trouve les zones S/R par clustering des swings extremes."""
    if not highs or not lows:
        return {"supports": [], "resistances": []}
    # Tous les prix extremes
    extremes = sorted([float(h) for h in highs] +
                        [float(l) for l in lows])
    if not extremes:
        return {"supports": [], "resistances": []}
    min_p = min(extremes)
    max_p = max(extremes)
    if min_p == 0:
        return {"supports": [], "resistances": []}
    threshold = threshold_pct * (max_p - min_p)
    # Cluster les prix proches
    clusters = []
    current_cluster = [extremes[0]]
    for p in extremes[1:]:
        if p - current_cluster[-1] < threshold:
            current_cluster.append(p)
        else:
            if len(current_cluster) >= 3:
                clusters.append({
                    "price": round(sum(current_cluster) / len(current_cluster), 5),
                    "n_touches": len(current_cluster),
                    "type": "support_or_resistance",
                })
            current_cluster = [p]
    if len(current_cluster) >= 3:
        clusters.append({
            "price": round(sum(current_cluster) / len(current_cluster), 5),
            "n_touches": len(current_cluster),
            "type": "support_or_resistance",
        })
    # Separe supports (sous mid) et resistances (sur mid)
    mid = (min_p + max_p) / 2
    supports = [c for c in clusters if c["price"] < mid]
    resistances = [c for c in clusters if c["price"] >= mid]
    supports.sort(key=lambda c: c["price"], reverse=True)
    resistances.sort(key=lambda c: c["price"])
    return {
        "supports": supports[:3],  # top 3
        "resistances": resistances[:3],
        "n_clusters": len(clusters),
    }


# === CONTEXT SUMMARY ===

def price_action_context(symbol: str, db_path: Path,
                            tf: str = "D") -> dict:
    """Contexte price action complet pour un symbole/TF."""
    if not db_path.exists():
        return {"error": "db_missing"}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(f"""
                SELECT open, high, low, close
                FROM candles_{tf.lower()}
                WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT 100
            """, (symbol,)).fetchall()
            if not rows:
                return {"symbol": symbol, "tf": tf, "error": "no_candles"}
            opens = [float(r[0]) for r in rows]
            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]
            closes = [float(r[3]) for r in rows]
            # Reverse (DESC -> ASC)
            opens.reverse()
            highs.reverse()
            lows.reverse()
            closes.reverse()
            swings = detect_swings(highs, lows)
            pattern = detect_pattern(opens, highs, lows, closes)
            sr = find_sr_clusters(highs, lows)
            last_close = closes[-1]
            # Position vs S/R
            nearest_sup = sr["supports"][0]["price"] if sr["supports"] else None
            nearest_res = sr["resistances"][0]["price"] if sr["resistances"] else None
            return {
                "symbol": symbol,
                "tf": tf,
                "n_candles": len(closes),
                "last_close": round(last_close, 5),
                "pattern": pattern,
                "swings": {
                    "n_highs": len(swings["swing_highs"]),
                    "n_lows": len(swings["swing_lows"]),
                    "n_total": swings["n_swings"],
                },
                "support_resistance": {
                    "n_supports": len(sr["supports"]),
                    "n_resistances": len(sr["resistances"]),
                    "nearest_support": nearest_sup,
                    "nearest_resistance": nearest_res,
                },
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return {"symbol": symbol, "tf": tf, "error": "db_error"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 price action context (Phase 54)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--tf", default="D")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    result = price_action_context(args.symbol, Path(DB_PATH), tf=args.tf)

    print("=" * 70)
    print(f"PHASE 54 — PRICE ACTION CONTEXT ({args.symbol}, {args.tf})")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    print(f"N candles       : {result['n_candles']}")
    print(f"Last close      : {result['last_close']}")
    print()
    print(f"Pattern         : {result['pattern'].get('pattern', 'NONE')}")
    if "note" in result["pattern"]:
        print(f"  Note          : {result['pattern']['note']}")
    print()
    print(f"Swings          : {result['swings']['n_highs']} highs, "
          f"{result['swings']['n_lows']} lows")
    print()
    print("S/R :")
    print(f"  Supports      : {result['support_resistance']['n_supports']}")
    if result['support_resistance']['nearest_support']:
        print(f"    Nearest     : {result['support_resistance']['nearest_support']}")
    print(f"  Resistances   : {result['support_resistance']['n_resistances']}")
    if result['support_resistance']['nearest_resistance']:
        print(f"    Nearest     : {result['support_resistance']['nearest_resistance']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())