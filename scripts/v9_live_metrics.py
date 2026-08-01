"""v9_live_metrics.py — Phase 66 motion CEO 48H.

Live metrics dashboard : P&L unrealized + Greeks + trade flow.
Updates last 1s via poll.

Auteur : Hermes (Phase 66 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.live_metrics")


def compute_unrealized_pnl(positions: list[dict], prices: dict) -> dict:
    """P&L unrealized = (current - entry) * size * side."""
    total_pnl = 0.0
    detail = []
    for pos in positions:
        sym = pos["symbol"]
        direction = pos.get("direction", "LONG")
        entry = pos["entry"]
        size = pos["size"]
        current = prices.get(sym, entry)
        if direction == "LONG":
            pnl = (current - entry) * size * 10000  # en pips
        else:
            pnl = (entry - current) * size * 10000
        total_pnl += pnl
        detail.append({
            "symbol": sym,
            "direction": direction,
            "entry": entry,
            "current": current,
            "size": size,
            "pnl_pips": round(pnl, 2),
        })
    return {
        "total_pnl_pips": round(total_pnl, 2),
        "n_positions": len(positions),
        "detail": detail,
    }


def compute_greeks_delta(positions: list[dict],
                           prices: dict) -> dict:
    """Delta simplifié : somme des sizes LONG - SHORT."""
    delta_long = sum(p["size"] for p in positions
                      if p.get("direction", "LONG") == "LONG")
    delta_short = sum(p["size"] for p in positions
                       if p.get("direction") == "SHORT")
    return {
        "delta_long": delta_long,
        "delta_short": delta_short,
        "net_delta": delta_long - delta_short,
    }


def compute_trade_flow(last_trades: list[dict]) -> dict:
    """Trade flow : volume par direction."""
    if not last_trades:
        return {"buy_volume": 0, "sell_volume": 0, "n_trades": 0}
    buy_vol = sum(t["volume"] for t in last_trades
                    if t.get("side") == "BUY")
    sell_vol = sum(t["volume"] for t in last_trades
                     if t.get("side") == "SELL")
    return {
        "buy_volume": round(buy_vol, 2),
        "sell_volume": round(sell_vol, 2),
        "n_trades": len(last_trades),
        "buy_pct": round(buy_vol / (buy_vol + sell_vol) * 100, 1)
            if (buy_vol + sell_vol) > 0 else 0.0,
    }


def live_metrics(positions: list[dict], prices: dict,
                  last_trades: list[dict] = None) -> dict:
    """Pipeline complet live metrics."""
    pnl = compute_unrealized_pnl(positions, prices)
    greeks = compute_greeks_delta(positions, prices)
    flow = compute_trade_flow(last_trades or [])
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pnl": pnl,
        "greeks": greeks,
        "flow": flow,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 live metrics (Phase 66)",
    )
    parser.add_argument("--demo", action="store_true",
                        help="Demo positions")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("V9 LIVE METRICS")
    print("=" * 70)
    if args.demo:
        positions = [
            {"symbol": "GBPUSD", "direction": "LONG",
             "entry": 1.3000, "size": 0.5},
            {"symbol": "EURUSD", "direction": "SHORT",
             "entry": 1.0850, "size": 0.3},
        ]
        prices = {"GBPUSD": 1.3025, "EURUSD": 1.0840}
        last_trades = [
            {"side": "BUY", "volume": 100},
            {"side": "BUY", "volume": 50},
            {"side": "SELL", "volume": 75},
        ]
    else:
        positions = []
        prices = {}
        last_trades = []
    metrics = live_metrics(positions, prices, last_trades)
    print(f"TS              : {metrics['ts'][:19]}")
    print(f"Total PnL (pips): {metrics['pnl']['total_pnl_pips']:+.2f}")
    print(f"N positions     : {metrics['pnl']['n_positions']}")
    print(f"Net delta       : {metrics['greeks']['net_delta']}")
    print(f"Buy vol         : {metrics['flow']['buy_volume']}")
    print(f"Sell vol        : {metrics['flow']['sell_volume']}")
    print(f"Buy %           : {metrics['flow']['buy_pct']}%")
    print()
    for d in metrics['pnl']['detail']:
        print(f"  {d['symbol']} {d['direction']:5s} "
              f"entry={d['entry']} current={d['current']} "
              f"pnl={d['pnl_pips']:+.2f}p")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())
