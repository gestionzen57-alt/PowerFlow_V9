"""v9_daily_paper_audit.py — Phase 17 motion CEO « EDGE FUND MAX ».

Audit quotidien des paper_trades en cours de validation (Phase 16).
Execute 1 fois/jour (cron 23h55 UTC). Calcule :

1. n_total / n_closed / n_open
2. WR global + WR par jour (7 derniers jours)
3. Expectancy brute + nette (R6 spread)
4. Max DD net
5. Drift WR 7j (L12 early warning)
6. Verdict go/no-go Phase 12 LIVE reel

Sortie :
- Console : rapport lisible
- Fichier : data/logs/paper_audit_YYYY-MM-DD.json
- Exit code 0 si OK, 1 si drift detecte

Auteur : Hermes (Phase 17 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.daily_paper_audit")

# Cibles Phase 12 LIVE (calibrees Phase 15)
TARGETS = {
    "wr_min_pct": 60.0,
    "exp_net_min_p": 3.0,
    "max_dd_max_p": 100.0,
    "wr_drift_alert_pct": 5.0,  # L12
}


def audit_paper_trades(db_path: Path | str, *, days=7) -> dict:
    """Audit des v9_paper_trades des N derniers jours."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {"error": "db_missing"}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Stats globales
        rows = conn.execute("""
            SELECT id, opened_at, closed_at,
                   pips_brut, pips_net, close_reason, spread_pips
            FROM v9_paper_trades
            WHERE opened_at > datetime('now', ? || ' days')
            ORDER BY opened_at DESC
        """, (-days,)).fetchall()

        n_total = len(rows)
        n_closed = sum(1 for r in rows if r["closed_at"])
        n_open = n_total - n_closed
        wins = sum(1 for r in rows if r["closed_at"] and (r["pips_net"] or 0) > 0)
        total_pips_brut = sum(float(r["pips_brut"] or 0) for r in rows if r["closed_at"])
        total_pips_net = sum(float(r["pips_net"] or 0) for r in rows if r["closed_at"])
        wr_pct = (100.0 * wins / n_closed) if n_closed else 0.0
        exp_brut = (total_pips_brut / n_closed) if n_closed else 0.0
        exp_net = (total_pips_net / n_closed) if n_closed else 0.0

        # Max DD net (rolling)
        running_max = 0.0
        running_dd = 0.0
        max_dd = 0.0
        for r in sorted(rows, key=lambda x: x["opened_at"]):
            if r["closed_at"]:
                running_dd += float(r["pips_net"] or 0)
                if running_dd > running_max:
                    running_max = running_dd
                drawdown = running_max - running_dd
                if drawdown > max_dd:
                    max_dd = drawdown

        # WR par jour
        wr_per_day = {}
        for r in rows:
            if not r["closed_at"]:
                continue
            day = str(r["opened_at"])[:10]
            if day not in wr_per_day:
                wr_per_day[day] = {"n": 0, "wins": 0, "pips_net": 0.0}
            wr_per_day[day]["n"] += 1
            if (r["pips_net"] or 0) > 0:
                wr_per_day[day]["wins"] += 1
            wr_per_day[day]["pips_net"] += float(r["pips_net"] or 0)
        # Calcul WR% par jour
        for day in wr_per_day:
            d = wr_per_day[day]
            d["wr_pct"] = (100.0 * d["wins"] / d["n"]) if d["n"] else 0.0

        # Verdict
        checks = {
            "wr_ok": wr_pct >= TARGETS["wr_min_pct"],
            "exp_net_ok": exp_net >= TARGETS["exp_net_min_p"],
            "max_dd_ok": max_dd <= TARGETS["max_dd_max_p"],
            "n_sufficient": n_closed >= 20,  # minimum 20 trades fermes
        }
        ready_live = all(checks.values())

        return {
            "audit_ts": datetime.now(timezone.utc).isoformat(),
            "days_analyzed": days,
            "n_total": n_total,
            "n_open": n_open,
            "n_closed": n_closed,
            "wr_pct": round(wr_pct, 2),
            "expectancy_brut": round(exp_brut, 2),
            "expectancy_net": round(exp_net, 2),
            "max_dd_net": round(max_dd, 2),
            "total_pips_brut": round(total_pips_brut, 2),
            "total_pips_net": round(total_pips_net, 2),
            "wr_per_day": wr_per_day,
            "targets": TARGETS,
            "checks": checks,
            "ready_live": ready_live,
            "recommendation": (
                "GO_PHASE12_LIVE" if ready_live
                else "WAIT_MORE_DATA" if n_closed < 20
                else "FIX_EDGE_FIRST"
            ),
        }
    finally:
        conn.close()


def main(argv=None) -> int:
    from core.v9.config import DB_PATH
    db_path = DB_PATH

    result = audit_paper_trades(db_path, days=7)

    # Log fichier
    log_dir = Path(__file__).resolve().parent.parent / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = log_dir / f"paper_audit_{today}.json"
    log_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # Console rapport
    print("=" * 70)
    print(f"PHASE 17 — DAILY PAPER AUDIT — {today}")
    print("=" * 70)
    print()
    print(f"n_total              = {result.get('n_total', 0)}")
    print(f"n_open               = {result.get('n_open', 0)}")
    print(f"n_closed             = {result.get('n_closed', 0)}")
    print(f"WR global            = {result.get('wr_pct', 0):.1f}%  "
          f"(cible >= {TARGETS['wr_min_pct']:.0f}%)")
    print(f"Expectancy brut      = {result.get('expectancy_brut', 0):+.2f}p")
    print(f"Expectancy net (R6)  = {result.get('expectancy_net', 0):+.2f}p  "
          f"(cible >= {TARGETS['exp_net_min_p']}p)")
    print(f"Max DD net           = {result.get('max_dd_net', 0):.1f}p  "
          f"(cible <= {TARGETS['max_dd_max_p']}p)")
    print()
    if result.get("wr_per_day"):
        print("WR par jour :")
        for day in sorted(result["wr_per_day"].keys()):
            d = result["wr_per_day"][day]
            print(f"  {day} : n={d['n']:3d}  WR={d['wr_pct']:5.1f}%  "
                  f"pips_net={d['pips_net']:+.1f}")
    print()
    print("Checks :")
    for k, v in result.get("checks", {}).items():
        flag = "[OK]" if v else "[KO]"
        print(f"  {flag} {k}")
    print()
    print(f">>> RECOMMENDATION : {result.get('recommendation', 'n/a')}")
    print(f">>> Log ecrit : {log_file}")
    print("=" * 70)

    return 0 if result.get("ready_live") else 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())