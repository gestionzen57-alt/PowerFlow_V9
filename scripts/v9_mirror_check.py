"""v9_mirror_check.py — Phase 14 motion CEO « EDGE FUND MAX ».

BUG-P2 follow-up (Phase 8) : alerte si V9_HUMAN_MIRROR_BLOCKING=1 et
< 20 trades humains logues dans v9_human_trades (fingerprint obsolete).

Module : compte les trades humains, retourne dict avec count + alert si
< 20 trades. Recommandation motion CEO pour activer BLOCKING.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

log = logging.getLogger("v9.mirror_check")

MIN_HUMAN_TRADES_FOR_BLOCKING = 20


def count_human_trades(db_path: Path | str) -> int:
    """Retourne nombre de trades dans v9_human_trades."""
    db_path = Path(db_path)
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM v9_human_trades"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0
    finally:
        conn.close()


def check_mirror_readiness(db_path: Path | str) -> dict[str, object]:
    """Verifie que mirror BLOCKING peut etre active."""
    blocking_enabled = os.environ.get("V9_HUMAN_MIRROR_BLOCKING", "0") == "1"
    n_human = count_human_trades(db_path)

    can_activate = n_human >= MIN_HUMAN_TRADES_FOR_BLOCKING
    return {
        "blocking_enabled": blocking_enabled,
        "n_human_trades": n_human,
        "min_for_blocking": MIN_HUMAN_TRADES_FOR_BLOCKING,
        "can_activate_blocking": can_activate,
        "alert": blocking_enabled and not can_activate,
        "recommendation": (
            "ok_blocking_active" if (blocking_enabled and can_activate)
            else (
                "log_human_trades_first" if blocking_enabled
                else "blocking_disabled_no_action"
            )
        ),
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    from core.v9.config import DB_PATH
    db = DB_PATH
    for arg in argv:
        if arg.startswith("--db="):
            db = Path(arg.split("=", 1)[1])
    result = check_mirror_readiness(db)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["alert"] else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())