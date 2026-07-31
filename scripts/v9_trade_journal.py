"""v9_trade_journal.py — Phase 22 motion CEO « EDGE FUND MAX ».

Consolide les paper trades par jour dans un journal structure JSON.
Genere un rapport lisible du trading day-by-day.

Output : data/trade_journal/YYYY-MM-DD.json

Auteur : Hermes (Phase 22 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.trade_journal")

JOURNAL_DIR = Path(r"C:\projet\V9\data\trade_journal")


def get_trades_for_day(db_path: Path | str, day: str) -> list[dict]:
    """Retourne les paper trades fermes pour un jour donne (YYYY-MM-DD)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT id, symbol, opened_at, closed_at,
                       pips_brut, pips_net, close_reason, spread_pips
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                  AND substr(closed_at, 1, 10) = ?
                ORDER BY closed_at ASC
            """, (day,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def aggregate_day(trades: list[dict], day: str) -> dict:
    """Agrege les trades d'un jour en stats journal."""
    n_total = len(trades)
    if n_total == 0:
        return {
            "day": day,
            "n_total": 0,
            "n_wins": 0,
            "n_losses": 0,
            "wr_pct": 0.0,
            "pips_brut": 0.0,
            "pips_net": 0.0,
            "expectancy_net": 0.0,
            "max_pips": 0.0,
            "min_pips": 0.0,
        }
    pips_net_list = [float(t.get("pips_net") or 0) for t in trades]
    pips_brut_list = [float(t.get("pips_brut") or 0) for t in trades]
    wins = [p for p in pips_net_list if p > 0]
    losses = [p for p in pips_net_list if p < 0]
    return {
        "day": day,
        "n_total": n_total,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "wr_pct": round(100.0 * len(wins) / n_total, 2),
        "pips_brut": round(sum(pips_brut_list), 2),
        "pips_net": round(sum(pips_net_list), 2),
        "expectancy_net": round(sum(pips_net_list) / n_total, 2),
        "max_pips": round(max(pips_net_list), 2),
        "min_pips": round(min(pips_net_list), 2),
        "trades": trades,
    }


def save_journal(aggregated: dict) -> Path:
    """Sauvegarde le journal du jour dans data/trade_journal/YYYY-MM-DD.json."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    day = aggregated["day"]
    path = JOURNAL_DIR / f"{day}.json"
    path.write_text(
        json.dumps(aggregated, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 trade journal aggregator (Phase 22)",
    )
    parser.add_argument("--day", default=None,
                        help="Jour YYYY-MM-DD (defaut aujourd'hui UTC)")
    parser.add_argument("--days", type=int, default=None,
                        help="Generer les N derniers jours")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH

    days_to_aggregate = []
    if args.days:
        # Generer N derniers jours
        today = datetime.now(timezone.utc)
        for i in range(args.days):
            day = (today - __import__("datetime").timedelta(days=i)).strftime("%Y-%m-%d")
            days_to_aggregate.append(day)
    elif args.day:
        days_to_aggregate.append(args.day)
    else:
        days_to_aggregate.append(
            datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )

    print("=" * 70)
    print("PHASE 22 — TRADE JOURNAL AGGREGATOR")
    print("=" * 70)
    print(f"Jour(s) : {days_to_aggregate}")
    print()

    for day in days_to_aggregate:
        trades = get_trades_for_day(DB_PATH, day)
        aggregated = aggregate_day(trades, day)
        path = save_journal(aggregated)
        print(f"{day} : n={aggregated['n_total']:3d}  "
              f"WR={aggregated['wr_pct']:5.1f}%  "
              f"pips_net={aggregated['pips_net']:+.1f}  "
              f"exp_net={aggregated['expectancy_net']:+.2f}p  "
              f"-> {path.name}")
    print()
    print(f"Journal sauvegarde dans : {JOURNAL_DIR}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())