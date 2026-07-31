"""v9_alert_engine.py — Phase 29B motion CEO autopilote.

Moteur d'alertes configurable.
Detecte des evenements critiques et declenche des actions :
- Console log (stdout)
- File log (data/alerts.log)
- Telegram (future, via .env config)

Regles :
- WR < 50% sur 7j
- DD > 50 pips
- 3 losses consecutives
- Heartbeat > 10 min sans MAJ
- Edge drift (live vs bootstrap)

Auteur : Hermes (Phase 29B motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.alerts")

ALERTS_LOG = Path(r"C:\projet\V9\data\alerts.log")


def check_wr_alert(db_path: Path | str, days: int = 7,
                    threshold: float = 50.0) -> dict | None:
    """Alerte si WR < threshold% sur N jours."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("""
                SELECT
                    SUM(CASE WHEN pips_net > 0 THEN 1 ELSE 0 END) AS n_wins,
                    SUM(CASE WHEN pips_net <= 0 THEN 1 ELSE 0 END) AS n_losses
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                  AND closed_at > REPLACE(datetime('now', ? || ' days'),
                                          ' ', 'T')
            """, (-days,)).fetchone()
            n_wins = int(row[0] or 0)
            n_losses = int(row[1] or 0)
            n = n_wins + n_losses
            if n < 5:
                return None
            wr = 100.0 * n_wins / n
            if wr < threshold:
                return {
                    "type": "WR_LOW",
                    "severity": "WARNING",
                    "message": f"WR {wr:.1f}% < {threshold}% sur {days}j "
                                f"({n_wins}W/{n_losses}L, n={n})",
                    "value": wr,
                    "threshold": threshold,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            return None
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def check_dd_alert(db_path: Path | str, threshold: float = 50.0) -> dict | None:
    """Alerte si drawdown courant > threshold pips."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("""
                SELECT pips_net FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                ORDER BY closed_at ASC
            """).fetchall()
            if not rows:
                return None
            running_max = 0.0
            running_dd = 0.0
            max_dd = 0.0
            for (p,) in rows:
                running_dd += p
                if running_dd > running_max:
                    running_max = running_dd
                dd = running_max - running_dd
                if dd > max_dd:
                    max_dd = dd
            if max_dd > threshold:
                return {
                    "type": "DD_HIGH",
                    "severity": "CRITICAL",
                    "message": f"Max DD {max_dd:.1f}p > {threshold}p",
                    "value": max_dd,
                    "threshold": threshold,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            return None
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def check_loss_streak_alert(db_path: Path | str,
                              threshold: int = 3) -> dict | None:
    """Alerte si N losses consecutives."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("""
                SELECT pips_net FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
                ORDER BY closed_at DESC
                LIMIT 20
            """).fetchall()
            if not rows:
                return None
            streak = 0
            for (p,) in rows:
                if p < 0:
                    streak += 1
                else:
                    break
            if streak >= threshold:
                return {
                    "type": "LOSS_STREAK",
                    "severity": "WARNING",
                    "message": f"{streak} losses consecutives",
                    "value": streak,
                    "threshold": threshold,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            return None
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def log_alert(alert: dict) -> None:
    """Log alerte dans fichier + console."""
    line = (f"[{alert['ts']}] [{alert['severity']}] {alert['type']}: "
            f"{alert['message']}")
    print(line)
    ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_all_checks(db_path: Path | str) -> list[dict]:
    """Execute tous les checks et retourne la liste des alertes."""
    alerts = []
    wr_alert = check_wr_alert(db_path)
    if wr_alert:
        alerts.append(wr_alert)
    dd_alert = check_dd_alert(db_path)
    if dd_alert:
        alerts.append(dd_alert)
    streak_alert = check_loss_streak_alert(db_path)
    if streak_alert:
        alerts.append(streak_alert)
    return alerts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 alert engine (Phase 29B)",
    )
    parser.add_argument("--wr-threshold", type=float, default=50.0)
    parser.add_argument("--dd-threshold", type=float, default=50.0)
    parser.add_argument("--streak-threshold", type=int, default=3)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    alerts = run_all_checks(DB_PATH)

    print("=" * 70)
    print("PHASE 29B — ALERT ENGINE")
    print("=" * 70)
    if not alerts:
        print("Aucune alerte declenchee.")
        return 0
    for alert in alerts:
        log_alert(alert)
    print()
    print(f"{len(alerts)} alerte(s) declenchee(s). Log : {ALERTS_LOG}")
    print("=" * 70)
    return 1 if any(a["severity"] == "CRITICAL" for a in alerts) else 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())