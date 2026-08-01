"""v9_market_microstructure.py — Phase 44 motion CEO 48h autopilote.

Analyse microstructure marche : order book imbalance + volume profile +
trade flow toxicity.

Auteur : Hermes (Phase 44 motion CEO 48h, 31/07/2026)
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

log = logging.getLogger("v9.micro")


def order_book_imbalance(bid_volume: float, ask_volume: float,
                            depth_levels: int = 5) -> dict:
    """Imbalance carnet d'ordres L5 (5 niveaux).

    Imbalance = (bid - ask) / (bid + ask) ∈ [-1, +1]
    """
    total = bid_volume + ask_volume
    if total == 0:
        return {"imbalance": 0.0, "pressure": "NEUTRAL",
                "depth_levels": depth_levels, "ratio": 0.0}
    imbalance = (bid_volume - ask_volume) / total
    ratio = bid_volume / max(ask_volume, 0.001)
    if imbalance > 0.4:
        pressure = "STRONG_BID"
    elif imbalance > 0.1:
        pressure = "MILD_BID"
    elif imbalance < -0.4:
        pressure = "STRONG_ASK"
    elif imbalance < -0.1:
        pressure = "MILD_ASK"
    else:
        pressure = "NEUTRAL"
    return {
        "imbalance": round(imbalance, 3),
        "pressure": pressure,
        "depth_levels": depth_levels,
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
        "ratio": round(ratio, 3),
    }


def volume_profile(volume_per_price: dict[str, float]) -> dict:
    """Profile de volume par prix.

    Identifie POC (Point of Control = prix avec plus de volume),
    Value Area (70% du volume).
    """
    if not volume_per_price:
        return {"poc": None, "value_area_high": None,
                "value_area_low": None, "total_volume": 0.0}
    total_volume = sum(volume_per_price.values())
    poc_price = max(volume_per_price, key=volume_per_price.get)
    # Value area : trier prix par volume desc, prendre jusqu'a 70%
    sorted_prices = sorted(volume_per_price.items(),
                             key=lambda x: x[1], reverse=True)
    cum = 0.0
    va_prices = []
    for price, vol in sorted_prices:
        va_prices.append(price)
        cum += vol
        if cum >= 0.7 * total_volume:
            break
    try:
        va_low = min(va_prices, key=lambda x: float(x))
        va_high = max(va_prices, key=lambda x: float(x))
    except ValueError:
        va_low, va_high = None, None
    return {
        "poc": poc_price,
        "value_area_low": va_low,
        "value_area_high": va_high,
        "total_volume": round(total_volume, 2),
        "n_prices": len(volume_per_price),
    }


def trade_flow_toxicity(buy_trades: int, sell_trades: int,
                          avg_buy_size: float, avg_sell_size: float) -> dict:
    """Toxicite du flux : detecte informed traders.

    Toxicity = |buy_ratio - 0.5| * 2 * size_asymmetry
    """
    total = buy_trades + sell_trades
    if total == 0:
        return {"toxicity": 0.0, "informed_side": "NEUTRAL",
                "buy_ratio": 0.5, "size_asymmetry": 0.0}
    buy_ratio = buy_trades / total
    size_total = avg_buy_size + avg_sell_size
    size_asymmetry = (avg_buy_size - avg_sell_size) / max(size_total, 0.001)
    toxicity = abs(buy_ratio - 0.5) * 2 + abs(size_asymmetry)
    toxicity = min(1.0, toxicity)
    if buy_ratio > 0.6 and size_asymmetry > 0.2:
        informed_side = "BUYERS"
    elif buy_ratio < 0.4 and size_asymmetry < -0.2:
        informed_side = "SELLERS"
    else:
        informed_side = "NEUTRAL"
    return {
        "toxicity": round(toxicity, 3),
        "informed_side": informed_side,
        "buy_ratio": round(buy_ratio, 3),
        "size_asymmetry": round(size_asymmetry, 3),
    }


def micro_alpha_signal(book_imb: dict, vol_prof: dict,
                          toxicity: dict) -> dict:
    """Combine microstructure signals en alpha final."""
    score = 0.0
    n = 0
    if book_imb.get("pressure") in ("STRONG_BID", "MILD_BID"):
        score += 0.4
        n += 1
    elif book_imb.get("pressure") in ("STRONG_ASK", "MILD_ASK"):
        score -= 0.4
        n += 1
    if toxicity.get("informed_side") == "BUYERS":
        score += 0.5
        n += 1
    elif toxicity.get("informed_side") == "SELLERS":
        score -= 0.5
        n += 1
    if vol_prof.get("poc"):
        # POC au-dessus du mid → bullish (volume sur hauts)
        try:
            mid = (float(vol_prof.get("value_area_low", 0)) +
                   float(vol_prof.get("value_area_high", 0))) / 2
            if float(vol_prof["poc"]) > mid:
                score += 0.2
                n += 1
            else:
                score -= 0.2
                n += 1
        except (ValueError, TypeError):
            pass
    final_score = score / max(n, 1)
    if final_score > 0.3:
        direction = "LONG"
    elif final_score < -0.3:
        direction = "SHORT"
    else:
        direction = "WAIT"
    return {
        "score": round(final_score, 3),
        "direction": direction,
        "n_signals": n,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 market microstructure (Phase 44)",
    )
    args = parser.parse_args(argv)

    book = order_book_imbalance(bid_volume=1500.0, ask_volume=800.0)
    vp = volume_profile({"1.2900": 100, "1.2920": 250,
                            "1.2950": 500, "1.2980": 300, "1.3000": 150})
    tox = trade_flow_toxicity(buy_trades=80, sell_trades=20,
                                avg_buy_size=1.5, avg_sell_size=1.0)
    alpha = micro_alpha_signal(book, vp, tox)

    print("=" * 70)
    print("PHASE 44 — MARKET MICROSTRUCTURE")
    print("=" * 70)
    print(f"Order book   : imbalance={book['imbalance']:+.3f}  "
          f"pressure={book['pressure']}")
    print(f"Volume prof  : POC={vp['poc']} VA=[{vp['value_area_low']}, "
          f"{vp['value_area_high']}]")
    print(f"Toxicity     : {tox['toxicity']:.3f}  "
          f"informed={tox['informed_side']}")
    print(f"Alpha        : score={alpha['score']:+.3f}  "
          f"direction={alpha['direction']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())