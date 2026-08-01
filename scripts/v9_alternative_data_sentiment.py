"""v9_alternative_data_sentiment.py — Phase 95 motion CEO 48H (Plan C).

Alternative data sentiment : agrège sentiment depuis Twitter/Reddit/News.
Lexique-based (pas de LLM reel, R18 compliant).

Auteur : Hermes (Phase 95 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("v9.alt_data")

# Lexique sentiment (simple)
BULLISH_WORDS = {
    "bullish", "rally", "breakout", "strong", "buy", "long",
    "up", "rise", "gain", "win", "boom", "surge", "high",
    "rallying", "moon", "soar", "recover",
}
BEARISH_WORDS = {
    "bearish", "selloff", "sell", "short", "down", "fall",
    "drop", "loss", "crash", "weak", "panic", "low", "tumble",
    "dive", "collapse", "decline",
}

BULLISH_THRESHOLD = 0.3
BEARISH_THRESHOLD = -0.3


def clean_text(text: str) -> str:
    """Nettoie le texte : lowercase, retire punctuation."""
    text = text.lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_sentiment_score(texts: list[str]) -> float:
    """Calcule un score sentiment -1..1 base sur le lexique."""
    if not texts:
        return 0.0
    scores = []
    for text in texts:
        cleaned = clean_text(text)
        words = set(cleaned.split())
        n_bullish = len(words & BULLISH_WORDS)
        n_bearish = len(words & BEARISH_WORDS)
        total = n_bullish + n_bearish
        if total == 0:
            scores.append(0.0)
        else:
            scores.append((n_bullish - n_bearish) / total)
    avg = sum(scores) / len(scores)
    # Bounded
    return max(-1.0, min(1.0, avg))


def label_sentiment(score: float) -> str:
    """Label le score en BULLISH / NEUTRAL / BEARISH."""
    if score >= BULLISH_THRESHOLD:
        return "BULLISH"
    if score <= BEARISH_THRESHOLD:
        return "BEARISH"
    return "NEUTRAL"


def aggregate_sources(sources: dict[str, float]) -> dict[str, Any]:
    """Agrege les sentiments de plusieurs sources."""
    if not sources:
        return {"average": 0.0, "consensus": "NEUTRAL", "n_sources": 0}
    scores = list(sources.values())
    avg = sum(scores) / len(scores)
    return {
        "average": round(avg, 3),
        "consensus": label_sentiment(avg),
        "n_sources": len(sources),
        "per_source": {k: round(v, 3) for k, v in sources.items()},
    }


def main(argv=None) -> int:
    """Demo alternative data sentiment."""
    print("=" * 70)
    print("V9 ALTERNATIVE DATA SENTIMENT (Phase 95)")
    print("=" * 70)
    texts = [
        "GBPUSD bullish breakout strong rally",
        "EURUSD weak bearish selloff",
        "USDJPY neutral stable",
        "Market panic selloff crash",
    ]
    score = compute_sentiment_score(texts)
    label = label_sentiment(score)
    print(f"Score      : {score:+.3f}")
    print(f"Label      : {label}")
    # Aggregation
    sources = {
        "twitter": compute_sentiment_score(
            ["GBPUSD breakout bullish strong"]),
        "reddit": compute_sentiment_score(
            ["EURUSD weak bearish selloff"]),
        "news": compute_sentiment_score(
            ["Markets stable neutral calm"]),
    }
    agg = aggregate_sources(sources)
    print(f"\nSources ({agg['n_sources']}) :")
    for src, s in agg["per_source"].items():
        print(f"  {src:10s} : {s:+.3f}")
    print(f"\nConsensus : {agg['consensus']} (avg={agg['average']:+.3f})")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())