"""v9_feature_importance.py — Phase 26A motion CEO autopilote.

Analyse de l'importance des features (L1-L14) sur l'expectancy.
Utilise ablation study : pour chaque feature, calcule l'expectancy
sans cette feature et mesure le delta.

Auteur : Hermes (Phase 26A motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.feat_imp")


def get_paper_trades_full(db_path: Path | str) -> list[dict]:
    """Retourne tous les champs des paper trades fermes."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT id, symbol, direction, opened_at, closed_at,
                       pips_brut, pips_net, close_reason
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def _expectancy(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    return sum(t["pips_net"] for t in trades) / len(trades)


# Features definies (subset L1-L14 applicables au paper trades)
FEATURES = [
    ("symbol_gbpusd", lambda t: t.get("symbol") == "GBPUSD"),
    ("hour_11_13_utc", lambda t: 11 <= _extract_hour(t.get("closed_at")) < 13),
    ("direction_haussiere", lambda t: t.get("direction") == "haussiere"),
    ("is_win", lambda t: t.get("pips_net", 0) > 0),
    ("close_reason_tp", lambda t: t.get("close_reason") == "TP_hit"),
    ("close_reason_sl", lambda t: t.get("close_reason") == "SL_hit"),
    ("close_reason_time_exit", lambda t: t.get("close_reason") == "time_exit"),
]


def _extract_hour(ts: str | None) -> int:
    if not ts:
        return -1
    try:
        return int(ts.split("T")[1].split(":")[0]) if "T" in ts else -1
    except (IndexError, ValueError):
        return -1


def ablation_study(trades: list[dict]) -> list[dict]:
    """Calcule l'impact de chaque feature via ablation."""
    if len(trades) < 10:
        return []
    baseline = _expectancy(trades)
    results = []
    for name, predicate in FEATURES:
        # Trades SANS cette feature
        without = [t for t in trades if not predicate(t)]
        exp_without = _expectancy(without)
        # Trades AVEC cette feature
        with_feat = [t for t in trades if predicate(t)]
        exp_with = _expectancy(with_feat)
        delta = exp_with - baseline  # contribution = exp(with) - baseline
        results.append({
            "feature": name,
            "n_with": len(with_feat),
            "n_without": len(without),
            "exp_with": round(exp_with, 3),
            "exp_without": round(exp_without, 3),
            "delta": round(delta, 3),
            "impact": (
                "POSITIVE" if delta > 1.0
                else "NEGATIVE" if delta < -1.0
                else "NEUTRAL"
            ),
        })
    # Trier par delta descendant
    results.sort(key=lambda r: -r["delta"])
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 feature importance ablation (Phase 26A)",
    )
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    trades = get_paper_trades_full(DB_PATH)
    results = ablation_study(trades)

    print("=" * 70)
    print("PHASE 26A — FEATURE IMPORTANCE (ABLATION STUDY)")
    print("=" * 70)
    print(f"N trades analyses : {len(trades)}")
    print()
    if not results:
        print("Pas assez de trades pour analyse.")
        return 1
    print(f"{'Feature':30s} {'N with':>8s} {'Exp with':>10s} "
          f"{'Exp w/o':>10s} {'Delta':>8s} {'Impact':>10s}")
    print("-" * 70)
    for r in results:
        print(f"{r['feature']:30s} {r['n_with']:>8d} "
              f"{r['exp_with']:>+10.3f} {r['exp_without']:>+10.3f} "
              f"{r['delta']:>+8.3f} {r['impact']:>10s}")
    print()
    print("Top 3 features positives :")
    for r in results[:3]:
        print(f"  {r['feature']:30s} delta=+{r['delta']:.3f}")
    print()
    print("Bottom 3 features negatives :")
    for r in results[-3:]:
        print(f"  {r['feature']:30s} delta={r['delta']:.3f}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())