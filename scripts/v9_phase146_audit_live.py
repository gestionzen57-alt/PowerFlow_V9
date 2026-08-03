#!/usr/bin/env python
"""
Phase 146 — Audit live vendredi (audit hebdo GBPUSD post-L8L9-OFF + L11v2).

Exécuté chaque vendredi 18:00 UTC par le cron V9Phase146AuditLive.
Produit un rapport markdown + verdict GO/WARN/HALT/WAIT sur la semaine.

Doctrine :
  R2 additif (nouveau script, 0 modif core/)
  R6 fail-open
  R14 audit SQL live
"""
from __future__ import annotations

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


def audit_gbpusd_week() -> dict:
    """Calcule n, WR, PNL par jour pour la semaine en cours (7j glissants)."""
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
            WHERE opened_at > datetime('now', '-7 days')
              AND substr(snapshot_id, 3, 6) = '-GBPUS'
            """,
        ).fetchone()
        by_day = conn.execute(
            """
            SELECT
              CASE strftime('%w', opened_at)
                WHEN '0' THEN 'Dimanche' WHEN '1' THEN 'Lundi'
                WHEN '2' THEN 'Mardi' WHEN '3' THEN 'Mercredi'
                WHEN '4' THEN 'Jeudi' WHEN '5' THEN 'Vendredi'
                WHEN '6' THEN 'Samedi'
              END jour,
              COUNT(*) n,
              ROUND(100.0 * SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) wr,
              ROUND(SUM(pips_simulated), 1) pnl
            FROM paper_trades
            WHERE opened_at > datetime('now', '-7 days')
              AND substr(snapshot_id, 3, 6) = '-GBPUS'
            GROUP BY strftime('%w', opened_at)
            """,
        ).fetchall()
        return {
            "n_trades": row[0] or 0,
            "n_wins": row[1] or 0,
            "wr_pct": row[2] or 0.0,
            "pnl_pips": row[3] or 0.0,
            "by_day": [{"jour": j, "n": n, "wr": wr, "pnl": pnl} for j, n, wr, pnl in by_day],
        }
    except Exception as e:
        return {"n_trades": 0, "n_wins": 0, "wr_pct": 0.0, "pnl_pips": 0.0, "by_day": [], "error": str(e)}
    finally:
        if conn is not None:
            conn.close()


def main() -> int:
    week = audit_gbpusd_week()
    n, wr, pnl = week["n_trades"], week["wr_pct"], week["pnl_pips"]
    if n < 5:
        verdict = "WAIT"
    elif n >= 30 and wr >= 70 and pnl >= 100:
        verdict = "GO"
    elif n >= 15 and wr >= 50:
        verdict = "WARN"
    else:
        verdict = "HALT"

    out = _ROOT / "docs" / "audits" / f"PHASE146_AUDIT_LIVE_{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Phase 146 — Audit Live GBPUSD (semaine glissante 7j)",
        f"",
        f"**Date d'exécution** : {datetime.now(timezone.utc).isoformat()}",
        f"**Verdict** : {verdict}",
        f"",
        f"## Métriques globales",
        f"",
        f"| Métrique | Valeur |",
        f"|---|---|",
        f"| n_trades | {n} |",
        f"| n_wins | {week['n_wins']} |",
        f"| WR | {wr}% |",
        f"| PNL | {pnl} pips |",
        f"| Verdict | **{verdict}** |",
        f"",
        f"## Détail par jour",
        f"",
        f"| Jour | n | WR | PNL |",
        f"|---|---|---|---|",
    ]
    for d in week.get("by_day", []):
        lines.append(f"| {d['jour']} | {d['n']} | {d['wr']}% | {d['pnl']:+.1f}p |")
    lines.append("")
    lines.append("## Critères")
    lines.append("")
    lines.append("- GO : n>=30 ET WR>=70% ET PNL>=+100p")
    lines.append("- WARN : n>=15 ET WR>=50%")
    lines.append("- HALT : n>=5 ET WR<50%")
    lines.append("- WAIT : n<5")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Verdict {verdict} : n={n} WR={wr}% PNL={pnl}p")
    print(f"Rapport : {out}")
    return 0 if verdict != "HALT" else 2


if __name__ == "__main__":
    sys.exit(main())
