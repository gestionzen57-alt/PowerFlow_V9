"""
V10 — Phase D Portfolio Construction orchestrator.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Exécute Kelly + Black-Litterman + Corrélation + Risk Budget → rapport JSON.

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.
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
OUTPUT_DEFAULT = ROOT / "docs" / "V10" / "portfolio_latest.json"


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
    parser = argparse.ArgumentParser(description="V10 Phase D Portfolio orchestrator")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--output", default=None, help="Fichier sortie")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else OUTPUT_DEFAULT

    print("🏛️  V10 Phase D Portfolio — orchestrateur", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    print("  [1/4] Kelly fraction...", file=sys.stderr)
    kelly = run_script("v10_kelly.py", ["--fraction", "0.5"])

    print("  [2/4] Black-Litterman...", file=sys.stderr)
    bl = run_script("v10_black_litterman.py")

    print("  [3/4] Corrélation inter-stratégies...", file=sys.stderr)
    corr = run_script("v10_correlation.py")

    print("  [4/4] Risk budget...", file=sys.stderr)
    risk_budget = run_script("v10_risk_budget.py", ["--target-vol", "0.08", "--max-dd", "0.05"])

    verdicts = [
        kelly.get("verdict", "ERROR"),
        bl.get("verdict", "ERROR"),
        corr.get("verdict", "ERROR"),
        risk_budget.get("verdict", "ERROR"),
    ]

    n_go = sum(1 for v in verdicts if v == "GO")
    n_nogo = sum(1 for v in verdicts if v == "NO-GO")

    if n_nogo == 0 and n_go >= 3:
        global_verdict = "GO"
    elif n_nogo >= 3:
        global_verdict = "NO-GO"
    else:
        global_verdict = "HOLD"

    report = {
        "phase": "D — Multi-stratégie & Portfolio Construction",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict_global": global_verdict,
        "verdicts": verdicts,
        "summary": {"n_go": n_go, "n_nogo": n_nogo, "n_total": len(verdicts)},
        "kelly": kelly,
        "black_litterman": bl,
        "correlation": corr,
        "risk_budget": risk_budget,
        "next_step": (
            "Phase E (Compliance & Infrastructure)"
            if global_verdict == "GO"
            else "KILL — corrigez le portfolio avant Phase E"
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
        print(f"  Kelly         : {kelly.get('verdict', 'ERROR')}  (kelly={kelly.get('kelly_clamped', 'N/A')})")
        print(f"  Black-Lit     : {bl.get('verdict', 'ERROR')}  (HHI={bl.get('hhi_concentration', 'N/A')})")
        print(f"  Corrélation   : {corr.get('verdict', 'ERROR')}  (avg={corr.get('avg_correlation', 'N/A')})")
        print(f"  Risk Budget   : {risk_budget.get('verdict', 'ERROR')}  (total={risk_budget.get('total_risk_budget', 'N/A')})")
        print("=" * 70)
        print(f"  VERDICT GLOBAL : {global_verdict}")
        print(f"  → {report['next_step']}")
        print(f"  → Rapport sauvé : {output_path}")
        print("=" * 70)

    return 0 if global_verdict == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())