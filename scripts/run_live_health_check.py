#!/usr/bin/env python3
"""run_live_health_check.py — Health check live V10 en 6 couches (Z-HEALTH).

6 couches :
  1. broker        — bridge IBKR (port 7497 paper) joignable
  2. spread        — spread moyen M5 <= seuil (défaut 10 points)
  3. data_gap      — validate_data_continuity (trous > 2.5× barre) → OK/WARN
  4. latency       — temps de réponse DB (SELECT) < 80 ms
  5. session_active— qualité de session courante (get_session_quality)
  6. live_readiness— audit C11 (Sharpe/WR/DD sur track record)

Score global = moyenne des couches (0-100). Score < 90 → status DEGRADED.
Rapport JSON : reports/health_report_{ts}.json (R9).
R6 fail-open : chaque check isolé, une erreur → couche à 0 avec error,
jamais de crash. R10 : lecture seule (compute only).

Usage :
    python scripts/run_live_health_check.py            # console
    python scripts/run_live_health_check.py --json     # JSON seul
    python scripts/run_live_health_check.py --report   # écrit le rapport

Exit codes : 0 = HEALTHY, 1 = DEGRADED, 2 = ERREUR.
"""
from __future__ import annotations

import argparse
import json
import socket
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "reports"
DB_PATH = ROOT / "data" / "v9_forces.db"

# Seuils (R8 surchargeables)
SPREAD_MAX_POINTS = 10.0
LATENCY_MAX_MS = 80.0
SCORE_DEGRADED = 90.0
IBKR_HOST = "127.0.0.1"
IBKR_PORT = 7497  # paper (7496 live)
PAIR_REF = "EURUSD"
TF_REF = "M5"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_broker(host: str = IBKR_HOST, port: int = IBKR_PORT,
                 timeout: float = 2.0) -> dict:
    """Couche 1 — bridge IBKR joignable (R6 fail-open)."""
    out = {"ok": False, "score": 0.0, "detail": {"host": host, "port": port},
           "error": None}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            out["ok"] = True
            out["score"] = 100.0
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def check_spread(db_path: Path, max_points: float = SPREAD_MAX_POINTS) -> dict:
    """Couche 2 — spread moyen M5 <= seuil (R6 fail-open)."""
    out = {"ok": False, "score": 0.0, "detail": {}, "error": None}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        try:
            row = con.execute(
                "SELECT AVG(spread_points), COUNT(*) FROM forces_snapshots "
                "WHERE timeframe='M5' AND is_closed_bar=1"
            ).fetchone()
        finally:
            con.close()
        avg = float(row[0] or 0.0)
        n = int(row[1] or 0)
        out["detail"] = {"avg_spread_points": round(avg, 2), "n_snapshots": n}
        if n == 0:
            out["error"] = "no_snapshots"
            return out
        out["ok"] = avg <= max_points
        out["score"] = 100.0 if out["ok"] else max(0.0, 100.0 - (avg - max_points) * 5.0)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def check_data_gap(db_path: Path, pair: str = PAIR_REF, tf: str = TF_REF) -> dict:
    """Couche 3 — continuité des données (trous > 2.5× barre)."""
    out = {"ok": False, "score": 0.0, "detail": {}, "error": None}
    try:
        from core.v10.v10_data_gap_validator import validate_data_continuity
        report = validate_data_continuity(str(db_path), pair, tf)
        rec = report.recommendation
        out["detail"] = {
            "pair": pair, "tf": tf,
            "recommendation": rec,
            "total_gap_hours": round(report.total_gap_hours, 2),
            "n_gaps": len(report.gaps),
        }
        out["ok"] = rec in ("OK", "WARN")
        out["score"] = 100.0 if rec == "OK" else (60.0 if rec == "WARN" else 0.0)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def check_latency(db_path: Path, max_ms: float = LATENCY_MAX_MS) -> dict:
    """Couche 4 — latence DB (SELECT) < 80 ms (R6 fail-open)."""
    out = {"ok": False, "score": 0.0, "detail": {}, "error": None}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
        try:
            t0 = time.perf_counter()
            con.execute("SELECT COUNT(*) FROM forces_snapshots").fetchone()
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
        finally:
            con.close()
        out["detail"] = {"latency_ms": round(elapsed_ms, 2), "max_ms": max_ms}
        out["ok"] = elapsed_ms < max_ms
        out["score"] = 100.0 if out["ok"] else max(0.0, 100.0 - (elapsed_ms - max_ms) * 2.0)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def check_session_active(pair: str = PAIR_REF) -> dict:
    """Couche 5 — session courante active (get_session_quality)."""
    out = {"ok": False, "score": 0.0, "detail": {}, "error": None}
    try:
        from core.v10.v10_session_filter import get_session_quality
        q = get_session_quality(pair)
        score = float(getattr(q, "score", 0.0) or 0.0)
        out["detail"] = {
            "pair": pair,
            "session": str(getattr(q, "session", "UNKNOWN")),
            "score": round(score, 3),
            "is_optimal": bool(getattr(q, "is_optimal_for_pair", False)),
        }
        out["ok"] = score >= 0.5
        out["score"] = round(score * 100.0, 1)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def check_live_readiness() -> dict:
    """Couche 6 — audit C11 LiveReadiness (Sharpe/WR/DD)."""
    out = {"ok": False, "score": 0.0, "detail": {}, "error": None}
    try:
        from core.v10.v10_live_readiness import audit_live_readiness
        r = audit_live_readiness({})  # track record vide → gates évalués
        gates = dict(getattr(r, "gates", {}))
        n_ok = sum(1 for v in gates.values() if v is True)
        n_total = max(len(gates), 1)
        out["detail"] = {
            "live_ready": bool(getattr(r, "live_ready", False)),
            "reason": str(getattr(r, "reason", "NOT_EVALUATED")),
            "sharpe": round(float(getattr(r, "sharpe", 0.0)), 3),
            "wr": round(float(getattr(r, "wr", 0.0)), 3),
            "n_trades": int(getattr(r, "n_trades", 0)),
            "gates": gates,
        }
        out["ok"] = bool(getattr(r, "live_ready", False))
        out["score"] = round(n_ok / n_total * 100.0, 1)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def build_health() -> dict:
    """Assemble le rapport 6 couches (R6 fail-open global)."""
    report = {
        "report": "live_health_check",
        "generated_at_utc": _now_iso(),
        "doctrine": {"r6": "fail-open", "r9": "audit JSON", "r10": "lecture seule"},
        "layers": {},
        "score": 0.0,
        "status": "ERROR",
        "meta": {"db_path": str(DB_PATH), "error": None},
    }
    try:
        layers = {
            "broker": check_broker(),
            "spread": check_spread(DB_PATH),
            "data_gap": check_data_gap(DB_PATH),
            "latency": check_latency(DB_PATH),
            "session_active": check_session_active(),
            "live_readiness": check_live_readiness(),
        }
        report["layers"] = layers
        scores = [float(l["score"]) for l in layers.values()]
        report["score"] = round(sum(scores) / len(scores), 1)
        report["status"] = "HEALTHY" if report["score"] >= SCORE_DEGRADED else "DEGRADED"
    except Exception as exc:  # R6 fail-open ultime
        report["meta"]["error"] = f"{type(exc).__name__}: {exc}"
        report["status"] = "ERROR"
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Live health check V10 — 6 couches")
    ap.add_argument("--json", action="store_true", help="sortie JSON seule")
    ap.add_argument("--report", action="store_true", help="écrit reports/health_report_<ts>.json")
    args = ap.parse_args()

    report = build_health()

    if args.report:
        REPORTS.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = REPORTS / f"health_report_{ts}.json"
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"[run_live_health_check] rapport écrit : {out_path}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"status : {report['status']} | score : {report['score']}/100")
        for name, layer in report["layers"].items():
            err = f" ERR={layer['error']}" if layer.get("error") else ""
            print(f"  {name:<16} score={layer['score']:>6.1f} ok={layer['ok']}{err}")

    return 0 if report["status"] == "HEALTHY" else (1 if report["status"] == "DEGRADED" else 2)


if __name__ == "__main__":
    sys.exit(main())
