"""v9_order_flow_institution.py — P2-4 motion CEO 48h Champ libre.

Order flow institution detection :
- Iceberg orders (split pattern)
- Stop hunts (liquidity grab)
- Accumulation institutionnelle
- Order book pressure

Auteur : Hermes (P2-4 motion CEO 48h Champ libre, 31/07/2026)
"""
from __future__ import annotations

import logging
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.order_flow")


def detect_iceberg_orders(trades: list[dict],
                            min_splits: int = 3,
                            price_tolerance: float = 0.0001) -> dict:
    """Detecte iceberg orders (split pattern)."""
    if not trades:
        return {"error": "no_data"}
    # Groupe par (prix approx, side)
    groups = defaultdict(list)
    for t in trades:
        key = (round(t["price"] / price_tolerance) * price_tolerance,
                t.get("side", "?"))
        groups[key].append(t)
    icebergs = []
    for (price, side), group_trades in groups.items():
        if len(group_trades) >= min_splits:
            sizes = [t["size"] for t in group_trades]
            # Uniform sizes = icebergs
            avg_size = sum(sizes) / len(sizes)
            if max(sizes) - min(sizes) <= 0.1 * avg_size:
                icebergs.append({
                    "price": price,
                    "side": side,
                    "n_splits": len(group_trades),
                    "avg_size": round(avg_size, 2),
                    "total_size": round(sum(sizes), 2),
                })
    return {
        "icebergs_detected": len(icebergs),
        "icebergs": icebergs,
    }


def detect_stop_hunt(prices: list[float],
                      spike_threshold: float = 0.005) -> dict:
    """Detecte stop hunt (spike rapide puis retour)."""
    if len(prices) < 4:
        return {"hunt_detected": False, "reason": "insufficient_data"}
    # Cherche spike > threshold suivi d'un retour
    for i in range(2, len(prices) - 1):
        prev_close = prices[i - 1]
        spike = prices[i]
        next_close = prices[i + 1]
        spike_pct = abs(spike - prev_close) / prev_close
        if spike_pct > spike_threshold:
            # Spike detecte, verifier retour
            return_pct = abs(next_close - spike) / spike
            if return_pct > 0.5 * spike_pct:
                direction = "HUNT_LONG" if spike > prev_close else "HUNT_SHORT"
                return {
                    "hunt_detected": True,
                    "direction": direction,
                    "spike_price": spike,
                    "return_price": next_close,
                    "spike_pct": round(spike_pct, 4),
                }
    return {"hunt_detected": False}


def detect_accumulation(trades: list[dict],
                          price_range_pct: float = 0.005) -> dict:
    """Detecte accumulation : prix stable + gros volume."""
    if not trades:
        return {"accumulation_score": 0.0, "reason": "no_data"}
    prices = [t["price"] for t in trades]
    sizes = [t["size"] for t in trades]
    if not prices:
        return {"accumulation_score": 0.0, "reason": "no_prices"}
    min_p, max_p = min(prices), max(prices)
    if min_p == 0:
        return {"accumulation_score": 0.0}
    range_pct = (max_p - min_p) / min_p
    total_volume = sum(sizes)
    avg_size = total_volume / len(sizes)
    # Score : price range tight + gros volume
    if range_pct > price_range_pct:
        return {
            "accumulation_score": 0.0,
            "reason": "price_range_too_wide",
            "range_pct": round(range_pct, 4),
        }
    score = min(1.0, total_volume / (avg_size * 50))
    return {
        "accumulation_score": round(score, 3),
        "n_trades": len(trades),
        "price_range_pct": round(range_pct, 4),
        "total_volume": total_volume,
        "interpretation": "ACCUMULATION" if score > 0.5 else "NORMAL",
    }


def order_book_pressure(bid_volume: float, ask_volume: float) -> dict:
    """Score de pression order book."""
    total = bid_volume + ask_volume
    if total == 0:
        return {"pressure": "NEUTRAL", "imbalance": 0.0, "ratio": 0.0}
    imbalance = (bid_volume - ask_volume) / total
    ratio = bid_volume / max(ask_volume, 0.001)
    if imbalance > 0.3:
        pressure = "STRONG_BID"
    elif imbalance < -0.3:
        pressure = "STRONG_ASK"
    elif imbalance > 0.1:
        pressure = "MILD_BID"
    elif imbalance < -0.1:
        pressure = "MILD_ASK"
    else:
        pressure = "NEUTRAL"
    return {
        "pressure": pressure,
        "imbalance": round(imbalance, 3),
        "ratio": round(ratio, 3),
        "bid_volume": bid_volume,
        "ask_volume": ask_volume,
    }


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="V9 order flow institution (P2-4)",
    )
    parser.add_argument("--mode", default="demo")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("P2-4 — ORDER FLOW INSTITUTION")
    print("=" * 70)
    # Demo
    trades_demo = [
        {"price": 1.3000 + i * 0.00001, "size": 1.0, "side": "BUY"}
        for i in range(5)
    ]
    iceberg = detect_iceberg_orders(trades_demo)
    print(f"Iceberg      : {iceberg['icebergs_detected']} detectes")
    prices_demo = [1.30, 1.31, 1.33, 1.30, 1.31]
    hunt = detect_stop_hunt(prices_demo)
    print(f"Stop hunt    : {hunt.get('hunt_detected', False)}")
    accum = detect_accumulation(trades_demo)
    print(f"Accumulation : {accum.get('accumulation_score', 0):.2f}")
    pressure = order_book_pressure(800, 300)
    print(f"OB pressure  : {pressure['pressure']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())