#!/usr/bin/env python3
"""run_mt4_health.py — Health check MT4 bridge + flux snapshots (Z10, 2026-08-10).

Vérifie 3 piliers :
  1. Port 31685 (bridge MT4) — écoute ?
  2. Fraîcheur DB forces_snapshots — delta entre MAX(bar_time) et now
     (seuils miroirs de core/v9/config.py:STALE_THRESHOLDS_MS). Le serveur
     MT4 peut être en avance (skew horloge) → tolérance future ± 60s.
  3. Couverture 6 paires majeures (EURUSD/GBPUSD/USDJPY/USDCAD/USDCHF/AUDUSD).

R6 fail-open : toute erreur → health partielle, jamais de crash.
R9 : rapport JSON complet + audit. R10 : lecture seule (compute only).

Usage :
    python scripts/run_mt4_health.py            # console
    python scripts/run_mt4_health.py --json     # JSON seul
    python scripts/run_mt4_health.py --report   # écrit reports/mt4_health_<date>.json

Exit codes : 0 = OK, 1 = STALE ou couverture incomplète, 2 = ERREUR.
"""
from __future__ import annotations

import argparse
import json
import socket
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

REPORTS_DIR = ROOT_DIR / "reports"
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"

MT4_PORT = 31685
MT4_HOST = "127.0.0.1"

# 6 paires majeures V9 (miroir de la spec Z10)
MAJOR_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD"]

# Tolérance de fraîcheur par défaut (spec Z10 : delta > 120s → stale).
# Le serveur MT4 peut être en avance (skew d'horloge) → tolérance future 60s.
STALE_DELTA_S = 120
CLOCK_SKEW_TOLERANCE_S = 60


def check_port(host: str = MT4_HOST, port: int = MT4_PORT,
               timeout: float = 2.0) -> dict:
    """Ping TCP du bridge MT4 (R6 fail-open)."""
    out = {"port": port, "host": host, "listening": False, "pid": None,
           "error": None}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            out["listening"] = True
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def check_freshness(db_path: Path, stale_delta_s: int = STALE_DELTA_S) -> dict:
    """Fraîcheur des snapshots : MAX(bar_time) vs now (R6 fail-open)."""
    out = {"stale": False, "max_bar_time": None, "max_bar_time_utc": None,
           "age_s": None, "stale_delta_s": stale_delta_s, "error": None}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        try:
            row = con.execute(
                "SELECT MAX(bar_time) FROM forces_snapshots"
            ).fetchone()
        finally:
            con.close()
        if not row or row[0] is None:
            out["error"] = "no_snapshots"
            return out
        max_bt = int(row[0])
        now = datetime.now(timezone.utc)
        age_s = now.timestamp() - max_bt
        # Tolérance future : clock skew serveur MT4 (± 60s) n'est pas du stale
        out["max_bar_time"] = max_bt
        out["max_bar_time_utc"] = datetime.fromtimestamp(
            max_bt, timezone.utc).isoformat(timespec="seconds")
        out["age_s"] = int(age_s)
        out["stale"] = age_s > stale_delta_s + CLOCK_SKEW_TOLERANCE_S
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["stale"] = True  # R6 : indéterminé = traité comme stale (warning)
    return out


def check_pairs(db_path: Path) -> dict:
    """Couverture des 6 paires majeures dans forces_snapshots (R6 fail-open)."""
    out = {"pairs": {}, "missing": [], "error": None}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        try:
            rows = con.execute(
                "SELECT symbol, COUNT(*) AS n FROM forces_snapshots "
                "GROUP BY symbol"
            ).fetchall()
        finally:
            con.close()
        present = {r[0]: r[1] for r in rows}
        for pair in MAJOR_PAIRS:
            n = present.get(pair, 0)
            out["pairs"][pair] = {"present": n > 0, "n_snapshots": n}
            if n == 0:
                out["missing"].append(pair)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["missing"] = list(MAJOR_PAIRS)
    return out


def build_health() -> dict:
    """Assemble le rapport complet Z10 (R6 fail-open global)."""
    report: dict = {
        "report": "mt4_health",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "doctrine": {"r6": "fail-open", "r9": "audit traçable", "r10": "lecture seule"},
    }
    try:
        port = check_port()
        fresh = check_freshness(DB_PATH)
        pairs = check_pairs(DB_PATH)
        report["port"] = port
        report["freshness"] = fresh
        report["pairs"] = pairs
        report["pairs_ok"] = not pairs["missing"]
        report["stale"] = bool(fresh["stale"])
        # Verdict : port + fraîcheur + couverture
        if fresh.get("error") and fresh.get("error") == "no_snapshots":
            report["verdict"] = "ERROR_NO_DATA"
        elif port["listening"] and not fresh["stale"] and not pairs["missing"]:
            report["verdict"] = "OK"
        else:
            report["verdict"] = "STALE_OR_INCOMPLETE"
        report["meta"] = {
            "db_path": str(DB_PATH),
            "stale_delta_s": STALE_DELTA_S,
            "clock_skew_tolerance_s": CLOCK_SKEW_TOLERANCE_S,
            "error": None,
        }
    except Exception as exc:  # R6 fail-open ultime
        report["port"] = {"listening": False, "error": "unknown"}
        report["freshness"] = {"stale": True, "error": "unknown"}
        report["pairs"] = {"missing": list(MAJOR_PAIRS), "error": "unknown"}
        report["pairs_ok"] = False
        report["stale"] = True
        report["verdict"] = "AUDIT_ERROR"
        report["meta"] = {"error": f"{type(exc).__name__}: {exc}"}
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="MT4 Health Check V10 (Z10)")
    ap.add_argument("--json", action="store_true", help="sortie JSON seule")
    ap.add_argument("--report", action="store_true",
                    help="écrit reports/mt4_health_<YYYY_MM_DD>.json")
    args = ap.parse_args()

    report = build_health()

    if args.report:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = report["date"].replace("-", "_")
        out_path = REPORTS_DIR / f"mt4_health_{stamp}.json"
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"[run_mt4_health] rapport écrit : {out_path}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"verdict      : {report['verdict']}")
        print(f"port         : {report['port'].get('listening')} "
              f"({report['port'].get('host')}:{report['port'].get('port')})")
        f = report["freshness"]
        print(f"freshness    : max_bar_time={f.get('max_bar_time_utc')} "
              f"age_s={f.get('age_s')} stale={f.get('stale')}")
        print(f"pairs        : {6 - len(report['pairs'].get('missing', []))}/6 "
              f"missing={report['pairs'].get('missing')}")

    # Exit codes : 0 OK, 1 stale/incomplet, 2 erreur
    v = report["verdict"]
    if v == "OK":
        return 0
    if v in ("STALE_OR_INCOMPLETE", "ERROR_NO_DATA"):
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
