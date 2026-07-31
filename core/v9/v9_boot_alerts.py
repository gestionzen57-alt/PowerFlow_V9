"""core/v9/v9_boot_alerts.py — Phase 8 motion CEO « EDGE FUND MAX ».

Alertes au boot du systeme (import du module) si kill switches
critiques sont desactives ou incoherents entre eux.

BUG-P1 : aucun log d'alerte si MEGA est OFF en runtime prod.
BUG-P4 : L3 time_exit 5min vs HUMAN_SCALP TREND TP=35 incoherence.
BUG-P2 : mirror BLOCKING actif mais sans donnees humaines depuis X jours.

R2 additif (jamais bloquant), R6 silencieux (best-effort).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("v9.boot_alerts")


def check_kill_switch_coherence(db_path: Path | None = None) -> list[str]:
    """Verifie coherence kill switches et DB. Retourne liste de warnings."""
    warnings: list[str] = []

    # BUG-P1 : si MEGA_OFF en runtime prod, alerter.
    # On distingue "prod" via V9_BOOT_CONTEXT=prod (pose par scripts CLI,
    # cron, trade_engine). Si absent (pytest, notebooks, REPL), pas d'alerte.
    is_prod = os.environ.get("V9_BOOT_CONTEXT") == "prod"
    if os.environ.get("V9_MEGA_EDGE_ENABLED", "1") == "0" and is_prod:
        warnings.append(
            "[BUG-P1] V9_MEGA_EDGE_ENABLED=0 en runtime prod. "
            "Le filtre MEGA-EDGE L1-L9 est desactive. "
            "Le systeme trade sans les leviers quantitatifs."
        )

    # BUG-P4 : L3 5min vs HUMAN_SCALP TREND/CASSURE incoherence
    l3_on = os.environ.get("V9_TIME_EXIT_ENABLED", "1") == "1"
    human_on = os.environ.get("V9_DRM_HUMAN_PROFILE_ENABLED", "1") == "1"
    if l3_on and human_on:
        # HUMAN_SCALP TREND TP=35 vs L3 5min = RR reel 0
        warnings.append(
            "[BUG-P4] L3 time_exit (5min) actif ET HUMAN_SCALP TREND/CASSURE "
            "(TP=25-35) actif. Les trades longs sont forces a pips=0 avant "
            "TP. RR reel degrade. Recommendation : V9_DRM_HUMAN_PROFILE_ENABLED=0 "
            "OU augmenter V9_TIME_EXIT_MINUTES pour les phases TREND/CASSURE."
        )

    # BUG-P2 : mirror BLOCKING actif sans donnees
    if os.environ.get("V9_HUMAN_MIRROR_ENABLED", "1") == "1" and \
       os.environ.get("V9_HUMAN_MIRROR_BLOCKING", "0") == "1":
        age = _mirror_data_age_days(db_path)
        if age is None:
            warnings.append(
                "[BUG-P2] Mirror BLOCKING actif mais table v9_human_trades "
                "vide. Le score est neutre (0.5), aucun blocage effectif."
            )
        elif age > 7:
            warnings.append(
                f"[BUG-P2] Mirror BLOCKING actif mais dernier trade humain "
                f"il y a {age} jours. Le fingerprint est obsolète."
            )

    return warnings


def _mirror_data_age_days(db_path: Path | None = None) -> int | None:
    """Retourne jours depuis dernier trade dans v9_human_trades. None si vide/DB absente."""
    conn = None
    try:
        from core.v9.config import DB_PATH
        path = Path(db_path) if db_path else DB_PATH
        if not path.exists():
            return None
        conn = sqlite3.connect(str(path))
        row = conn.execute(
            "SELECT MAX(timestamp) FROM v9_human_trades"
        ).fetchone()
        if not row or not row[0]:
            return None
        last = datetime.fromisoformat(str(row[0]).replace(" ", "T"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last
        return delta.days
    except Exception:
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def run_boot_alerts(db_path: Path | None = None) -> int:
    """Execute les alertes au boot. Retourne nombre de warnings."""
    warnings = check_kill_switch_coherence(db_path=db_path)
    for w in warnings:
        log.warning(w)
    return len(warnings)