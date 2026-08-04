"""
V10 — Phase A Audit orchestrator.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Exécute WFOOS + Monte Carlo + Deflated Sharpe + Stress Test → rapport JSON.

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_phase_a_audit.py
  .venv/Scripts/python.exe scripts/v10_phase_a_audit.py --json
  .venv/Scripts/python.exe scripts/v10_phase_a_audit.py --json --output docs/V10/audit_2026_08.json
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
OUTPUT_DEFAULT = ROOT / "docs" / "V10" / "audit_latest.json"


def run_script(name: str, args: list[str] | None = None) -> dict[str, Any]:
    """Exécute un script v10_*.py avec --json et retourne le résultat."""
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
    parser = argparse.ArgumentParser(description="V10 Phase A Audit orchestrator")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--output", default=None, help="Fichier sortie (default: docs/V10/audit_latest.json)")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else OUTPUT_DEFAULT

    print("🔬 V10 Phase A Audit — orchestrateur", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # 1. WFOOS (auto-retry si données insuffisantes)
    print("  [1/4] WFOOS (auto)...", file=sys.stderr)
    wfoos = run_script("v10_wfoos.py", ["--window", "7", "--oos", "7", "--auto"])
    if "error" in wfoos and "Données insuffisantes" in wfoos.get("error", ""):
        # Retry avec window=3, oos=3
        wfoos = run_script("v10_wfoos.py", ["--window", "3", "--oos", "3"])

    # 2. Monte Carlo
    print("  [2/4] Monte Carlo (10k)...", file=sys.stderr)
    mc = run_script("v10_monte_carlo.py", ["--n", "10000"])

    # 3. Deflated Sharpe
    print("  [3/4] Deflated Sharpe (50 trials)...", file=sys.stderr)
    dsr = run_script("v10_deflated_sharpe.py", ["--n-trials", "50"])

    # 4. Stress Test
    print("  [4/4] Stress Test (5 scénarios)...", file=sys.stderr)
    stress = run_script("v10_stress_test.py")

    # Synthèse
    verdicts = [
        wfoos.get("verdict", "ERROR"),
        mc.get("verdict", "ERROR"),
        dsr.get("verdict", "ERROR"),
        stress.get("verdict", "ERROR"),
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
        "phase": "A — Audit statistique",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict_global": global_verdict,
        "verdicts": verdicts,
        "summary": {
            "n_go": n_go,
            "n_hold": n_hold,
            "n_nogo": n_nogo,
            "n_total": len(verdicts),
        },
        "wfoos": wfoos,
        "monte_carlo": mc,
        "deflated_sharpe": dsr,
        "stress_test": stress,
        "kill_criteria_summary": (
            f"GO: {n_go} | HOLD: {n_hold} | NO-GO: {n_nogo} | "
            f"Global: {global_verdict}"
        ),
        "next_step": (
            "Phase B (Risk Management institutionnel)"
            if global_verdict == "GO"
            else "KILL — corrigez les 4 axes avant Phase B"
            if global_verdict == "NO-GO"
            else "HOLD — analysez les résultats mitigés"
        ),
    }

    # Sauvegarde
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("=" * 70)
        print(f"  WFOOS       : {wfoos.get('verdict', 'ERROR')}  (Sharpe OOS={wfoos.get('synthese', {}).get('avg_oos_sharpe', 'N/A')})")
        print(f"  Monte Carlo : {mc.get('verdict', 'ERROR')}  (Sharpe median={mc.get('sharpe', {}).get('median', 'N/A')})")
        print(f"  Deflated SR : {dsr.get('verdict', 'ERROR')}  (DSR={dsr.get('deflated_sharpe', {}).get('dsr', 'N/A')})")
        print(f"  Stress Test : {stress.get('verdict', 'ERROR')}  (survies={stress.get('n_survives', 'N/A')}/{stress.get('n_scenarios', 'N/A')})")
        print("=" * 70)
        print(f"  VERDICT GLOBAL : {global_verdict}")
        print(f"  → {report['next_step']}")
        print(f"  → Rapport sauvé : {output_path}")
        print("=" * 70)

    return 0 if global_verdict == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())