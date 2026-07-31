"""v9_dd_recovery_analysis.py — Phase 25B motion CEO autopilote.

Analyse la duree et le pattern de recovery apres drawdown.
Pour chaque drawdown > seuil, calcule :
- Profondeur max
- Duree avant recovery
- Recovery factor (gain_total / dd_max)

Auteur : Hermes (Phase 25B motion CEO autopilote, 31/07/2026)
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

log = logging.getLogger("v9.dd_recovery")


def get_paper_trades_pips(db_path: Path | str) -> list[float]:
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("""
                SELECT pips_net FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
            """).fetchall()
            return [float(r[0] or 0) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def analyze_dd_recovery(pips_list: list[float], dd_threshold: float = 10.0
                          ) -> dict:
    """Identifie les episodes de DD et leur recovery."""
    if not pips_list or len(pips_list) < 20:
        return {"error": "insufficient_data"}
    episodes = []
    running_max = 0.0
    running_dd = 0.0
    current_episode = None
    max_dd_overall = 0.0
    for i, p in enumerate(pips_list):
        running_dd += p
        if running_dd > running_max:
            running_max = running_dd
        dd = running_max - running_dd
        if dd > max_dd_overall:
            max_dd_overall = dd
        # Detecter entree en DD
        if dd >= dd_threshold and current_episode is None:
            current_episode = {
                "start_idx": i,
                "peak_before": running_max,
                "max_dd": dd,
            }
        elif dd < dd_threshold and current_episode is not None:
            # Recovery
            current_episode["end_idx"] = i
            current_episode["duration_trades"] = i - current_episode["start_idx"]
            current_episode["recovery_pips"] = running_dd - (
                current_episode["peak_before"] - current_episode["max_dd"]
            )
            episodes.append(current_episode)
            current_episode = None

    if not episodes:
        return {
            "n_episodes": 0,
            "max_dd_overall": round(max_dd_overall, 2),
            "message": "Aucun episode de DD > seuil detecte",
        }

    durations = [e["duration_trades"] for e in episodes]
    depths = [e["max_dd"] for e in episodes]
    return {
        "n_episodes": len(episodes),
        "max_dd_overall": round(max_dd_overall, 2),
        "duration_median": sorted(durations)[len(durations) // 2],
        "duration_max": max(durations),
        "depth_median": round(sorted(depths)[len(depths) // 2], 2),
        "depth_max": round(max(depths), 2),
        "episodes": episodes,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 DD recovery analysis (Phase 25B)",
    )
    parser.add_argument("--dd-threshold", type=float, default=10.0,
                        help="Seuil DD pour detecter episode (defaut 10p)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    pips = get_paper_trades_pips(DB_PATH)
    result = analyze_dd_recovery(pips, dd_threshold=args.dd_threshold)

    print("=" * 70)
    print("PHASE 25B — DRAWDOWN RECOVERY ANALYSIS")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    if "message" in result:
        print(result["message"])
        print(f"Max DD overall : {result['max_dd_overall']}p")
        return 0
    print(f"DD threshold       : {args.dd_threshold}p")
    print(f"N episodes         : {result['n_episodes']}")
    print(f"Max DD overall     : {result['max_dd_overall']}p")
    print(f"Duration median    : {result['duration_median']} trades")
    print(f"Duration max       : {result['duration_max']} trades")
    print(f"Depth median       : {result['depth_median']}p")
    print(f"Depth max          : {result['depth_max']}p")
    print()
    if result["duration_median"] <= 5:
        print(">>> Recovery RAPIDE (<=5 trades median)")
    elif result["duration_median"] <= 15:
        print(">>> Recovery MODEREE")
    else:
        print(">>> Recovery LENTE (>15 trades median)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())