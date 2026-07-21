#!/usr/bin/env python
"""v9_cvd_sentinel.py — Surveillance live 6/6 flux CVD M1 (PowerFlow V9).

Vérifie que les 6 paires M1 ont un flux CVD tick-level non-nul sur les
15 dernières minutes. Émet une alerte Telegram si une paire tombe à
couverture < 80% (seuil --threshold, défaut 80%).

Doctrine : R4 (données stale rejetées), R8 (doc/trace à chaque livraison),
R13 (observer d'abord, agir ensuite — alerte seule, pas d'auto-réparation).

Usage :
    python scripts/v9_cvd_sentinel.py                       # check seul, exit 0/1
    python scripts/v9_cvd_sentinel.py --json                # sortie JSON
    python scripts/v9_cvd_sentinel.py --alert-telegram      # alerte si KO
    python scripts/v9_cvd_sentinel.py --threshold 80        # seuil % (défaut 80)
    python scripts/v9_cvd_sentinel.py --window-min 15       # fenêtre minutes (défaut 15)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"
EXPECTED_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(window_min: int, threshold_pct: float) -> dict:
    """Retourne un dict par paire : n_total, n_cvd, coverage_pct, status."""
    if not DB_PATH.exists():
        return {"error": f"DB introuvable: {DB_PATH}"}
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT symbol,
                   COUNT(*) AS n_total,
                   COUNT(cvd_delta) AS n_cvd,
                   MAX(timestamp) AS last_ts
            FROM forces_snapshots
            WHERE timestamp > datetime('now', ?)
              AND timeframe = 'M1'
            GROUP BY symbol
            """,
            (f"-{window_min} minutes",),
        ).fetchall()
    finally:
        conn.close()

    by_symbol = {r[0]: {"n_total": r[1], "n_cvd": r[2], "last_ts": r[3]} for r in rows}
    report = {}
    for sym in EXPECTED_PAIRS:
        d = by_symbol.get(sym, {"n_total": 0, "n_cvd": 0, "last_ts": None})
        n_total = d["n_total"]
        n_cvd = d["n_cvd"]
        coverage = (100.0 * n_cvd / n_total) if n_total > 0 else 0.0
        status = "OK" if coverage >= threshold_pct else "KO"
        report[sym] = {
            "n_total": n_total,
            "n_cvd": n_cvd,
            "coverage_pct": round(coverage, 1),
            "last_ts": d["last_ts"],
            "status": status,
        }

    n_ok = sum(1 for v in report.values() if v["status"] == "OK")
    return {
        "checked_at": _now_iso(),
        "window_min": window_min,
        "threshold_pct": threshold_pct,
        "pairs_expected": EXPECTED_PAIRS,
        "pairs_alive": n_ok,
        "pairs_total": len(EXPECTED_PAIRS),
        "global_status": "OK" if n_ok == len(EXPECTED_PAIRS) else "DEGRADED",
        "details": report,
    }


def _send_telegram(text: str) -> bool:
    """Envoi best-effort via le notifier (évite recursion via subprocess)."""
    try:
        import subprocess

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "v9_telegram_notifier.py"), "--send-text", text],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception as e:  # pragma: no cover
        print(f"[WARN] Telegram send failed: {e}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="V9 CVD Sentinel — surveillance 6/6 flux M1")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--alert-telegram", action="store_true", help="alerte Telegram si KO")
    parser.add_argument("--threshold", type=float, default=80.0, help="seuil couverture %% (défaut 80)")
    parser.add_argument("--window-min", type=int, default=15, help="fenêtre minutes (défaut 15)")
    args = parser.parse_args()

    report = check(args.window_min, args.threshold)
    exit_code = 0 if report.get("global_status") == "OK" else 1

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"CVD Sentinel — {report.get('checked_at')}")
        print(f"Paires vivantes : {report.get('pairs_alive')}/{report.get('pairs_total')} "
              f"(seuil {args.threshold}% / fenêtre {args.window_min}min)")
        print(f"Statut global : {report.get('global_status')}")
        for sym, d in report.get("details", {}).items():
            mark = "🟢" if d["status"] == "OK" else "🔴"
            print(f"  {mark} {sym}: {d['n_cvd']}/{d['n_total']} = {d['coverage_pct']}% "
                  f"(last={d['last_ts']})")

    if args.alert_telegram and report.get("global_status") != "OK":
        kos = [f"{s} ({d['coverage_pct']}%)" for s, d in report["details"].items() if d["status"] == "KO"]
        msg = (f"🔴 CVD Sentinel DEGRADED — {report['pairs_alive']}/{report['pairs_total']} paires OK\n"
               f"KO: {', '.join(kos)}\n"
               f"Vérifier MT4 + EA V9_Sonde_M1 sur graphiques concernés.")
        _send_telegram(msg)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
