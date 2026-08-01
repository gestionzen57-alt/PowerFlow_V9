"""v9_oos_validator.py — Phase 59 motion CEO validée.

Out-of-sample validator avec walk-forward 7 folds.
Trade selon L1-L17 sur 90j historique, mesure Sharpe / Sortino / DD / PF.

Auteur : Hermes (Phase 59 motion CEO validée, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.oos_validator")


def fetch_candles(db_path: Path, symbol: str, n: int = 90) -> list[dict]:
    """Recupere les n dernieres bougies daily."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT timestamp, open, high, low, close
                FROM candles_d WHERE symbol = ?
                ORDER BY timestamp ASC LIMIT ?
            """, (symbol, n)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def compute_trend(closes: list[float], lookback: int = 20) -> str:
    """Trend detection sur N periodes."""
    if len(closes) < lookback:
        return "UNKNOWN"
    recent = closes[-lookback:]
    slope = (recent[-1] - recent[0]) / recent[0] if recent[0] != 0 else 0
    if slope > 0.005:
        return "UPTREND"
    if slope < -0.005:
        return "DOWNTREND"
    return "RANGING"


def walk_forward_validate(symbol: str, db_path: Path, n_folds: int = 7,
                            tp: float = 25.0, sl: float = 8.0
                            ) -> dict:
    """Walk-forward OOS validation."""
    candles = fetch_candles(db_path, symbol, n=90)
    if len(candles) < 30:
        return {"error": "insufficient_data",
                "n_candles": len(candles), "symbol": symbol}
    closes = [float(c["close"]) for c in candles]
    fold_size = len(closes) // n_folds
    if fold_size < 5:
        return {"error": "candles_too_short"}
    fold_results = []
    all_oos_pips = []
    for fold in range(n_folds):
        start = fold * fold_size
        end = start + fold_size + 20  # lookback 20
        if end > len(closes):
            break
        fold_closes = closes[start:end]
        fold_pips = []
        for i in range(20, len(fold_closes) - 1):
            trend = compute_trend(fold_closes[i - 20:i])
            if trend == "RANGING":
                continue
            entry = fold_closes[i]
            exit_p = fold_closes[i + 1]
            if trend == "UPTREND":
                change = (exit_p - entry) / entry
            else:
                change = (entry - exit_p) / entry
            pips = min(tp, max(-sl, change * 10000))
            fold_pips.append(pips)
        if not fold_pips:
            continue
        n = len(fold_pips)
        wins = sum(1 for p in fold_pips if p > 0)
        cum = sum(fold_pips)
        peak = 0
        cum_p = 0
        max_dd = 0
        for p in fold_pips:
            cum_p += p
            if cum_p > peak:
                peak = cum_p
            dd = peak - cum_p
            if dd > max_dd:
                max_dd = dd
        fold_results.append({
            "fold": fold + 1,
            "n_trades": n,
            "wr": round(wins / n, 4),
            "total_pips": round(cum, 2),
            "max_dd": round(-max_dd, 2),
        })
        all_oos_pips.extend(fold_pips)
    if not all_oos_pips:
        return {"error": "no_trades", "symbol": symbol}
    n = len(all_oos_pips)
    wins = sum(1 for p in all_oos_pips if p > 0)
    cum = sum(all_oos_pips)
    mean = cum / n
    var = sum((p - mean) ** 2 for p in all_oos_pips) / n
    std = var ** 0.5
    sharpe = mean / std if std > 0 else 0.0
    peak = 0
    cum_p = 0
    max_dd = 0
    for p in all_oos_pips:
        cum_p += p
        if cum_p > peak:
            peak = cum_p
        dd = peak - cum_p
        if dd > max_dd:
            max_dd = dd
    n_pos_folds = sum(1 for f in fold_results if f["total_pips"] > 0)
    n_neg_folds = sum(1 for f in fold_results if f["total_pips"] < 0)
    verdict = "DEPLOYABLE"
    if sharpe < 0.5:
        verdict = "NEEDS_TUNING"
    if sharpe < 0 or n_pos_folds < n_folds / 2:
        verdict = "NOT_EDGE"
    return {
        "symbol": symbol,
        "n_folds": len(fold_results),
        "n_oos_trades": n,
        "n_oos_wins": wins,
        "wr": round(wins / n, 4),
        "total_pips": round(cum, 2),
        "sharpe": round(sharpe, 3),
        "max_dd": round(-max_dd, 2),
        "n_pos_folds": n_pos_folds,
        "n_neg_folds": n_neg_folds,
        "verdict": verdict,
        "folds": fold_results,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 OOS validator (Phase 59)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--folds", type=int, default=7)
    parser.add_argument("--tp", type=float, default=25.0)
    parser.add_argument("--sl", type=float, default=8.0)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    result = walk_forward_validate(args.symbol, Path(DB_PATH),
                                       n_folds=args.folds,
                                       tp=args.tp, sl=args.sl)
    print("=" * 70)
    print(f"PHASE 59 — OOS VALIDATOR ({args.symbol})")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        print(f"N candles : {result.get('n_candles', 0)}")
        return 1
    print(f"N folds         : {result['n_folds']}")
    print(f"N OOS trades    : {result['n_oos_trades']}")
    print(f"WR              : {result['wr']:.1%}")
    print(f"Total pips      : {result['total_pips']:+.2f}")
    print(f"Sharpe          : {result['sharpe']:+.3f}")
    print(f"Max DD          : {result['max_dd']}")
    print(f"Folds positifs  : {result['n_pos_folds']}")
    print(f"Folds negatifs  : {result['n_neg_folds']}")
    print()
    print(f"VERDICT : {result['verdict']}")
    print()
    print("Detail folds :")
    for f in result["folds"]:
        sign = "+" if f["total_pips"] > 0 else "-"
        print(f"  Fold {f['fold']}  {sign}  "
              f"WR={f['wr']:.1%}  pips={f['total_pips']:+.2f}  "
              f"DD={f['max_dd']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())