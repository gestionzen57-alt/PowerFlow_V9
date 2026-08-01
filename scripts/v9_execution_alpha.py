"""v9_execution_alpha.py — Phase 42 motion CEO 48h autopilote.

Execution alpha : modele de slippage en fonction de :
- Volume (lots)
- Volatilite (ATR-like)
- Spread courant
- Heure (sessions)
- News proximity

Auteur : Hermes (Phase 42 motion CEO 48h, 31/07/2026)
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

log = logging.getLogger("v9.exec")


def estimate_slippage_pips(lot_size: float, spread_pips: float,
                              volatility_atr: float,
                              session: str = "london_ny",
                              news_within_min: int = 60) -> dict:
    """Estime le slippage en pips selon conditions d'execution.

    Formule simplifiee :
    slippage = base + volume_factor * vol + spread * 0.5 + news_penalty
    """
    base_slippage = 0.3  # pips
    volume_factor = max(0.0, (lot_size - 0.5) * 0.2)  # +0.2p/lot > 0.5
    vol_factor = volatility_atr * 0.05  # 5% de l'ATR
    spread_contrib = spread_pips * 0.3
    news_penalty = 1.5 if news_within_min <= 15 else (
        0.8 if news_within_min <= 60 else 0.0
    )
    session_factor = {
        "london_ny": 0.0,
        "asia": 0.2,
        "off_hours": 0.5,
    }.get(session, 0.3)
    total = (base_slippage + volume_factor + vol_factor +
               spread_contrib + news_penalty + session_factor)
    return {
        "slippage_pips": round(total, 3),
        "base": base_slippage,
        "volume_factor": round(volume_factor, 3),
        "vol_factor": round(vol_factor, 3),
        "spread_contrib": round(spread_contrib, 3),
        "news_penalty": news_penalty,
        "session_factor": session_factor,
    }


def estimate_latency_ms(mt4_ping_ms: float = 50,
                          broker_load_pct: float = 30.0,
                          news_proximity: bool = False) -> dict:
    """Estime la latence en millisecondes."""
    base = 5.0  # ms
    ping = mt4_ping_ms * 0.5
    load_factor = broker_load_pct * 0.2
    news_add = 50.0 if news_proximity else 0.0
    total = base + ping + load_factor + news_add
    return {
        "latency_ms": round(total, 2),
        "base_ms": base,
        "ping_contrib_ms": round(ping, 2),
        "load_factor_ms": round(load_factor, 2),
        "news_add_ms": news_add,
    }


def order_flow_imbalance(buy_volume: float, sell_volume: float) -> dict:
    """Calcule l'imbalance order flow.

    I = (buy - sell) / (buy + sell) ∈ [-1, +1]
    > 0.3 = buy pressure
    < -0.3 = sell pressure
    """
    total = buy_volume + sell_volume
    if total == 0:
        return {"imbalance": 0.0, "pressure": "NEUTRAL", "ratio": 0.0}
    imbalance = (buy_volume - sell_volume) / total
    ratio = buy_volume / max(sell_volume, 0.001)
    if imbalance > 0.3:
        pressure = "BUY_PRESSURE"
    elif imbalance < -0.3:
        pressure = "SELL_PRESSURE"
    else:
        pressure = "NEUTRAL"
    return {
        "imbalance": round(imbalance, 3),
        "pressure": pressure,
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "ratio": round(ratio, 3),
    }


def execution_quality_score(slippage_pips: float, latency_ms: float,
                              spread_pips: float,
                              target_tp_pips: float = 25.0) -> dict:
    """Score de qualite d'execution 0-100.

    Penalties : slippage (high = bad), latency (high = bad), spread (high = bad).
    """
    slip_cost_pct = slippage_pips / target_tp_pips * 100  # 1% = 0.25p/25p
    lat_cost_pct = max(0.0, (latency_ms - 50) / 100 * 100)
    spread_cost_pct = spread_pips / target_tp_pips * 100
    total_cost_pct = slip_cost_pct + lat_cost_pct + spread_cost_pct
    quality = max(0.0, 100.0 - total_cost_pct)
    grade = (
        "A+" if quality >= 95 else
        "A" if quality >= 90 else
        "B" if quality >= 80 else
        "C" if quality >= 70 else
        "D" if quality >= 60 else "F"
    )
    return {
        "quality_score": round(quality, 1),
        "grade": grade,
        "slip_cost_pct": round(slip_cost_pct, 2),
        "lat_cost_pct": round(lat_cost_pct, 2),
        "spread_cost_pct": round(spread_cost_pct, 2),
        "total_cost_pct": round(total_cost_pct, 2),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 execution alpha (Phase 42)",
    )
    parser.add_argument("--lot", type=float, default=0.5)
    parser.add_argument("--spread", type=float, default=1.2)
    parser.add_argument("--atr", type=float, default=10.0)
    parser.add_argument("--session", default="london_ny")
    parser.add_argument("--news-min", type=int, default=120,
                        help="Prochaine news en minutes")
    parser.add_argument("--ping", type=float, default=50.0)
    args = parser.parse_args(argv)

    slip = estimate_slippage_pips(
        args.lot, args.spread, args.atr, args.session, args.news_min,
    )
    lat = estimate_latency_ms(args.ping)
    ofi = order_flow_imbalance(buy_volume=1200.0, sell_volume=800.0)
    eqs = execution_quality_score(
        slip["slippage_pips"], lat["latency_ms"], args.spread,
    )

    print("=" * 70)
    print("PHASE 42 — EXECUTION ALPHA")
    print("=" * 70)
    print(f"Slippage           : {slip['slippage_pips']:.2f} pips")
    print(f"  - base           : {slip['base']:.2f}")
    print(f"  - volume factor  : {slip['volume_factor']:.2f}")
    print(f"  - vol factor     : {slip['vol_factor']:.2f}")
    print(f"  - spread contrib : {slip['spread_contrib']:.2f}")
    print(f"  - news penalty   : {slip['news_penalty']:.2f}")
    print(f"  - session factor : {slip['session_factor']:.2f}")
    print()
    print(f"Latency            : {lat['latency_ms']:.2f} ms")
    print()
    print(f"Order Flow Imbalance:")
    print(f"  - imbalance      : {ofi['imbalance']:+.3f}")
    print(f"  - pressure       : {ofi['pressure']}")
    print(f"  - ratio          : {ofi['ratio']:.2f}")
    print()
    print(f"Execution Quality:")
    print(f"  - score          : {eqs['quality_score']}/100")
    print(f"  - grade          : {eqs['grade']}")
    print(f"  - total cost     : {eqs['total_cost_pct']:.2f}%")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())