"""v9_strategy_ensemble.py — Phase 43 motion CEO 48h autopilote.

Ensemble de strategies : vote multi-leviers pour decision finale.
Combine L1-L15 avec vote majoritaire + meta-strategy.

Auteur : Hermes (Phase 43 motion CEO 48h, 31/07/2026)
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

log = logging.getLogger("v9.ensemble")


# === LEVIER SIGNAL MOCKS (simplifie, SQL aggregate) ===

def _lever_signal_l1(symbol: str, hour: int) -> dict:
    """L1 : GBPUSD haussiere 11-13h UTC."""
    if symbol == "GBPUSD" and 11 <= hour <= 13:
        return {"vote": 1, "weight": 1.5, "label": "L1_mega_edge"}
    return {"vote": 0, "weight": 0.5, "label": "L1_neutral"}


def _lever_signal_l2(hour: int) -> dict:
    """L2 : Kill hour 0-9h UTC."""
    if 0 <= hour <= 9:
        return {"vote": -1, "weight": 2.0, "label": "L2_kill_hour"}
    return {"vote": 0, "weight": 0.5, "label": "L2_safe"}


def _lever_signal_l7(symbol: str) -> dict:
    """L7 : Blacklist 5 paires."""
    blacklist = {"USDCAD", "AUDUSD", "USDJPY", "EURUSD", "USDCHF"}
    if symbol in blacklist:
        return {"vote": -1, "weight": 2.0, "label": "L7_blacklist"}
    return {"vote": 0, "weight": 0.5, "label": "L7_allowed"}


def _lever_signal_l8(regime: str) -> dict:
    """L8 : Regime NEUTRE blacklist."""
    if regime == "NEUTRE":
        return {"vote": -1, "weight": 1.8, "label": "L8_neutral_blacklist"}
    return {"vote": 1, "weight": 1.0, "label": "L8_regime_ok"}


def _lever_signal_l14(weekday: int) -> dict:
    """L14 : Jour mardi blacklist, vendredi boost."""
    # weekday: 0=lundi, 1=mardi, 4=vendredi
    if weekday == 1:
        return {"vote": -1, "weight": 2.5, "label": "L14_mardi_blacklist"}
    if weekday == 4:
        return {"vote": 1, "weight": 2.0, "label": "L14_vendredi_mega"}
    return {"vote": 0, "weight": 0.5, "label": "L14_neutral"}


def _lever_signal_l15(score: float) -> dict:
    """L15 : Sentiment-based blacklister."""
    if score < -0.5:
        return {"vote": -1, "weight": 1.5, "label": "L15_bearish_blacklist"}
    if score > 0.5:
        return {"vote": 1, "weight": 1.2, "label": "L15_bullish"}
    return {"vote": 0, "weight": 0.5, "label": "L15_neutral"}


# === ENSEMBLE ===

def compute_ensemble(symbol: str, hour: int, weekday: int,
                       regime: str, sentiment_score: float) -> dict:
    """Vote multi-leviers (L1, L2, L7, L8, L14, L15)."""
    signals = [
        _lever_signal_l1(symbol, hour),
        _lever_signal_l2(hour),
        _lever_signal_l7(symbol),
        _lever_signal_l8(regime),
        _lever_signal_l14(weekday),
        _lever_signal_l15(sentiment_score),
    ]
    weighted_sum = sum(s["vote"] * s["weight"] for s in signals)
    total_weight = sum(s["weight"] for s in signals)
    score = weighted_sum / max(total_weight, 0.001)
    n_positive = sum(1 for s in signals if s["vote"] > 0)
    n_negative = sum(1 for s in signals if s["vote"] < 0)
    n_neutral = sum(1 for s in signals if s["vote"] == 0)
    # Decision
    if score > 0.3 and n_positive > n_negative:
        decision = "TAKE_LONG"
    elif score < -0.3 and n_negative > n_positive:
        decision = "TAKE_SHORT"
    elif score < -0.1:
        decision = "BLOCK"
    else:
        decision = "WAIT"
    # Confidence
    confidence = min(1.0, abs(score))
    return {
        "score": round(score, 3),
        "decision": decision,
        "confidence": round(confidence, 3),
        "n_positive": n_positive,
        "n_negative": n_negative,
        "n_neutral": n_neutral,
        "signals": signals,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 strategy ensemble (Phase 43)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--hour", type=int, default=12)
    parser.add_argument("--weekday", type=int, default=4)
    parser.add_argument("--regime", default="FAVORABLE")
    parser.add_argument("--sentiment", type=float, default=0.0)
    args = parser.parse_args(argv)

    result = compute_ensemble(
        args.symbol, args.hour, args.weekday, args.regime, args.sentiment,
    )

    print("=" * 70)
    print("PHASE 43 — STRATEGY ENSEMBLE")
    print("=" * 70)
    print(f"Symbol     : {args.symbol}")
    print(f"Hour UTC   : {args.hour}")
    print(f"Weekday    : {args.weekday}")
    print(f"Regime     : {args.regime}")
    print(f"Sentiment  : {args.sentiment}")
    print()
    print(f"Score        : {result['score']:+.3f}")
    print(f"Decision     : {result['decision']}")
    print(f"Confidence   : {result['confidence']:.3f}")
    print(f"Positive     : {result['n_positive']}")
    print(f"Negative     : {result['n_negative']}")
    print(f"Neutral      : {result['n_neutral']}")
    print()
    print("Signaux :")
    for s in result["signals"]:
        sign = "+" if s["vote"] > 0 else ("-" if s["vote"] < 0 else "o")
        print(f"  [{sign}] {s['label']:30s}  weight={s['weight']:.1f}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())