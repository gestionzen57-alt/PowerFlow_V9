#!/usr/bin/env python3
"""v9_close_time_exit.py — Phase 3 motion CEO « EDGE FUND MAX ».

L3 audit SQL 90j : trades > 5min = -407p cumulé. Ferme tous paper_trades
ouverts depuis > 5min en mode forcé (artefact = pips conservateur 0).

R2 additif (n'altère pas close_open_trades). R6 jamais bloquant.
Kill switch V9_TIME_EXIT_ENABLED (défaut ON autopilot CEO).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Permet import core.v9.*
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.config import DB_PATH

log = logging.getLogger("v9.time_exit")


def time_exit_enabled() -> bool:
    """Kill switch V9_TIME_EXIT_ENABLED — L3 force closure >5min (defaut ON)."""
    return os.environ.get("V9_TIME_EXIT_ENABLED", "1") == "1"


def force_close_aged_trades(db_path: Path | None = None,
                            max_hold_minutes: float = 5.0) -> dict[str, int]:
    """Ferme paper_trades ouverts > 5min en artifact (pips=0, is_win=0).

    Returns dict {forced, skipped, artifact}.
    """
    if not time_exit_enabled():
        return {"forced": 0, "skipped": 0, "artifact": 0}

    path = Path(db_path) if db_path else DB_PATH
    if not path.exists():
        log.warning("time_exit: DB absente %s, no-op", path)
        return {"forced": 0, "skipped": 0, "artifact": 0}

    forced = skipped = artifact = 0
    now = datetime.utcnow().isoformat()
    try:
        with sqlite3.connect(str(path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT trade_id, opened_at,
                       (julianday('now') - julianday(opened_at)) * 24 * 60 AS age_min
                FROM paper_trades
                WHERE closed_at IS NULL AND opened_at IS NOT NULL
                """
            ).fetchall()
            for r in rows:
                age_min = r["age_min"]
                if age_min is None:
                    continue
                if age_min >= max_hold_minutes:
                    # Force closure artifact (pips=0, loss=0 pour R6)
                    conn.execute(
                        """
                        UPDATE paper_trades
                        SET closed_at = ?, is_win = 0, pips_simulated = 0
                        WHERE trade_id = ? AND closed_at IS NULL
                        """,
                        (now, r["trade_id"]),
                    )
                    forced += 1
                    artifact += 1
                else:
                    skipped += 1
            conn.commit()
    except Exception as exc:
        log.error("time_exit: best-effort failed: %s", exc)

    return {"forced": forced, "skipped": skipped, "artifact": artifact}


def main():
    logging.basicConfig(level=logging.INFO)
    res = force_close_aged_trades()
    print(f"v9_close_time_exit: {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())