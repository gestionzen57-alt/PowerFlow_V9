"""v9_ftmo_compliance_eur.py — Phase 76 motion CEO 48H (P2.3 audit Perplexity).

FTMO compliance en EUR (au lieu de pips) :
- daily_dd_eur = abs(sum_pips_24h) * lot_size * pip_value
- total_dd_eur = abs(sum_pips_total) * lot_size * pip_value
- Block si > 4% daily ou 8% total

Pip values standard (lot 0.01) :
- GBPUSD : 0.10 USD/pip
- EURUSD : 0.10 USD/pip
- USDJPY : 0.10 USD/pip (JPY pairs pip = 0.01)
- XAUUSD : 0.01 USD/pip (or, pip = 0.01)

Auteur : Hermes (Phase 76 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("v9.ftmo_eur")

FTMO_DAILY_DD_PCT_DEFAULT = 0.04  # 4%
FTMO_TOTAL_DD_PCT_DEFAULT = 0.08  # 8%

PIP_VALUE_PER_LOT_USD = {
    # paires standard (pip = 0.0001)
    "GBPUSD": 10.0,
    "EURUSD": 10.0,
    "AUDUSD": 10.0,
    "NZDUSD": 10.0,
    "USDCAD": 10.0,  # approx inverse quote
    "USDCHF": 10.0,
    # JPY pairs (pip = 0.01)
    "USDJPY": 10.0,
    "EURJPY": 10.0,
    "GBPJPY": 10.0,
    # Or / commodities
    "XAUUSD": 1.0,  # 0.01 move = 0.01 USD sur 0.01 lot (1 oz)
}

DEFAULT_LOT_SIZE = 0.01


def get_pip_value(symbol: str, lot_size: float = DEFAULT_LOT_SIZE) -> float:
    """Retourne la valeur en USD d'1 pip pour le symbol et lot_size."""
    base = PIP_VALUE_PER_LOT_USD.get(symbol.upper(), 10.0)
    return base * lot_size


def compute_daily_dd_eur(
    daily_pips: float,
    symbol: str = "GBPUSD",
    lot_size: float = DEFAULT_LOT_SIZE,
) -> float:
    """Daily drawdown en EUR (positif = perte)."""
    pip_value = get_pip_value(symbol, lot_size)
    return abs(daily_pips) * pip_value


def compute_total_dd_eur(
    total_pips: float,
    symbol: str = "GBPUSD",
    lot_size: float = DEFAULT_LOT_SIZE,
) -> float:
    """Total drawdown en EUR (positif = perte)."""
    pip_value = get_pip_value(symbol, lot_size)
    return abs(total_pips) * pip_value


def ftmo_compliance_check(
    capital_eur: float,
    daily_pips: float,
    total_pips: float,
    symbol: str = "GBPUSD",
    lot_size: float = DEFAULT_LOT_SIZE,
    daily_limit_pct: float = FTMO_DAILY_DD_PCT_DEFAULT,
    total_limit_pct: float = FTMO_TOTAL_DD_PCT_DEFAULT,
) -> dict[str, Any]:
    """Verdict FTMO complet en EUR.

    Retourne dict avec alertes, can_trade, daily_dd_eur, total_dd_eur.
    """
    daily_dd = compute_daily_dd_eur(daily_pips, symbol, lot_size)
    total_dd = compute_total_dd_eur(total_pips, symbol, lot_size)

    daily_alert = "OK"
    total_alert = "OK"

    if capital_eur <= 0:
        return {"error": "capital_eur <= 0"}

    daily_pct = daily_dd / capital_eur
    total_pct = total_dd / capital_eur

    if daily_pct >= daily_limit_pct:
        daily_alert = "CRITICAL"
    elif daily_pct >= daily_limit_pct * 0.5:
        daily_alert = "WARNING"

    if total_pct >= total_limit_pct:
        total_alert = "CRITICAL"
    elif total_pct >= total_limit_pct * 0.5:
        total_alert = "WARNING"

    can_trade = daily_alert != "CRITICAL" and total_alert != "CRITICAL"

    return {
        "capital_eur": capital_eur,
        "daily_dd_eur": round(daily_dd, 2),
        "total_dd_eur": round(total_dd, 2),
        "daily_dd_pct": round(daily_pct, 6),
        "total_dd_pct": round(total_pct, 6),
        "daily_alert": daily_alert,
        "total_alert": total_alert,
        "can_trade": can_trade,
        "symbol": symbol,
        "lot_size": lot_size,
    }


def recommended_sizing_reduction(
    capital_eur: float,
    daily_pips: float,
    symbol: str = "GBPUSD",
    lot_size: float = DEFAULT_LOT_SIZE,
) -> float:
    """Retourne facteur de reduction sizing (1.0 = pas de reduction)."""
    res = ftmo_compliance_check(capital_eur, daily_pips, 0.0, symbol, lot_size)
    if res.get("daily_alert") == "CRITICAL":
        return 0.0  # stop complet
    if res.get("daily_alert") == "WARNING":
        return 0.5  # demi sizing
    return 1.0


def main(argv=None) -> int:
    """Demo FTMO compliance."""
    print("=" * 70)
    print("V9 FTMO COMPLIANCE EUR (Phase 76)")
    print("=" * 70)

    # Phase 12 cible : capital 10k, mini-lot 0.01, GBPUSD
    capital = 10000.0  # 10k EUR
    daily_pips = -50.0  # perte 50 pips sur la journee
    total_pips = -120.0  # perte cumulee 120 pips

    res = ftmo_compliance_check(
        capital_eur=capital,
        daily_pips=daily_pips,
        total_pips=total_pips,
        symbol="GBPUSD",
        lot_size=0.01,
    )
    print(f"Capital         : {res['capital_eur']} EUR")
    print(f"Daily DD        : {res['daily_dd_eur']} EUR ({res['daily_dd_pct']*100:.2f}%) [{res['daily_alert']}]")
    print(f"Total DD        : {res['total_dd_eur']} EUR ({res['total_dd_pct']*100:.2f}%) [{res['total_alert']}]")
    print(f"Can trade       : {res['can_trade']}")
    print(f"Sizing reduce   : {recommended_sizing_reduction(capital, daily_pips)}x")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())