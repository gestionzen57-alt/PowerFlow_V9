"""v9_ftmo_compliance.py — Phase 63 motion CEO 48H.

FTMO compliance : daily DD 4% + total DD 8% + auto-reduce sizing.
Integration avec dispatcher Telegram.

Auteur : Hermes (Phase 63 motion CEO 48H non-stop, 31/07/2026)
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

log = logging.getLogger("v9.ftmo")

FTMO_LIMITS = {
    "daily_dd_pct": 4.0,
    "total_dd_pct": 8.0,
    "warning_daily_dd_pct": 2.0,
    "warning_total_dd_pct": 5.0,
}


def compute_pnl_from_trades(trades_pips: list[float]) -> float:
    """Somme des pnl en pips."""
    return sum(trades_pips)


def check_daily_dd(daily_pnl_negative: float, capital: float) -> dict:
    """Verifie daily DD vs FTMO 4% limit."""
    dd_pct = (abs(daily_pnl_negative) / capital * 100
                if capital > 0 else 0.0)
    if dd_pct >= FTMO_LIMITS["daily_dd_pct"]:
        alert = "CRITICAL"
    elif dd_pct >= FTMO_LIMITS["warning_daily_dd_pct"]:
        alert = "WARNING"
    else:
        alert = "OK"
    return {
        "dd_pct": round(dd_pct, 3),
        "limit_pct": FTMO_LIMITS["daily_dd_pct"],
        "alert": alert,
        "block": alert == "CRITICAL",
    }


def compute_total_dd(peak_pnl: float, capital: float) -> dict:
    """Verifie total DD vs FTMO 8% limit."""
    dd_pct = (abs(peak_pnl) / capital * 100 if capital > 0 else 0.0)
    if dd_pct >= FTMO_LIMITS["total_dd_pct"]:
        alert = "CRITICAL"
    elif dd_pct >= FTMO_LIMITS["warning_total_dd_pct"]:
        alert = "WARNING"
    else:
        alert = "OK"
    return {
        "dd_pct": round(dd_pct, 3),
        "limit_pct": FTMO_LIMITS["total_dd_pct"],
        "alert": alert,
        "block": alert == "CRITICAL",
    }


def compute_sizing(capital: float, tp: float, sl: float,
                     daily_dd_pct: float = 0.0,
                     base_lot: float = 0.01) -> dict:
    """Calcule sizing avec reduction selon DD.
    base_lot : taille mini (0.01 FTMO).
    """
    if daily_dd_pct >= FTMO_LIMITS["daily_dd_pct"]:
        return {"lot_size": 0.0, "reduction_pct": 100.0,
                "reason": "daily_dd_critical"}
    if daily_dd_pct >= FTMO_LIMITS["warning_daily_dd_pct"]:
        # Reduce 50%
        reduction = 0.5
    elif daily_dd_pct >= 1.0:
        reduction = 0.75
    else:
        reduction = 1.0
    # Sizing base : risk per trade = 1% capital
    if sl <= 0:
        return {"lot_size": base_lot, "reduction_pct": 0.0}
    risk_per_trade = capital * 0.01
    pip_value = 10.0  # standard $10/pip pour 1 lot
    if pip_value == 0:
        return {"lot_size": base_lot, "reduction_pct": 0.0}
    lot_size = risk_per_trade / (sl * pip_value)
    lot_size = max(base_lot, lot_size * reduction)
    return {
        "lot_size": round(lot_size, 2),
        "reduction_pct": round((1 - reduction) * 100, 1),
        "risk_per_trade": risk_per_trade,
    }


def ftmo_status(capital: float, daily_pnl: float, peak_pnl: float) -> dict:
    """Status FTMO complet."""
    daily = check_daily_dd(min(daily_pnl, 0), capital)
    total = compute_total_dd(min(peak_pnl, 0), capital)
    can_trade = not (daily["block"] or total["block"])
    return {
        "can_trade": can_trade,
        "daily": daily,
        "total": total,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 FTMO compliance (Phase 63)",
    )
    parser.add_argument("--capital", type=float, required=True)
    parser.add_argument("--pnl", type=float, default=0.0,
                        help="Daily PnL (negative = loss)")
    parser.add_argument("--peak", type=float, default=0.0,
                        help="Peak equity drawdown")
    parser.add_argument("--tp", type=float, default=25.0)
    parser.add_argument("--sl", type=float, default=8.0)
    args = parser.parse_args(argv)

    status = ftmo_status(args.capital, args.pnl, args.peak)
    sizing = compute_sizing(args.capital, args.tp, args.sl,
                              daily_dd_pct=status["daily"]["dd_pct"])

    print("=" * 70)
    print("V9 FTMO COMPLIANCE")
    print("=" * 70)
    print(f"Capital         : ${args.capital:,.2f}")
    print(f"Daily PnL       : ${args.pnl:,.2f}")
    print(f"Peak DD         : ${args.peak:,.2f}")
    print()
    print(f"Daily DD        : {status['daily']['dd_pct']}% / "
          f"{status['daily']['limit_pct']}%  [{status['daily']['alert']}]")
    print(f"Total DD        : {status['total']['dd_pct']}% / "
          f"{status['total']['limit_pct']}%  [{status['total']['alert']}]")
    print()
    print(f"Can trade       : {status['can_trade']}")
    print(f"Lot size        : {sizing['lot_size']}")
    print(f"Reduction       : {sizing['reduction_pct']}%")
    if not status["can_trade"]:
        print()
        print("!!! TRADE BLOCKED !!!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())