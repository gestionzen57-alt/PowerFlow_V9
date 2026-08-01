"""v9_price_action_ensemble.py — P1-2 motion CEO 48h Champ libre.

Integre price action (L16/L17) dans le strategy_ensemble.
L16 : pattern sur Daily (DOJI/HAMMER/etc.)
L17 : pattern sur H4 (ENGULFING)

Auteur : Hermes (P1-2 motion CEO 48h Champ libre, 31/07/2026)
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.pa_ensemble")


def _load_candles(db_path: Path, symbol: str, tf: str,
                    limit: int = 5) -> tuple[list, list, list, list]:
    """Charge les N dernieres bougies d'un TF."""
    if not db_path.exists():
        return [], [], [], []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(f"""
                SELECT open, high, low, close FROM candles_{tf.lower()}
                WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT ?
            """, (symbol, limit)).fetchall()
            opens = [float(r[0]) for r in rows][::-1]
            highs = [float(r[1]) for r in rows][::-1]
            lows = [float(r[2]) for r in rows][::-1]
            closes = [float(r[3]) for r in rows][::-1]
            return opens, highs, lows, closes
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return [], [], [], []


def lever_signal_l16(symbol: str, db_path: Path) -> dict:
    """L16 : pattern price action Daily."""
    o, h, l, c = _load_candles(db_path, symbol, "D", 5)
    if not o:
        return {"vote": 0, "weight": 0.5, "label": "L16_no_data"}
    from scripts.v9_price_action_context import detect_pattern
    pattern = detect_pattern(o, h, l, c)
    p = pattern.get("pattern", "NONE")
    if p in ("HAMMER", "BULLISH_ENGULFING"):
        return {"vote": 1, "weight": 1.3, "label": f"L16_{p}"}
    if p in ("SHOOTING_STAR", "BEARISH_ENGULFING"):
        return {"vote": -1, "weight": 1.3, "label": f"L16_{p}"}
    if p == "MARUBOZU_BULLISH":
        return {"vote": 1, "weight": 0.8, "label": "L16_MARUBOZU_BULLISH"}
    if p == "MARUBOZU_BEARISH":
        return {"vote": -1, "weight": 0.8, "label": "L16_MARUBOZU_BEARISH"}
    return {"vote": 0, "weight": 0.5, "label": "L16_NEUTRAL"}


def lever_signal_l17(symbol: str, db_path: Path) -> dict:
    """L17 : pattern price action H4."""
    o, h, l, c = _load_candles(db_path, symbol, "H4", 5)
    if not o:
        return {"vote": 0, "weight": 0.5, "label": "L17_no_data"}
    from scripts.v9_price_action_context import detect_pattern
    pattern = detect_pattern(o, h, l, c)
    p = pattern.get("pattern", "NONE")
    if p in ("BULLISH_ENGULFING", "HAMMER"):
        return {"vote": 1, "weight": 1.5, "label": f"L17_{p}"}
    if p in ("BEARISH_ENGULFING", "SHOOTING_STAR"):
        return {"vote": -1, "weight": 1.5, "label": f"L17_{p}"}
    return {"vote": 0, "weight": 0.5, "label": "L17_NEUTRAL"}


def compute_enhanced_ensemble(symbol: str, hour: int, weekday: int,
                                regime: str, sentiment_score: float,
                                db_path: Path) -> dict:
    """Ensemble avec L1-L15 + L16 + L17."""
    from scripts.v9_strategy_ensemble import compute_ensemble
    base = compute_ensemble(symbol, hour, weekday, regime, sentiment_score)
    # Ajoute L16 + L17
    extra = [
        lever_signal_l16(symbol, db_path),
        lever_signal_l17(symbol, db_path),
    ]
    all_signals = base["signals"] + extra
    weighted_sum = sum(s["vote"] * s["weight"] for s in all_signals)
    total_weight = sum(s["weight"] for s in all_signals)
    score = weighted_sum / max(total_weight, 0.001)
    n_positive = sum(1 for s in all_signals if s["vote"] > 0)
    n_negative = sum(1 for s in all_signals if s["vote"] < 0)
    n_neutral = sum(1 for s in all_signals if s["vote"] == 0)
    if score > 0.3 and n_positive > n_negative:
        decision = "TAKE_LONG"
    elif score < -0.3 and n_negative > n_positive:
        decision = "TAKE_SHORT"
    elif score < -0.1:
        decision = "BLOCK"
    else:
        decision = "WAIT"
    confidence = min(1.0, abs(score))
    return {
        "score": round(score, 3),
        "decision": decision,
        "confidence": round(confidence, 3),
        "n_positive": n_positive,
        "n_negative": n_negative,
        "n_neutral": n_neutral,
        "n_leviers": len(all_signals),
        "signals": all_signals,
    }


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="V9 enhanced ensemble (P1-2)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--hour", type=int, default=12)
    parser.add_argument("--weekday", type=int, default=4)
    parser.add_argument("--regime", default="FAVORABLE")
    parser.add_argument("--sentiment", type=float, default=0.0)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    result = compute_enhanced_ensemble(
        args.symbol, args.hour, args.weekday,
        args.regime, args.sentiment, Path(DB_PATH),
    )

    print("=" * 70)
    print(f"P1-2 — ENHANCED ENSEMBLE ({args.symbol})")
    print("=" * 70)
    print(f"Score        : {result['score']:+.3f}")
    print(f"Decision     : {result['decision']}")
    print(f"Confidence   : {result['confidence']:.3f}")
    print(f"Leviers      : {result['n_leviers']}")
    print(f"Positive     : {result['n_positive']}")
    print(f"Negative     : {result['n_negative']}")
    print(f"Neutral      : {result['n_neutral']}")
    print()
    print("Signaux (8 leviers) :")
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