"""v9_market_anticipation.py — Phase 52 motion CEO no-limit.

Anticipation des forces du marche depuis la lecture actuelle.
Detecte : regime_phase (Wyckoff simplifie) + momentum_divergence +
forward_projection (H+1, H+4, D+1, W+1).

Auteur : Hermes (Phase 52 motion CEO no-limit, 31/07/2026)
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

log = logging.getLogger("v9.anticipation")


# === REGIME PHASE DETECTOR ===

REGIME_PHASES = ["ACCUMULATION", "MARKUP", "DISTRIBUTION", "MARKDOWN"]


def detect_regime_phase(symbol: str, db_path: Path) -> dict:
    """Detecte la phase de regime actuelle (Wyckoff simplifie).

    Logique :
    - ACCUMULATION : range serre + volume croissant + prix stable
    - MARKUP : tendance haussiere + volume croissant + prix > range haut
    - DISTRIBUTION : range serre + volume eleve + prix stable haut
    - MARKDOWN : tendance baissiere + prix < range bas
    """
    if not db_path.exists():
        return {"error": "db_missing", "symbol": symbol,
                "phase": "UNKNOWN"}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("""
                SELECT
                    MIN(low) AS low_30,
                    MAX(high) AS high_30,
                    AVG(close) AS avg_close,
                    AVG(volume) AS avg_vol,
                    COUNT(*) AS n_candles,
                    (SELECT close FROM candles_d
                     WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1) AS last_close
                FROM candles_d
                WHERE symbol = ?
                  AND timestamp > datetime('now', '-30 days')
            """, (symbol, symbol)).fetchone()
            if not row or row[4] == 0:
                return {"symbol": symbol, "phase": "UNKNOWN",
                        "n_candles": 0}
            low_30 = float(row[0] or 0)
            high_30 = float(row[1] or 0)
            avg_close = float(row[2] or 0)
            avg_vol = float(row[3] or 0)
            last_close = float(row[5] or 0)
            range_30 = high_30 - low_30
            if avg_close == 0 or range_30 == 0:
                return {"symbol": symbol, "phase": "UNKNOWN",
                        "reason": "zero_data"}
            # Position dans le range
            position_in_range = (last_close - low_30) / range_30
            # Range tightness (range / avg_close)
            range_tightness = range_30 / avg_close
            if range_tightness < 0.005 and position_in_range < 0.5:
                phase = "ACCUMULATION"
            elif position_in_range > 0.95:
                phase = "DISTRIBUTION"
            elif position_in_range > 0.6 and range_tightness > 0.01:
                phase = "MARKUP"
            elif position_in_range < 0.4 and range_tightness > 0.01:
                phase = "MARKDOWN"
            else:
                phase = "NEUTRAL"
            return {
                "symbol": symbol,
                "phase": phase,
                "position_in_range": round(position_in_range, 3),
                "range_tightness": round(range_tightness, 4),
                "low_30": round(low_30, 5),
                "high_30": round(high_30, 5),
                "last_close": round(last_close, 5),
                "n_candles": int(row[4]),
            }
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return {"symbol": symbol, "phase": "UNKNOWN",
                "error": "db_error"}


# === MOMENTUM DIVERGENCE ===

def momentum_divergence(closes: list[float],
                          volumes: Optional[list[float]] = None) -> dict:
    """Detecte divergence prix vs momentum.

    Bullish divergence : prix fait bas plus bas mais momentum non.
    Bearish divergence : prix fait haut plus haut mais momentum non.
    """
    if len(closes) < 10:
        return {"divergence": "NONE", "reason": "insufficient_data"}
    # Split en 2 moities
    mid = len(closes) // 2
    first_half = closes[:mid]
    second_half = closes[mid:]
    first_low = min(first_half)
    second_low = min(second_half)
    first_high = max(first_half)
    second_high = max(second_half)
    # Momentum = diff between 5-day close vs 5-day close ago
    if len(closes) >= 10:
        momentum_first = (sum(first_half[-5:]) / 5 -
                            sum(first_half[:5]) / 5)
        momentum_second = (sum(second_half[-5:]) / 5 -
                              sum(second_half[:5]) / 5)
    else:
        momentum_first = momentum_second = 0.0
    # Divergence bearish (hauts plus hauts, momentum baisse)
    if second_high > first_high and momentum_second < momentum_first:
        return {
            "divergence": "BEARISH",
            "price_high_first": round(first_high, 5),
            "price_high_second": round(second_high, 5),
            "momentum_first": round(momentum_first, 4),
            "momentum_second": round(momentum_second, 4),
        }
    # Divergence bullish (bas plus bas, momentum hausse)
    if second_low < first_low and momentum_second > momentum_first:
        return {
            "divergence": "BULLISH",
            "price_low_first": round(first_low, 5),
            "price_low_second": round(second_low, 5),
            "momentum_first": round(momentum_first, 4),
            "momentum_second": round(momentum_second, 4),
        }
    return {"divergence": "NONE"}


# === FORWARD PROJECTION ===

def forward_projection(closes: list[float],
                          horizon: str = "H+1") -> dict:
    """Projection forward basee sur la tendance recente.

    H+1 : prochaine bougie (meme TF)
    H+4 : 4 bougies ahead
    D+1 : prochaine daily close
    W+1 : prochaine weekly close
    """
    if not closes or len(closes) < 5:
        return {"error": "insufficient_data"}
    last = closes[-1]
    # Trend = linear regression slope sur 20 dernieres
    n = min(20, len(closes))
    recent = closes[-n:]
    mean_y = sum(recent) / n
    mean_x = sum(range(n)) / n
    cov = sum((i - mean_x) * (c - mean_y) for i, c in enumerate(recent))
    var_x = sum((i - mean_x) ** 2 for i in range(n))
    slope = cov / var_x if var_x != 0 else 0
    intercept = mean_y - slope * mean_x
    # Projection
    if horizon == "H+1":
        x = n  # next candle
    elif horizon == "H+4":
        x = n + 4
    elif horizon == "D+1":
        x = n + 20  # ~20 H1 bougies = 1 daily
    elif horizon == "W+1":
        x = n + 100  # ~100 H1 bougies = 1 weekly
    else:
        x = n + 1
    projected = slope * x + intercept
    delta = projected - last
    delta_pct = (delta / last * 100) if last != 0 else 0
    confidence = min(1.0, n / 20.0)
    direction = "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT"
    return {
        "horizon": horizon,
        "current": round(last, 5),
        "projected": round(projected, 5),
        "delta": round(delta, 5),
        "delta_pct": round(delta_pct, 3),
        "direction": direction,
        "confidence": round(confidence, 2),
        "slope": round(slope, 6),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 market anticipation (Phase 52)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--horizon", default="H+1",
                        choices=["H+1", "H+4", "D+1", "W+1"])
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    print("=" * 70)
    print(f"PHASE 52 — MARKET ANTICIPATION ({args.symbol})")
    print("=" * 70)
    # Regime phase
    phase = detect_regime_phase(args.symbol, Path(DB_PATH))
    print(f"\nRegime phase : {phase.get('phase', 'UNKNOWN')}")
    if "position_in_range" in phase:
        print(f"Position     : {phase['position_in_range']:.1%} of range")
    # Forward projection
    closes = []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute("""
                SELECT close FROM candles_d
                WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT 30
            """, (args.symbol,)).fetchall()
            closes = [float(r[0]) for r in rows]
            closes.reverse()  # ordre ASC
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass
    proj = forward_projection(closes, horizon=args.horizon)
    print(f"\nProjection {args.horizon} :")
    if "error" not in proj:
        print(f"  Current   : {proj['current']}")
        print(f"  Projected : {proj['projected']}")
        print(f"  Delta     : {proj['delta']} ({proj['delta_pct']:+.2f}%)")
        print(f"  Direction : {proj['direction']}")
        print(f"  Confidence: {proj['confidence']}")
    # Divergence
    div = momentum_divergence(closes)
    print(f"\nDivergence : {div.get('divergence', 'NONE')}")
    if "momentum_first" in div:
        print(f"  Momentum1 : {div['momentum_first']}")
        print(f"  Momentum2 : {div['momentum_second']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())