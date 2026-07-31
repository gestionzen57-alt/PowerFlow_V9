"""v9_heartbeat_capture.py — Phase 13 motion CEO « EDGE FUND MAX ».

R3 Perplexity : capture_server est headless mais MT4 necessite une
session GUI Windows. Un redemarrage machine ou une deconnexion coupe
le flux de donnees en silence. Aucun cron ne verifie que
capture_server recoit toujours des donnees (heartbeat absent).

Module : verifie que la table forces_snapshots a recu des snapshots
recents. Si pas de snapshot dans les N dernieres minutes, alerte.

Seuil configurable via V9_HEARTBEAT_MAX_AGE_MINUTES (defaut 5 min).
Sortie JSON stdout pour integration cron + alerte.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("v9.heartbeat_capture")


def get_last_snapshot_age_minutes(db_path: Path | str) -> float | None:
    """Retourne age en minutes du dernier forces_snapshot. None si table vide."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT MAX(timestamp) FROM forces_snapshots"
        ).fetchone()
        if not row or not row[0]:
            return None
        ts_str = str(row[0])
        try:
            last = datetime.fromisoformat(ts_str.replace(" ", "T"))
        except ValueError:
            try:
                last = datetime.utcfromtimestamp(int(float(ts_str)))
            except ValueError:
                log.error("heartbeat: format timestamp invalide: %s", ts_str)
                return None
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last
        return delta.total_seconds() / 60.0
    finally:
        conn.close()


def check_heartbeat(
    db_path: Path | str,
    *,
    max_age_minutes: float | None = None,
) -> dict[str, object]:
    """Verifie heartbeat capture_server. Retourne dict alert/ok + details."""
    if max_age_minutes is None:
        env_val = os.environ.get("V9_HEARTBEAT_MAX_AGE_MINUTES")
        max_age_minutes = float(env_val) if env_val else 5.0

    age = get_last_snapshot_age_minutes(db_path)

    if age is None:
        return {
            "ok": False,
            "alert": True,
            "reason": "no_snapshot_ever",
            "age_minutes": None,
            "max_age_minutes": max_age_minutes,
            "recommendation": "verifier_capture_server_status",
        }

    if age > max_age_minutes:
        return {
            "ok": False,
            "alert": True,
            "reason": "capture_silence",
            "age_minutes": round(age, 1),
            "max_age_minutes": max_age_minutes,
            "recommendation": "restart_capture_server",
        }

    return {
        "ok": True,
        "alert": False,
        "age_minutes": round(age, 1),
        "max_age_minutes": max_age_minutes,
        "reason": "ok",
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Retourne exit code 0=ok, 1=alert."""
    argv = argv or sys.argv[1:]
    from core.v9.config import DB_PATH
    db = DB_PATH
    for arg in argv:
        if arg.startswith("--db="):
            db = Path(arg.split("=", 1)[1])

    result = check_heartbeat(db)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result["alert"]:
        log.warning(
            "HEARTBEAT ALERT: %s (age=%.1f min, max=%.1f)",
            result["reason"], result.get("age_minutes") or 0,
            result["max_age_minutes"],
        )
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())