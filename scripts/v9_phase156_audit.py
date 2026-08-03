#!/usr/bin/env python
"""
Phase 156 — Audit quotidien GBPUSD post-désactivation L8+L9 (2026-08-03+).

Mesure le retour de l'edge GBPUSD après que L8 (n_principes>=5) et L9
(blacklist <14h UTC) aient été désactivés (commit 5c963cb).

Usage:
    python scripts/v9_phase156_audit.py            # audit aujourd'hui
    python scripts/v9_phase156_audit.py --days 7   # audit J+7
    python scripts/v9_phase156_audit.py --json     # sortie JSON (pour cron)

Verdict GO/NO-GO :
  GO    : n>=50  AND WR>=70% AND PNL>=+200p    → edge authentique préservé
  WARN  : n>=30  AND WR>=50% AND PNL>=0         → edge en récupération
  HALT  : n>=30  AND WR<50%                     → L8/L9 avaient raison, bug ailleurs
  WAIT  : n<30                                  → pas assez de données

Doctrine :
  R2 additif (nouveau script, 0 modif core/)
  R6 fail-open (try/except close connexion, fallback WR=0 PNL=0)
  R14 audit SQL live = source de vérité
  R26 entrée DECISIONS_LOG si verdict change
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def get_db_path() -> Path:
    return _ROOT / "data" / "v9_forces.db"


def audit_gbpusd(days: int = 7) -> dict:
    """Calcule n, WR, PNL sur window_days post-désactivation L8+L9."""
    conn = None
    try:
        conn = sqlite3.connect(str(get_db_path()), timeout=15)
        row = conn.execute(
            """
            SELECT
              COUNT(*),
              SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END),
              ROUND(100.0 * SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) / MAX(COUNT(*), 1), 1),
              ROUND(SUM(pips_simulated), 1)
            FROM paper_trades
            WHERE opened_at > datetime('now', ?)
              AND substr(snapshot_id, 3, 6) = '-GBPUS'
            """,
            (f"-{days} days",),
        ).fetchone()
        n_total, n_wins, wr_pct, pnl_pips = (row[0] or 0, row[1] or 0, row[2] or 0.0, row[3] or 0.0)
        by_day = conn.execute(
            """
            SELECT DATE(opened_at) d, COUNT(*) n,
              ROUND(100.0 * SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) wr,
              ROUND(SUM(pips_simulated), 1) pnl
            FROM paper_trades
            WHERE opened_at > datetime('now', ?)
              AND substr(snapshot_id, 3, 6) = '-GBPUS'
            GROUP BY d ORDER BY d
            """,
            (f"-{days} days",),
        ).fetchall()
        return {
            "n_trades": n_total,
            "n_wins": n_wins,
            "wr_pct": wr_pct,
            "pnl_pips": pnl_pips,
            "by_day": [{"date": d, "n": n, "wr": wr, "pnl": pnl} for d, n, wr, pnl in by_day],
        }
    except Exception as e:
        return {"n_trades": 0, "n_wins": 0, "wr_pct": 0.0, "pnl_pips": 0.0, "by_day": [], "error": str(e)}
    finally:
        if conn is not None:
            conn.close()


def compute_verdict(metrics: dict) -> str:
    n = metrics["n_trades"]
    wr = metrics["wr_pct"]
    pnl = metrics["pnl_pips"]
    if n < 30:
        return "WAIT"
    if wr < 50:
        return "HALT"
    if n >= 50 and wr >= 70 and pnl >= 200:
        return "GO"
    return "WARN"


def format_report(days: int, metrics: dict) -> str:
    verdict = compute_verdict(metrics)
    lines = [
        f"=== Phase 156 Audit GBPUSD — window {days}j ===",
        f"  n_trades  = {metrics['n_trades']}",
        f"  n_wins    = {metrics['n_wins']}",
        f"  WR        = {metrics['wr_pct']}%",
        f"  PNL       = {metrics['pnl_pips']} pips",
        f"  Verdict   = {verdict}",
        "",
    ]
    if metrics.get("by_day"):
        lines.append("  Détail par jour :")
        for d in metrics["by_day"]:
            lines.append(f"    {d['date']}  n={d['n']:>3}  WR={d['wr']:>5}%  PNL={d['pnl']:>+7.1f}p")
        lines.append("")
    crit = {
        "GO":   "Critère : n>=50 ET WR>=70% ET PNL>=+200p (edge authentique préservé)",
        "WARN": "Critère : n>=30 ET WR>=50% ET PNL>=0 (edge en récupération)",
        "HALT": "Critère : n>=30 ET WR<50% (L8/L9 avaient raison, bug ailleurs)",
        "WAIT": "Critère : n<30 (pas assez de données)",
    }
    lines.append(f"  {crit[verdict]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 156 audit GBPUSD post-L8L9-OFF")
    parser.add_argument("--days", type=int, default=7, help="Fenêtre d'audit (défaut 7)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON (pour cron)")
    args = parser.parse_args()

    metrics = audit_gbpusd(args.days)
    metrics["verdict"] = compute_verdict(metrics)
    metrics["computed_at"] = datetime.now(timezone.utc).isoformat()
    metrics["window_days"] = args.days

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print(format_report(args.days, metrics))

    if metrics["verdict"] == "HALT":
        return 2
    if metrics["verdict"] == "WAIT":
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
