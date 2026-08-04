"""
V10 — Phase B Risk Management orchestrator.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Exécute VaR/CVaR + Liquidity Sharpe + Risk Parity + Vol Targeting → rapport JSON.

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_phase_b_risk.py
  .venv/Scripts/python.exe scripts/v10_phase_b_risk.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
OUTPUT_DEFAULT = ROOT / "docs" / "V10" / "risk_latest.json"


def run_script(name: str, args: list[str] | None = None) -> dict[str, Any]:
    cmd = [sys.executable, str(SCRIPTS / name)]
    if args:
        cmd.extend(args)
    cmd.append("--json")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode not in (0, 1):
            return {"error": f"{name} exit {result.returncode}", "stderr": result.stderr[-500:]}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"error": f"{name} timeout 60s"}
    except json.JSONDecodeError as e:
        return {"error": f"{name} JSON decode: {e}", "stdout": result.stdout[-500:]}
    except Exception as e:
        return {"error": f"{name} exception: {e}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="V10 Phase B Risk orchestrator")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--output", default=None, help="Fichier sortie")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else OUTPUT_DEFAULT

    print("🛡️  V10 Phase B Risk Management — orchestrateur", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    print("  [1/4] VaR/CVaR 95%...", file=sys.stderr)
    var_cvar = run_script("v10_var_cvar.py", ["--confidence", "0.95"])

    print("  [2/4] Liquidity Sharpe...", file=sys.stderr)
    liquidity = run_script("v10_liquidity_sharpe.py", ["--spread", "1.5", "--slippage", "0.5"])

    print("  [3/4] Risk Parity 2.0...", file=sys.stderr)
    risk_parity = run_script("v10_risk_parity.py")

    print("  [4/4] Vol Targeting 8%...", file=sys.stderr)
    vol_targeting = run_script("v10_vol_targeting.py", ["--target", "0.08"])

    verdicts = [
        var_cvar.get("verdict", "ERROR"),
        liquidity.get("verdict", "ERROR"),
        risk_parity.get("verdict", "ERROR"),
        vol_targeting.get("verdict", "ERROR"),
    ]

    n_go = sum(1 for v in verdicts if v == "GO")
    n_nogo = sum(1 for v in verdicts if v == "NO-GO")
    n_hold = sum(1 for v in verdicts if v == "HOLD")

    if n_nogo == 0 and n_go >= 3:
        global_verdict = "GO"
    elif n_nogo >= 3:
        global_verdict = "NO-GO"
    else:
        global_verdict = "HOLD"

    report = {
        "phase": "B — Risk Management institutionnel",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict_global": global_verdict,
        "verdicts": verdicts,
        "summary": {"n_go": n_go, "n_hold": n_hold, "n_nogo": n_nogo, "n_total": len(verdicts)},
        "var_cvar": var_cvar,
        "liquidity_sharpe": liquidity,
        "risk_parity": risk_parity,
        "vol_targeting": vol_targeting,
        "next_step": (
            "Phase C (Exécution microstructure)"
            if global_verdict == "GO"
            else "KILL — corrigez le risk management avant Phase C"
            if global_verdict == "NO-GO"
            else "HOLD — analysez les résultats mitigés"
        ),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print(f"  VaR/CVaR        : {var_cvar.get('verdict', 'ERROR')}  (VaR95={var_cvar.get('var', {}).get('historique', 'N/A')})")
        print(f"  Liquidity Sharpe: {liquidity.get('verdict', 'ERROR')}  (adj={liquidity.get('sharpe_liquidity_adjusted', 'N/A')})")
        print(f"  Risk Parity     : {risk_parity.get('verdict', 'ERROR')}  (corr={risk_parity.get('avg_correlation', 'N/A')})")
        print(f"  Vol Targeting   : {vol_targeting.get('verdict', 'ERROR')}  (scale={vol_targeting.get('scale', 'N/A')})")
        print("=" * 70)
        print(f"  VERDICT GLOBAL : {global_verdict}")
        print(f"  → {report['next_step']}")
        print(f"  → Rapport sauvé : {output_path}")
        print("=" * 70)

    return 0 if global_verdict == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())