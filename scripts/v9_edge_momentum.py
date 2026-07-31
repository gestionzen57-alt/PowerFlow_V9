"""v9_edge_momentum.py — Phase 22 motion CEO « EDGE FUND MAX ».

Tracker l'evolution de l'edge dans le temps (semaine par semaine).
Genere un rapport de momentum : l'edge s'ameliore-t-il ou se degrade-t-il ?

Output : data/edge_momentum/YYYY-MM-DD.json (par jour)
         data/edge_momentum/weekly_summary.json (consolide)

Auteur : Hermes (Phase 22 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.edge_momentum")

MOMENTUM_DIR = Path(r"C:\projet\V9\data\edge_momentum")

# Edge baseline Phase 15
EDGE_BASELINE_WR = 94.6
EDGE_BASELINE_EXP_NET = 3.05
EDGE_BASELINE_DD = 34.5


def get_weekly_stats(db_path: Path | str, days_ago: int = 0) -> dict:
    """Stats sur une semaine se terminant il y a N jours."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {"error": "db_missing"}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            # Fenetre de 7 jours
            start_offset = days_ago + 7
            rows = conn.execute("""
                SELECT pips_net, closed_at
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                  AND closed_at > REPLACE(datetime('now', ? || ' days'), ' ', 'T')
                  AND closed_at <= REPLACE(datetime('now', ? || ' days'), ' ', 'T')
            """, (-start_offset, -days_ago)).fetchall()
            n = len(rows)
            if n == 0:
                return {
                    "n_total": 0,
                    "wr_pct": 0.0,
                    "expectancy_net": 0.0,
                    "total_pips_net": 0.0,
                    "period": f"j-{start_offset}_to_j-{days_ago}",
                }
            pips_net_list = [float(r["pips_net"] or 0) for r in rows]
            wins = [p for p in pips_net_list if p > 0]
            return {
                "n_total": n,
                "wr_pct": round(100.0 * len(wins) / n, 2),
                "expectancy_net": round(sum(pips_net_list) / n, 2),
                "total_pips_net": round(sum(pips_net_list), 2),
                "period": f"j-{start_offset}_to_j-{days_ago}",
            }
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return {"error": "tables_missing"}


def compute_momentum(db_path: Path | str, n_weeks: int = 4) -> dict:
    """Calcule le momentum sur N semaines consecutives."""
    weekly_stats = []
    for week in range(n_weeks):
        days_ago = week * 7
        stats = get_weekly_stats(db_path, days_ago=days_ago)
        weekly_stats.append(stats)

    # Filtrer semaines avec data
    valid = [w for w in weekly_stats if w.get("n_total", 0) > 0]
    if len(valid) < 2:
        return {
            "recommendation": "INSUFFICIENT_DATA",
            "weekly_stats": weekly_stats,
            "n_weeks_valid": len(valid),
        }

    # Trend WR : croissante ou decroissante ?
    wrs = [w["wr_pct"] for w in valid]
    wr_trend = wrs[-1] - wrs[0]
    exp_trend = valid[-1]["expectancy_net"] - valid[0]["expectancy_net"]

    if wr_trend > 5.0 and exp_trend > 0.5:
        trend = "IMPROVING"
        rec = "EDGE_GROWING"
    elif wr_trend < -5.0 or exp_trend < -1.0:
        trend = "DEGRADING"
        rec = "EDGE_FADING"
    else:
        trend = "STABLE"
        rec = "EDGE_STABLE"

    return {
        "recommendation": rec,
        "trend": trend,
        "wr_trend_pts": round(wr_trend, 2),
        "exp_trend_pips": round(exp_trend, 2),
        "weekly_stats": weekly_stats,
        "n_weeks_valid": len(valid),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def save_momentum(momentum: dict) -> Path:
    """Sauvegarde le rapport momentum."""
    MOMENTUM_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = MOMENTUM_DIR / f"{today}.json"
    path.write_text(
        json.dumps(momentum, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    weekly_path = MOMENTUM_DIR / "weekly_summary.json"
    weekly_path.write_text(
        json.dumps(momentum, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 edge momentum tracker (Phase 22)",
    )
    parser.add_argument("--weeks", type=int, default=4,
                        help="Nombre de semaines a analyser (defaut 4)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    momentum = compute_momentum(DB_PATH, n_weeks=args.weeks)
    path = save_momentum(momentum)

    print("=" * 70)
    print("PHASE 22 — EDGE MOMENTUM TRACKER")
    print("=" * 70)
    print(f"Semaines analysees : {args.weeks}")
    print(f"Semaines avec data : {momentum.get('n_weeks_valid', 0)}")
    print()
    print("Stats par semaine :")
    for w in momentum.get("weekly_stats", []):
        print(f"  {w.get('period', '?'):25s}  "
              f"n={w.get('n_total', 0):3d}  "
              f"WR={w.get('wr_pct', 0):5.1f}%  "
              f"exp_net={w.get('expectancy_net', 0):+.2f}p  "
              f"total={w.get('total_pips_net', 0):+.1f}p")
    print()
    print(f"Trend WR    : {momentum.get('wr_trend_pts', 0):+.1f} pts")
    print(f"Trend exp   : {momentum.get('exp_trend_pips', 0):+.2f} pips")
    print(f"Recommendation : {momentum.get('recommendation', 'unknown')}")
    print()
    print(f"Sauvegarde : {path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())