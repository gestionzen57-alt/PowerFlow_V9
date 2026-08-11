"""Z2 — Live Health Check Script (bug-fixed 11/08/2026).

Fixes appliqués :
  Z2-FIX-1 : ImportError guard sur LiveHealthChecker (fail-open R6)
  Z2-FIX-2 : db_path fallback sur 'data/v9_forces.db' si absent
  Z2-FIX-3 : JSON report horodaté systématiquement (R9)
  Z2-FIX-4 : exit code 0 si HEALTHY, 1 si DEGRADED/CRITICAL
  Z2-FIX-5 : ruff-clean (no unused imports, no bare except)

Usage :
  python scripts/run_live_health_check.py
  python scripts/run_live_health_check.py --db data/v9_forces.db --verbose
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ── Import guard (Z2-FIX-1 / R6 fail-open) ──────────────────────────
try:
    from core.v10.v10_live_health_checker import LiveHealthChecker
    _CHECKER_OK = True
except Exception as _e:
    log.warning("[Z2] LiveHealthChecker import KO (fail-open): %s", _e)
    LiveHealthChecker = None  # type: ignore[assignment,misc]
    _CHECKER_OK = False

# ── Constantes ───────────────────────────────────────────────────────
DEFAULT_DB = "data/v9_forces.db"
REPORTS_DIR = Path("reports")
TARGET_SCORE = 90


def _neutral_report(db_path: str, reason: str) -> dict:
    """Rapport neutre si checker indisponible (R6)."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_path": db_path,
        "status": "UNKNOWN",
        "score": 0,
        "reason": reason,
        "layers": {},
        "r10": "compute only, zero order real",
    }


def run_health_check(db_path: str = DEFAULT_DB, verbose: bool = False) -> dict:
    """Lance le health check 6 couches et retourne le rapport dict."""
    # Z2-FIX-2 : fallback db_path
    resolved = Path(db_path)
    if not resolved.exists():
        log.warning("[Z2] DB absente : %s — fallback %s", db_path, DEFAULT_DB)
        db_path = DEFAULT_DB

    if not _CHECKER_OK or LiveHealthChecker is None:
        report = _neutral_report(db_path, "LiveHealthChecker_import_failed")
        _save_report(report)
        return report

    try:
        checker = LiveHealthChecker(db_path=db_path)
        result = checker.run()
        # Normalise en dict (R9)
        if hasattr(result, "as_dict"):
            report = result.as_dict()
        elif isinstance(result, dict):
            report = result
        else:
            report = {"status": str(result), "score": 0}
    except Exception as exc:
        log.warning("[Z2] LiveHealthChecker.run() fail-open: %s", exc)
        report = _neutral_report(db_path, f"run_error: {exc}")

    # Z2-FIX-3 : timestamp systématique
    report.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    report.setdefault("r10", "compute only, zero order real")

    if verbose:
        print(json.dumps(report, indent=2, default=str))
    else:
        score = report.get("score", 0)
        status = report.get("status", "UNKNOWN")
        print(f"[Z2] Health: {status} — score {score}/100 (cible ≥ {TARGET_SCORE})")

    _save_report(report)
    return report


def _save_report(report: dict) -> None:
    """Sauvegarde JSON horodaté dans reports/ (R9)."""
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = REPORTS_DIR / f"health_check_{ts}.json"
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        log.debug("[Z2] rapport sauvegardé : %s", path)
    except Exception as exc:
        log.warning("[Z2] sauvegarde rapport échouée (R6): %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Z2 — Live Health Check V10")
    parser.add_argument("--db", default=DEFAULT_DB, help="Chemin DB SQLite")
    parser.add_argument("--verbose", action="store_true", help="Rapport JSON complet")
    args = parser.parse_args()

    report = run_health_check(db_path=args.db, verbose=args.verbose)

    # Z2-FIX-4 : exit code différencié
    status = report.get("status", "UNKNOWN")
    score = int(report.get("score", 0))
    if status == "HEALTHY" and score >= TARGET_SCORE:
        print(f"✅ HEALTHY {score}/100 — GO LIVE conditions remplies")
        sys.exit(0)
    else:
        print(f"⚠️  {status} {score}/100 — en attente IBKR + feed actif")
        sys.exit(1)


if __name__ == "__main__":
    main()
