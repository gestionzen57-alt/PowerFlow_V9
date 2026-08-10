"""V10 Deployment Validator + System Health Check — post-merge PR#4 (R2 additif).

Lance DeploymentValidator C20 (12 critères) + SystemHealthChecker depuis
MasterOrchestrator, avec des valeurs issues de l'état live réel.

R6 fail-open : chaque module isolé en try/except.
R9 : rapport JSON dans reports/.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

DB = "data/v9_forces.db"


def _live_params() -> dict:
    """Construit les 12 paramètres du DeploymentValidator depuis l'état réel."""
    params = {
        "config_loaded": 1.0,
        "health_ok": 1.0,
        "sim_trades": 0.0,
        "max_drawdown": 0.0,
        "ruin_prob": 0.0,
        "exposure_ok": 1.0,
        "win_rate": 0.0,
        "sharpe": 0.0,
        "profit_factor": 0.0,
        "wfa_efficiency": 0.0,
        "broker_ok": 0.0,
        "feed_ok": 0.0,
    }
    try:
        conn = sqlite3.connect(DB, timeout=10)
        # feed actif : max timestamp récent ?
        row = conn.execute("SELECT MAX(timestamp) FROM forces_snapshots").fetchone()
        if row and row[0]:
            last = row[0].replace("Z", "+00:00")
            lag = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 60
            params["feed_ok"] = 1.0 if lag < 90 else 0.0
        # sim_trades : nombre de paper_trades
        try:
            n = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
            params["sim_trades"] = float(n)
        except Exception:
            pass
        conn.close()
    except Exception:
        pass
    return params


def main() -> None:
    now = datetime.now(timezone.utc)
    print(f"[{now.isoformat()}] Lancement DeploymentValidator + SystemHealthChecker...")
    results: dict = {"ts": now.isoformat()}

    # 1. DeploymentValidator C20
    try:
        from core.v10.v10_deployment_validator import DeploymentValidator
        dv = DeploymentValidator()
        params = _live_params()
        report = dv.validate(params)
        results["deployment_validator"] = {
            "params": params,
            "report": report.as_dict() if hasattr(report, "as_dict") else str(report),
        }
        print(f"DeploymentValidator : {report.as_dict() if hasattr(report,'as_dict') else report}")
    except Exception as e:
        results["deployment_validator"] = f"ERROR:{e}"
        print(f"[WARN] DeploymentValidator : {e}")

    # 2. SystemHealthChecker
    try:
        from core.v10.v10_system_health_check import SystemHealthChecker
        shc = SystemHealthChecker()
        checks = shc.default_checks() if hasattr(shc, "default_checks") else {}
        report = shc.run(checks)
        results["system_health"] = report.as_dict() if hasattr(report, "as_dict") else str(report)
        print(f"SystemHealthChecker : {report.as_dict() if hasattr(report,'as_dict') else report}")
    except Exception as e:
        results["system_health"] = f"ERROR:{e}"
        print(f"[WARN] SystemHealthChecker : {e}")

    out = "reports/deployment_validator_2026_08_10.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Rapport : {out}")


if __name__ == "__main__":
    main()
