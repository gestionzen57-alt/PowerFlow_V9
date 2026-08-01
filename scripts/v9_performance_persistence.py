"""v9_performance_persistence.py — Phase 68 motion CEO 48H.

Performance persistence : tracking des metriques sur le temps.
Stocke dans data/v9_performance_history.json.

Auteur : Hermes (Phase 68 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.perf_persist")

HISTORY_PATH = Path(r"C:\projet\V9\data\v9_performance_history.json")


def load_history() -> list[dict]:
    """Charge historique performance."""
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_history(history: list[dict]) -> None:
    """Persiste historique."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def record_snapshot(metrics: dict) -> dict:
    """Enregistre snapshot performance."""
    history = load_history()
    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **metrics,
    }
    history.append(snapshot)
    # Garde 1000 derniers
    if len(history) > 1000:
        history = history[-1000:]
    save_history(history)
    return snapshot


def compute_trend(history: list[dict], window: int = 10) -> dict:
    """Calcule trend recent."""
    if len(history) < 2:
        return {"trend": "UNKNOWN"}
    recent = history[-window:]
    pnl_values = [h.get("pnl_pips", 0) for h in recent]
    if not pnl_values:
        return {"trend": "NO_DATA"}
    slope = (pnl_values[-1] - pnl_values[0]) / len(pnl_values)
    if slope > 5:
        trend = "IMPROVING"
    elif slope < -5:
        trend = "DEGRADING"
    else:
        trend = "STABLE"
    return {
        "trend": trend,
        "slope": round(slope, 3),
        "n_snapshots": len(history),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 performance persistence (Phase 68)",
    )
    parser.add_argument("--record", action="store_true",
                        help="Record snapshot")
    parser.add_argument("--pnl", type=float, default=0.0)
    parser.add_argument("--wr", type=float, default=0.0)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    if args.record:
        snap = record_snapshot({
            "pnl_pips": args.pnl,
            "wr": args.wr,
        })
        print(f"Snapshot recorded : {snap['ts']}")
        return 0

    if args.status:
        history = load_history()
        trend = compute_trend(history)
        print("=" * 70)
        print("V9 PERFORMANCE PERSISTENCE")
        print("=" * 70)
        print(f"Snapshots saved : {len(history)}")
        print(f"Trend           : {trend['trend']}")
        if "slope" in trend:
            print(f"Slope           : {trend['slope']}")
        if history:
            last = history[-1]
            print(f"Last PnL        : {last.get('pnl_pips', 0)}")
            print(f"Last WR         : {last.get('wr', 0)}")
        print("=" * 70)
        return 0

    # Default : status
    history = load_history()
    print(f"Snapshots : {len(history)}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())
