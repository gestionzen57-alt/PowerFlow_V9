"""v9_multi_timeframe_reader.py — Phase 50 motion CEO no-limit.

Lecteur multi-timeframe structure : daily → H4 → H1 → M15 → M5 → M1.
Chaque TF a sa logique propre, le systeme fait la confluence.

Auteur : Hermes (Phase 50 motion CEO no-limit, 31/07/2026)
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

log = logging.getLogger("v9.mtf")


# === TF LEVELS ===

TF_LEVELS = ["D", "H4", "H1", "M15", "M5", "M1"]


def read_timeframe(symbol: str, tf: str, db_path: Path) -> dict:
    """Lit les bougies d'un timeframe depuis la DB.

    Retourne : trend, structure, key_levels, momentum, regime_phase.
    """
    if not db_path.exists():
        return {"error": "db_missing", "tf": tf}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            # Lit les 100 dernieres bougies du TF
            rows = conn.execute(f"""
                SELECT open, high, low, close, volume
                FROM candles_{tf.lower()}
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 100
            """, (symbol,)).fetchall()
            if not rows:
                return {
                    "tf": tf, "symbol": symbol, "n_candles": 0,
                    "trend": "UNKNOWN", "structure": "UNKNOWN",
                    "momentum": 0.0, "regime_phase": "UNKNOWN",
                    "key_levels": {"high": None, "low": None},
                    "anticipation": "NO_DATA",
                    "slope": 0.0, "range_pct": 0.0,
                }
            closes = [float(r[3]) for r in rows]
            highs = [float(r[1]) for r in rows]
            lows = [float(r[2]) for r in rows]
            return _analyze_timeframe(symbol, tf, closes, highs, lows)
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        # Fallback : mode degrade (DB sans candles)
        return _analyze_timeframe(symbol, tf, [], [], [])


def _analyze_timeframe(symbol: str, tf: str, closes: list[float],
                        highs: list[float], lows: list[float]) -> dict:
    """Analyse un timeframe."""
    if not closes or len(closes) < 2:
        return {
            "tf": tf, "symbol": symbol, "n_candles": len(closes),
            "trend": "UNKNOWN", "structure": "UNKNOWN",
            "momentum": 0.0, "regime_phase": "UNKNOWN",
            "key_levels": {"high": None, "low": None},
            "anticipation": "NO_DATA",
        }
    # Trend : pente sur 20 dernieres bougies
    if len(closes) >= 20:
        recent = closes[-20:]
        slope = (recent[-1] - recent[0]) / recent[0] if recent[0] != 0 else 0
    else:
        slope = (closes[-1] - closes[0]) / closes[0] if closes[0] != 0 else 0
    if slope > 0.005:
        trend = "UPTREND"
    elif slope < -0.005:
        trend = "DOWNTREND"
    else:
        trend = "RANGING"
    # Structure : swing high/low
    recent_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    recent_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)
    range_pct = (recent_high - recent_low) / recent_low if recent_low != 0 else 0
    if range_pct > 0.02:
        structure = "VOLATILE_RANGE"
    elif range_pct > 0.005:
        structure = "TIGHT_RANGE"
    else:
        structure = "CONSOLIDATION"
    # Momentum : diff entre derniers 5 vs premiers 5
    if len(closes) >= 10:
        first_5 = sum(closes[-10:-5]) / 5
        last_5 = sum(closes[-5:]) / 5
        momentum = (last_5 - first_5) / first_5 if first_5 != 0 else 0
    else:
        momentum = 0.0
    # Regime phase : cycle de Wyck simplifie
    last_close = closes[-1]
    if trend == "UPTREND" and last_close > recent_high * 0.95:
        regime_phase = "MARKUP"
    elif trend == "DOWNTREND" and last_close < recent_low * 1.05:
        regime_phase = "MARKDOWN"
    elif slope > 0.001 and structure == "TIGHT_RANGE":
        regime_phase = "ACCUMULATION"
    elif slope < -0.001 and structure == "TIGHT_RANGE":
        regime_phase = "DISTRIBUTION"
    else:
        regime_phase = "NEUTRAL"
    # Anticipation selon TF
    anticipation = _anticipate_next(tf, trend, regime_phase, momentum)
    return {
        "tf": tf, "symbol": symbol, "n_candles": len(closes),
        "trend": trend, "structure": structure,
        "momentum": round(momentum, 4),
        "regime_phase": regime_phase,
        "slope": round(slope, 4),
        "range_pct": round(range_pct, 4),
        "key_levels": {
            "high": round(recent_high, 5),
            "low": round(recent_low, 5),
            "close": round(last_close, 5),
        },
        "anticipation": anticipation,
    }


def _anticipate_next(tf: str, trend: str, regime_phase: str,
                       momentum: float) -> str:
    """Anticipe le mouvement du TF superieur."""
    anticipation_map = {
        ("UPTREND", "MARKUP"): "CONTINUATION_LIKELY",
        ("UPTREND", "ACCUMULATION"): "BREAKOUT_PENDING",
        ("DOWNTREND", "MARKDOWN"): "CONTINUATION_LIKELY",
        ("DOWNTREND", "DISTRIBUTION"): "BREAKDOWN_PENDING",
        ("RANGING", "ACCUMULATION"): "BULLISH_BREAKOUT",
        ("RANGING", "DISTRIBUTION"): "BEARISH_BREAKDOWN",
        ("RANGING", "NEUTRAL"): "CONTINUE_RANGE",
    }
    return anticipation_map.get((trend, regime_phase), "UNKNOWN")


def confluence_score(tf_readings: list[dict]) -> dict:
    """Score de confluence inter-TF (0-100)."""
    if not tf_readings:
        return {"score": 0, "alignment": "NO_DATA",
                "n_aligned": 0, "n_total": 0, "dominant": "NO_DATA"}
    trends = [r["trend"] for r in tf_readings if r.get("trend") != "UNKNOWN"]
    if not trends:
        return {"score": 0, "alignment": "NO_DATA",
                "n_aligned": 0, "n_total": len(tf_readings),
                "dominant": "NO_DATA"}
    # Compte le trend dominant
    n_up = sum(1 for t in trends if t == "UPTREND")
    n_down = sum(1 for t in trends if t == "DOWNTREND")
    n_range = sum(1 for t in trends if t == "RANGING")
    n_total = len(trends)
    if n_up / n_total >= 0.7:
        dominant = "UPTREND"
        n_aligned = n_up
    elif n_down / n_total >= 0.7:
        dominant = "DOWNTREND"
        n_aligned = n_down
    else:
        dominant = "MIXED"
        n_aligned = max(n_up, n_down, n_range)
    score = round(100 * n_aligned / n_total, 1)
    alignment = "STRONG" if score >= 80 else (
        "MODERATE" if score >= 60 else "WEAK"
    )
    return {"score": score, "alignment": alignment,
            "dominant": dominant, "n_aligned": n_aligned,
            "n_total": n_total}


def multi_tf_analysis(symbol: str, db_path: Path) -> dict:
    """Pipeline complet multi-TF."""
    readings = []
    for tf in TF_LEVELS:
        r = read_timeframe(symbol, tf, db_path)
        readings.append(r)
    confluence = confluence_score(readings)
    return {
        "symbol": symbol,
        "ts": datetime.now(timezone.utc).isoformat(),
        "tf_readings": readings,
        "confluence": confluence,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 multi-timeframe reader (Phase 50)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    result = multi_tf_analysis(args.symbol, Path(DB_PATH))

    print("=" * 70)
    print(f"PHASE 50 — MULTI-TIMEFRAME READER ({args.symbol})")
    print("=" * 70)
    print()
    for r in result["tf_readings"]:
        print(f"  [{r['tf']:3s}] trend={r['trend']:9s} "
              f"phase={r['regime_phase']:14s} "
              f"mom={r['momentum']:+.4f}  "
              f"anticip={r['anticipation']}")
    print()
    print(f"CONFLUENCE : {result['confluence']['score']}/100  "
          f"alignment={result['confluence']['alignment']}  "
          f"dominant={result['confluence']['dominant']}")
    print(f"Aligned    : {result['confluence']['n_aligned']}/"
          f"{result['confluence']['n_total']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())