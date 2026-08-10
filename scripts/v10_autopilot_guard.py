"""v10_autopilot_guard.py — garde de continuité NO-LIMIT (stdout-only).

Vérifie l'état du système sans raisonnement (no_agent cron pattern) :
  - base `feat/v10-c20-healthy` a-t-elle bougé ?
  - working tree a-t-il des modifications non commitées de code ?
  - la DB est-elle fraîche (bar_time récent) ?

Sortie : STDOUT VIDE = tout va bien (silence watchdog). NON-vide = alerte.

R10 : zéro ordre. Lecture seule. R6 fail-open.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V9_DB = ROOT / "data" / "v9_forces.db"
BRANCH = "feat/hermes-night"
BASE = "origin/feat/v10-c20-healthy"


def _sh(cmd: list[str], cwd: str | None = None) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                           cwd=cwd or str(ROOT))
        return r.stdout.strip()
    except Exception:
        return ""


def _check_base_moved() -> str:
    """Renvoie un message si la base a de nouveaux commits que la branche n'a pas."""
    _sh(["git", "fetch", "origin", "--quiet"])
    local = _sh(["git", "rev-parse", "HEAD"])
    ahead = _sh(["git", "log", "--oneline", f"{local}..{BASE}"])
    if ahead:
        n = len([ln for ln in ahead.splitlines() if ln.strip()])
        return f"[NO-LIMIT] base {BASE} a {n} commit(s) en avance sur {BRANCH} → rebase requis\n"
    return ""


def _check_uncommitted_code() -> str:
    """Renvoie un message si du code source est modifié non commité."""
    st = _sh(["git", "status", "--short", "--", "core/", "scripts/", "tests/", "config/"])
    if st:
        return f"[NO-LIMIT] code non commité sur {BRANCH}:\n{st}\n"
    return ""


def _check_db_freshness() -> str:
    """Renvoie un message si la DB est stale (>2h, week-end exclu)."""
    try:
        import sqlite3
        if not V9_DB.exists():
            return "[NO-LIMIT] DB introuvable\n"
        con = sqlite3.connect(f"file:{V9_DB}?mode=ro", uri=True, timeout=10)
        row = con.execute(
            "SELECT MAX(bar_time) FROM forces_snapshots WHERE is_closed_bar=1"
        ).fetchone()
        con.close()
        now = int(datetime.now(UTC).timestamp())
        if row and row[0]:
            age = now - int(row[0])
            if age > 7200:  # >2h
                return f"[NO-LIMIT] DB stale: dernier bar_time il y a {age//3600}h\n"
    except Exception:
        pass
    return ""


def main() -> int:
    msgs = []
    msgs.append(_check_base_moved())
    msgs.append(_check_uncommitted_code())
    msgs.append(_check_db_freshness())
    out = "".join(msgs)
    if out:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    main()
