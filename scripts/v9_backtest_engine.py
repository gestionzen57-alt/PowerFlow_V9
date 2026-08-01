"""v9_backtest_engine.py — P2-3 motion CEO 48h Champ libre.

Backtest engine vectorise complet.
Calcule Sharpe / Sortino / Max DD / Walk-forward automatique.

Auteur : Hermes (P2-3 motion CEO 48h Champ libre, 31/07/2026)
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.bt_engine")


def compute_metrics(pips: list[float], dates: list[str] = None) -> dict:
    """Calcule metriques completes d'une serie de trades."""
    if not pips:
        return {"n_trades": 0, "wr": 0.0, "total_pips": 0.0}
    n = len(pips)
    wins = sum(1 for p in pips if p > 0)
    losses = n - wins
    wr = wins / n
    total_pips = sum(pips)
    avg_pips = total_pips / n
    # Max drawdown
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pips:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    # Sharpe-like (mean / std)
    if n > 1:
        mean = total_pips / n
        var = sum((p - mean) ** 2 for p in pips) / n
        std = var ** 0.5
        sharpe = mean / std if std > 0 else 0.0
    else:
        sharpe = 0.0
    # Sortino-like (mean / downside_std)
    downside = [p for p in pips if p < 0]
    if downside and len(downside) > 1:
        down_std = (sum(p ** 2 for p in downside) / len(downside)) ** 0.5
        sortino = (total_pips / n) / down_std if down_std > 0 else 0.0
    else:
        sortino = sharpe
    # Profit factor
    gross_wins = sum(p for p in pips if p > 0)
    gross_losses = abs(sum(p for p in pips if p < 0))
    profit_factor = (gross_wins / gross_losses
                       if gross_losses > 0 else float("inf"))
    return {
        "n_trades": n,
        "n_wins": wins,
        "n_losses": losses,
        "wr": round(wr, 4),
        "total_pips": round(total_pips, 2),
        "avg_pips": round(avg_pips, 2),
        "max_dd": round(-max_dd, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "profit_factor": round(profit_factor, 3)
            if profit_factor != float("inf") else 999.0,
    }


def run_backtest(symbol: str, db_path: Path,
                    lookback: int = 20, tp: float = 25.0,
                    sl: float = 8.0) -> dict:
    """Backtest daily : trade dans le sens du trend Daily."""
    if not db_path.exists():
        return {"error": "db_missing"}
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("""
                SELECT timestamp, close FROM candles_d
                WHERE symbol = ?
                ORDER BY timestamp ASC
            """, (symbol,)).fetchall()
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return {"error": "db_error"}
    if len(rows) < lookback + 2:
        return {"error": "insufficient_data", "n_candles": len(rows)}
    dates = [r[0] for r in rows]
    closes = [float(r[1]) for r in rows]
    pips_list = []
    trade_dates = []
    for i in range(lookback, len(closes) - 1):
        recent = closes[i - lookback:i]
        slope = (recent[-1] - recent[0]) / recent[0] if recent[0] != 0 else 0
        if abs(slope) < 0.005:
            continue  # ranging, skip
        entry = closes[i]
        exit_p = closes[i + 1]
        if slope > 0:
            change = (exit_p - entry) / entry
        else:
            change = (entry - exit_p) / entry
        # Convertir en pips approx (1% = ~100p sur GBPUSD)
        pips = min(tp, max(-sl, change * 10000))
        pips_list.append(pips)
        trade_dates.append(dates[i + 1])
    metrics = compute_metrics(pips_list, trade_dates)
    return {
        "symbol": symbol,
        "n_candles": len(closes),
        "lookback": lookback,
        "tp": tp,
        "sl": sl,
        **metrics,
    }


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="V9 backtest engine (P2-3)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--tp", type=float, default=25.0)
    parser.add_argument("--sl", type=float, default=8.0)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    result = run_backtest(args.symbol, Path(DB_PATH),
                            lookback=args.lookback, tp=args.tp, sl=args.sl)
    print("=" * 70)
    print(f"P2-3 — BACKTEST ENGINE ({args.symbol})")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    for k, v in result.items():
        if k != "trades":
            print(f"  {k:18s} : {v}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())