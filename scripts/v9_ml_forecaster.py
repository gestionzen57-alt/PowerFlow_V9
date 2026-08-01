"""v9_ml_forecaster.py — Phase 67 motion CEO 48H.

ML forecaster : features techniques + scoring basé sur règles.
Fallback si pas de sklearn.

Auteur : Hermes (Phase 67 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.ml_forecaster")


def compute_features(closes: list[float]) -> dict:
    """Calcule features techniques sur N closes."""
    if len(closes) < 20:
        return {"error": "insufficient_data"}
    n = len(closes)
    # SMA
    sma_5 = sum(closes[-5:]) / 5
    sma_20 = sum(closes[-20:]) / 20
    # RSI simplifié (14 p)
    gains = 0.0
    losses = 0.0
    for i in range(1, min(15, n)):
        diff = closes[-i] - closes[-i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if gains + losses == 0:
        rsi = 50.0
    else:
        rs = gains / max(losses, 0.0001)
        rsi = 100 - (100 / (1 + rs))
    # MACD
    ema_12 = closes[-1]
    ema_26 = closes[-1]
    ema_12 = sum(closes[-12:]) / 12  # approx
    ema_26 = sum(closes[-26:]) / 26
    macd = ema_12 - ema_26
    # Bollinger
    std = (sum((c - sma_20) ** 2 for c in closes[-20:]) / 20) ** 0.5
    bb_upper = sma_20 + 2 * std
    bb_lower = sma_20 - 2 * std
    # Momentum
    momentum = (closes[-1] - closes[-5]) / closes[-5] * 10000
    return {
        "sma_5": round(sma_5, 5),
        "sma_20": round(sma_20, 5),
        "rsi": round(rsi, 2),
        "macd": round(macd, 5),
        "bb_upper": round(bb_upper, 5),
        "bb_lower": round(bb_lower, 5),
        "momentum_pips": round(momentum, 2),
        "current": closes[-1],
    }


def score_signal(features: dict) -> dict:
    """Score 0-100 base sur features."""
    if "error" in features:
        return {"score": 0, "signal": "NO_DATA"}
    score = 50.0
    reasons = []
    # RSI
    rsi = features["rsi"]
    if rsi < 30:
        score += 20
        reasons.append("RSI oversold->LONG bias")
    elif rsi > 70:
        score -= 20
        reasons.append("RSI overbought->SHORT bias")
    # SMA cross
    if features["sma_5"] > features["sma_20"]:
        score += 10
        reasons.append("SMA5 > SMA20 (uptrend)")
    elif features["sma_5"] < features["sma_20"]:
        score -= 10
        reasons.append("SMA5 < SMA20 (downtrend)")
    # MACD
    if features["macd"] > 0:
        score += 10
        reasons.append("MACD bullish")
    elif features["macd"] < 0:
        score -= 10
        reasons.append("MACD bearish")
    # Bollinger
    current = features["current"]
    if current < features["bb_lower"]:
        score += 10
        reasons.append("Price below BB lower")
    elif current > features["bb_upper"]:
        score -= 10
        reasons.append("Price above BB upper")
    # Momentum
    momentum = features["momentum_pips"]
    if momentum > 50:
        score += 5
        reasons.append("Strong upward momentum")
    elif momentum < -50:
        score -= 5
        reasons.append("Strong downward momentum")
    score = max(0, min(100, score))
    if score >= 70:
        signal = "STRONG_LONG"
    elif score >= 55:
        signal = "LONG"
    elif score >= 45:
        signal = "NEUTRAL"
    elif score >= 30:
        signal = "SHORT"
    else:
        signal = "STRONG_SHORT"
    return {
        "score": round(score, 1),
        "signal": signal,
        "reasons": reasons,
    }


def forecast(closes: list[float]) -> dict:
    """Forecast base sur features + score."""
    features = compute_features(closes)
    if "error" in features:
        return {"error": "insufficient_data"}
    score = score_signal(features)
    return {
        "features": features,
        "score": score,
        "ts": features.get("current"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 ML forecaster (Phase 67)",
    )
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("V9 ML FORECASTER")
    print("=" * 70)
    if args.demo:
        closes = [1.30 + i * 0.001 + (i % 5) * 0.0005 for i in range(40)]
    else:
        closes = []
    if not closes:
        print("No data")
        return 1
    result = forecast(closes)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    print(f"Current       : {result['features']['current']}")
    print(f"SMA 5         : {result['features']['sma_5']}")
    print(f"SMA 20        : {result['features']['sma_20']}")
    print(f"RSI           : {result['features']['rsi']}")
    print(f"MACD          : {result['features']['macd']}")
    print(f"Momentum pips : {result['features']['momentum_pips']}")
    print()
    print(f"Score         : {result['score']['score']}")
    print(f"Signal        : {result['score']['signal']}")
    print()
    print("Reasons :")
    for r in result['score']['reasons']:
        print(f"  - {r}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())
