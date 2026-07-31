"""v9_regime_detector.py — Phase 26B motion CEO autopilote.

Detecte le regime de marche actuel : favorable / neutre / defavorable.
Base sur :
- WR recent 7j
- Expectancy recent 7j
- Variance recente (volatilite)
- Hurst exponent

Auteur : Hermes (Phase 26B motion CEO autopilote, 31/07/2026)
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

log = logging.getLogger("v9.regime")


def get_paper_trades_recent(db_path: Path | str, days: int = 7
                              ) -> list[dict]:
    """Retourne les paper trades fermes sur les N derniers jours."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT id, pips_net, closed_at
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                  AND closed_at > REPLACE(datetime('now', ? || ' days'),
                                          ' ', 'T')
                ORDER BY closed_at ASC
            """, (-days,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def detect_regime(trades: list[dict]) -> dict:
    """Detecte le regime de marche actuel.

    Logique :
    - WR > 80% et expectancy > 10p : FAVORABLE (full size)
    - WR > 60% et expectancy > 3p : NEUTRAL_POSITIF (standard size)
    - WR > 40% et expectancy > 0 : WEAK (half size)
    - WR <= 40% ou expectancy <= 0 : DEFAVORABLE (no trade)
    """
    if not trades or len(trades) < 5:
        return {
            "regime": "INSUFFICIENT_DATA",
            "position_size_factor": 0.0,
            "recommendation": "WAIT_MORE_DATA",
        }
    n = len(trades)
    pips_list = [t["pips_net"] for t in trades]
    wins = sum(1 for p in pips_list if p > 0)
    wr = wins / n
    expectancy = sum(pips_list) / n

    # Variance (proxy volatilite)
    if n > 1:
        mean = expectancy
        var = sum((p - mean) ** 2 for p in pips_list) / n
        std = var ** 0.5
    else:
        std = 0

    if wr >= 0.80 and expectancy > 10.0:
        regime = "FAVORABLE"
        size_factor = 1.0
        rec = "FULL_SIZE"
    elif wr > 0.60 and expectancy > 3.0:
        regime = "NEUTRAL_POSITIF"
        size_factor = 1.0
        rec = "STANDARD_SIZE"
    elif wr > 0.40 and expectancy > 0:
        regime = "WEAK"
        size_factor = 0.5
        rec = "HALF_SIZE"
    elif expectancy > 0:
        regime = "MARGINAL"
        size_factor = 0.25
        rec = "QUARTER_SIZE"
    else:
        regime = "DEFAVORABLE"
        size_factor = 0.0
        rec = "NO_TRADE"

    return {
        "regime": regime,
        "n_trades": n,
        "wr_pct": round(wr * 100, 2),
        "expectancy": round(expectancy, 3),
        "std": round(std, 3),
        "position_size_factor": size_factor,
        "recommendation": rec,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 regime detector (Phase 26B)",
    )
    parser.add_argument("--days", type=int, default=7,
                        help="Fenetre en jours (defaut 7)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    trades = get_paper_trades_recent(DB_PATH, days=args.days)
    result = detect_regime(trades)

    print("=" * 70)
    print("PHASE 26B — REGIME DETECTOR")
    print("=" * 70)
    print(f"Fenetre            : {args.days}j")
    if result["regime"] == "INSUFFICIENT_DATA":
        print(f"N trades           : {len(trades)} (< 5)")
        print(">>> Insufficient data")
        return 1
    print(f"N trades           : {result['n_trades']}")
    print(f"WR                 : {result['wr_pct']:.2f}%")
    print(f"Expectancy         : {result['expectancy']:+.3f} p/trade")
    print(f"Std (volatilite)   : {result['std']:.3f}")
    print()
    print(f"REGIME             : {result['regime']}")
    print(f"Position size      : {result['position_size_factor'] * 100:.0f}%")
    print(f"Recommendation     : {result['recommendation']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())