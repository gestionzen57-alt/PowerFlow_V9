"""
V10 — Phase C Exécution orchestrator.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Exécute Latence + Slippage + Order Flow + Fill Rate → rapport JSON.

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_phase_c_exec.py
  .venv/Scripts/python.exe scripts/v10_phase_c_exec.py --json
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
OUTPUT_DEFAULT = ROOT / "docs" / "V10" / "exec_latest.json"


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
    parser = argparse.ArgumentParser(description="V10 Phase C Exécution orchestrator")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--output", default=None, help="Fichier sortie")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else OUTPUT_DEFAULT

    print("⚡ V10 Phase C Exécution — orchestrateur", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    print("  [1/4] Latence pipeline...", file=sys.stderr)
    latency = run_script("v10_latency.py")

    print("  [2/4] Slippage model...", file=sys.stderr)
    slippage = run_script("v10_slippage_model.py", ["--factor", "0.5"])

    print("  [3/4] Order Flow / VPIN...", file=sys.stderr)
    order_flow = run_script("v10_order_flow.py")

    print("  [4/4] Fill rate...", file=sys.stderr)
    fill_rate = run_script("v10_fill_rate.py")

    verdicts = [
        latency.get("verdict", "ERROR"),
        slippage.get("verdict", "ERROR"),
        order_flow.get("verdict", "ERROR"),
        fill_rate.get("verdict", "ERROR"),
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
        "phase": "C — Exécution & Microstructure",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict_global": global_verdict,
        "verdicts": verdicts,
        "summary": {"n_go": n_go, "n_nogo": n_nogo, "n_total": len(verdicts)},
        "latency": latency,
        "slippage_model": slippage,
        "order_flow": order_flow,
        "fill_rate": fill_rate,
        "next_step": (
            "Phase D (Multi-stratégie portfolio)"
            if global_verdict == "GO"
            else "KILL — corrigez l'exécution avant Phase D"
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
        print(f"  Latence      : {latency.get('verdict', 'ERROR')}  (total={latency.get('latency_total_ms', 'N/A')}ms)")
        print(f"  Slippage     : {slippage.get('verdict', 'ERROR')}  (est={slippage.get('slippage_estimated_pips', 'N/A')}pips)")
        print(f"  Order Flow   : {order_flow.get('verdict', 'ERROR')}  (VPIN={order_flow.get('vpin', 'N/A')})")
        print(f"  Fill Rate    : {fill_rate.get('verdict', 'ERROR')}  (fill={fill_rate.get('fill_rate_pct', 'N/A')}%)")
        print("=" * 70)
        print(f"  VERDICT GLOBAL : {global_verdict}")
        print(f"  → {report['next_step']}")
        print(f"  → Rapport sauvé : {output_path}")
        print("=" * 70)

    return 0 if global_verdict == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())