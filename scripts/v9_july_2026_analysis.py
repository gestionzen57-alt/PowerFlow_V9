"""v9_july_2026_analysis.py — Phase 51 motion CEO no-limit.

Analyse spécifique de la cloture juillet 2026 (W30-W31).
Comprendre la dynamique comportementale du mois qui vient de finir.

Auteur : Hermes (Phase 51 motion CEO no-limit, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.july")


# Symboles a analyser
SYMBOLS = ["GBPUSD", "EURUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF",
            "NZDUSD", "EURJPY", "GBPJPY"]


def get_july_summary(db_path: Path, symbol: str) -> dict:
    """Resume juillet 2026 pour un symbole."""
    if not db_path.exists():
        return {"error": "db_missing"}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("""
                SELECT
                    MIN(low) AS low_month,
                    MAX(high) AS high_month,
                    AVG((high + low) / 2) AS mid_avg,
                    AVG((high - low)) AS range_avg,
                    COUNT(*) AS n_candles
                FROM candles_d
                WHERE symbol = ?
                  AND timestamp >= '2026-07-01'
                  AND timestamp < '2026-08-01'
            """, (symbol,)).fetchone()
            return {
                "symbol": symbol,
                "low_month": round(float(row[0] or 0), 5),
                "high_month": round(float(row[1] or 0), 5),
                "mid_avg": round(float(row[2] or 0), 5),
                "range_avg": round(float(row[3] or 0), 5),
                "n_candles": int(row[4] or 0),
            }
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return {"symbol": symbol, "error": "no_candles_table"}


def weekly_breakdown(db_path: Path, symbol: str) -> list[dict]:
    """Decomposition par semaine (W27/W28/W29/W30/W31)."""
    weeks = [
        ("W27", "2026-07-06", "2026-07-12"),
        ("W28", "2026-07-13", "2026-07-19"),
        ("W29", "2026-07-20", "2026-07-26"),
        ("W30", "2026-07-27", "2026-08-02"),  # W30 = cloture
    ]
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        results = []
        try:
            for week_name, start, end in weeks:
                row = conn.execute("""
                    SELECT
                        MIN(low) AS w_low,
                        MAX(high) AS w_high,
                        (SELECT close FROM candles_d
                         WHERE symbol = ? AND timestamp >= ?
                         ORDER BY timestamp ASC LIMIT 1) AS w_open,
                        (SELECT close FROM candles_d
                         WHERE symbol = ? AND timestamp < ?
                         ORDER BY timestamp DESC LIMIT 1) AS w_close
                    FROM candles_d
                    WHERE symbol = ?
                      AND timestamp >= ? AND timestamp < ?
                """, (symbol, start, symbol, end, symbol, start, end)).fetchone()
                w_open = float(row[2] or 0)
                w_close = float(row[3] or 0)
                w_low = float(row[0] or 0)
                w_high = float(row[1] or 0)
                perf_pct = ((w_close - w_open) / w_open * 100
                              if w_open > 0 else 0.0)
                results.append({
                    "week": week_name,
                    "start": start,
                    "end": end,
                    "open": round(w_open, 5),
                    "close": round(w_close, 5),
                    "low": round(w_low, 5),
                    "high": round(w_high, 5),
                    "perf_pct": round(perf_pct, 3),
                    "direction": ("UP" if perf_pct > 0.1 else
                                    "DOWN" if perf_pct < -0.1 else "FLAT"),
                })
        finally:
            conn.close()
        return results
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def monthly_behavior(db_path: Path) -> dict:
    """Comportement global du mois juillet 2026."""
    symbols_data = []
    for symbol in SYMBOLS:
        summary = get_july_summary(db_path, symbol)
        if "error" not in summary:
            symbols_data.append(summary)
    # Tri par range (volatilite)
    symbols_data.sort(key=lambda s: s.get("range_avg", 0), reverse=True)
    return {
        "month": "2026-07",
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_symbols": len(symbols_data),
        "symbols": symbols_data,
        "most_volatile": symbols_data[0] if symbols_data else None,
    }


def july_weekly_summary(db_path: Path, symbol: str) -> dict:
    """Resume hebdomadaire d'un symbole en juillet 2026."""
    weeks = weekly_breakdown(db_path, symbol)
    n_up = sum(1 for w in weeks if w.get("direction") == "UP")
    n_down = sum(1 for w in weeks if w.get("direction") == "DOWN")
    n_flat = sum(1 for w in weeks if w.get("direction") == "FLAT")
    avg_perf = (sum(w["perf_pct"] for w in weeks) / len(weeks)
                  if weeks else 0.0)
    # Trend dominant
    if avg_perf > 0.3:
        trend = "BULLISH"
    elif avg_perf < -0.3:
        trend = "BEARISH"
    else:
        trend = "NEUTRAL"
    return {
        "symbol": symbol,
        "month": "2026-07",
        "weeks": weeks,
        "n_up_weeks": n_up,
        "n_down_weeks": n_down,
        "n_flat_weeks": n_flat,
        "avg_perf_pct": round(avg_perf, 3),
        "trend": trend,
    }


def anticipate_august() -> dict:
    """Anticipation entree aout 2026."""
    return {
        "month_in": "2026-08",
        "drivers": [
            "NFP_USD 2026-08-07 12:30 UTC (HIGH impact)",
            "CPI_USD 2026-08-13 18:00 UTC (HIGH impact)",
            "FOMC_MINUTES 2026-08-19 18:00 UTC (HIGH impact)",
            "Summer doldrums : faible liquidite historique",
            "Carry trades : risque si USD fort soudain",
        ],
        "scenarios": {
            "USD_CONTINUE_BEARISH": {
                "paire_favorables": ["GBPUSD", "EURUSD", "AUDUSD"],
                "paire_defavorables": ["USDJPY", "USDCHF"],
            },
            "USD_REPRISE_HAUSSIERE": {
                "paire_favorables": ["USDJPY", "USDCHF"],
                "paire_defavorables": ["GBPUSD", "AUDUSD"],
            },
            "RANGE_BORNE": {
                "vol_target": 0.5,
                "trades_per_day": "1-2 max",
            },
        },
        "risks": [
            "Geopolitique : risque escalation",
            "BCE decisions 2026-08",
            "Fed pivot expectations",
            "Liquidity squeeze fin ete",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 july 2026 analysis (Phase 51)",
    )
    parser.add_argument("--symbol", default=None,
                        help="Symbole specifique (defaut: tous)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    print("=" * 70)
    print("PHASE 51 — ANALYSE CLOTURE JUILLET 2026")
    print("=" * 70)
    monthly = monthly_behavior(Path(DB_PATH))
    print(f"Mois         : {monthly['month']}")
    print(f"Symboles     : {monthly['n_symbols']}")
    print(f"Plus volatil : {monthly['most_volatile']}")
    print()
    if args.symbol:
        weekly = july_weekly_summary(Path(DB_PATH), args.symbol)
        print(f"Symbole      : {weekly['symbol']}")
        print(f"Trend        : {weekly['trend']}")
        print(f"Avg perf     : {weekly['avg_perf_pct']:+.3f}%")
        print(f"Up/Down/Flat : {weekly['n_up_weeks']}/"
              f"{weekly['n_down_weeks']}/{weekly['n_flat_weeks']}")
        print()
        print("Detail semaines :")
        for w in weekly["weeks"]:
            print(f"  {w['week']}  {w['start']} -> {w['end']}  "
                  f"perf={w['perf_pct']:+.3f}%  "
                  f"[{w['direction']}]")
    print()
    print("--- ANTICIPATION AOUT 2026 ---")
    aug = anticipate_august()
    for d in aug["drivers"]:
        print(f"  - {d}")
    print()
    print("Scenarios :")
    for name, info in aug["scenarios"].items():
        print(f"  {name}: {info}")
    print()
    print("Risques :")
    for r in aug["risks"]:
        print(f"  - {r}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())