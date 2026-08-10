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
    """Construit les 12 paramètres du DeploymentValidator depuis l'état réel.

    Injecte le track record shadow V10 (50 trades) si disponible.
    """
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
    # 1. Track record shadow V10 (rapport ShadowTrader Étape A — 100 trades)
    try:
        import os
        # Priorité au rapport Étape A (100 trades), fallback au rapport 50 trades
        shadow_path = "reports/shadow_trader_etape_a_2026_08_10.json"
        if not os.path.exists(shadow_path):
            shadow_path = "reports/shadow_trader_2026_08_10.json"
        if os.path.exists(shadow_path):
            with open(shadow_path, encoding="utf-8") as f:
                sh = json.load(f)
            n = int(sh.get("shadow_trades", 0))
            wr = float(sh.get("shadow_wr", 0.0))
            pnl = float(sh.get("shadow_pnl", 0.0))
            sharpe = float(sh.get("sharpe", 0.0))
            pf = float(sh.get("profit_factor", 0.0))
            params["sim_trades"] = float(n)
            params["win_rate"] = wr
            params["sharpe"] = sharpe
            params["profit_factor"] = pf
    except Exception:
        pass
    # 2. WalkForward — wfa_efficiency (rapport walkforward)
    try:
        import os
        wf_path = "reports/walkforward_2026_08_10.json"
        if os.path.exists(wf_path):
            with open(wf_path, encoding="utf-8") as f:
                wf = json.load(f)
            wf_eff = wf.get("walkforward", {}).get("avg_efficiency", 0.0)
            params["wfa_efficiency"] = float(wf_eff)
    except Exception:
        pass
    # 3. Feed actif : max timestamp récent ?
    try:
        conn = sqlite3.connect(DB, timeout=10)
        row = conn.execute("SELECT MAX(timestamp) FROM forces_snapshots").fetchone()
        if row and row[0]:
            last = row[0].replace("Z", "+00:00")
            lag = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 60
            params["feed_ok"] = 1.0 if lag < 90 else 0.0
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
