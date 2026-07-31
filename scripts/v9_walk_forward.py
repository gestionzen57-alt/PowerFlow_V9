"""v9_walk_forward.py — Phase 3 motion CEO « EDGE FUND MAX » walk-forward.

Valide la robustesse de l'edge MEGA-EDGE (GBPUSD haussiere 11-13h UTC) sur
5 fenetres glissantes 90j.

R2 additif. R6 jamais bloquant (DB absente → no-op).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.config import DB_PATH

log = logging.getLogger("v9.walk_forward")


def walk_forward_evaluation(db_path: Path | None = None,
                            n_windows: int = 5,
                            window_days: int = 90) -> dict:
    """Evalue l'edge MEGA-EDGE sur N fenetres glissantes de W jours.

    Returns dict {windows: [...], summary: {wr_avg, total_pips, n_total}}
    """
    path = Path(db_path) if db_path else DB_PATH
    if not path.exists():
        log.warning("walk_forward: DB absente %s, no-op", path)
        return {"windows": [], "summary": {}}

    windows = []
    try:
        with sqlite3.connect(str(path)) as conn:
            conn.row_factory = sqlite3.Row
            for w in range(n_windows):
                offset = w * 7  # Fenetres decalees de 7j pour eviter overlapping total
                start = (datetime.utcnow() - timedelta(days=window_days + offset)).isoformat()
                end = (datetime.utcnow() - timedelta(days=offset)).isoformat()
                row = conn.execute(
                    """
                    SELECT COUNT(*) n, SUM(is_win) wins,
                           ROUND(100.0*SUM(is_win)/COUNT(*),1) wr,
                           ROUND(SUM(pips_simulated),1) total
                    FROM paper_trades pt
                    JOIN forces_snapshots fs ON pt.snapshot_id = fs.snapshot_id
                    WHERE substr(pt.snapshot_id,4,6)='GBPUSD'
                      AND pt.direction='haussiere'
                      AND cast(strftime('%H', fs.timestamp) as int) BETWEEN 11 AND 13
                      AND pt.opened_at BETWEEN ? AND ?
                    """,
                    (start, end),
                ).fetchone()
                windows.append({
                    "window_id": w,
                    "start": start,
                    "end": end,
                    "n": int(row["n"]) if row and row["n"] is not None else 0,
                    "wins": int(row["wins"]) if row and row["wins"] is not None else 0,
                    "wr": float(row["wr"]) if row and row["wr"] is not None else 0.0,
                    "total_pips": float(row["total"]) if row and row["total"] is not None else 0.0,
                })
    except Exception as exc:
        log.error("walk_forward: best-effort failed: %s", exc)

    n_total = sum((w.get("n") or 0) for w in windows)
    wins_total = sum((w.get("wins") or 0) for w in windows)
    pips_total = sum((w.get("total_pips") or 0.0) for w in windows)
    wr_avg = (wins_total / n_total * 100) if n_total > 0 else 0.0
    summary = {
        "n_total": n_total,
        "wins_total": wins_total,
        "wr_avg": round(wr_avg, 1),
        "total_pips": round(pips_total, 1),
        "n_windows_passed": sum(1 for w in windows if w["wr"] >= 70.0),
    }
    return {"windows": windows, "summary": summary}


def main():
    logging.basicConfig(level=logging.INFO)
    res = walk_forward_evaluation()
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())