#!/usr/bin/env python3
"""
v10_s24_batch.py — Batch CEO Sprint 24 (orchestrateur)
Perplexity GitHub MCP — 2026-08-08 20:45 CEST

Enchaîne dans l'ordre :
  1. RL shadow rerun  (EURUSD + USDJPY)
  2. Walk-forward 30j (EURUSD M30)
  3. Metrics dashboard
  4. Rapport consolidé CEO JSON + CLI

Doctrine : R1-AGIR, R6 fail-open, R9-AUDIT, R10-CAPITAL (0 order)
"""
from __future__ import annotations
import importlib, json, traceback
from datetime import datetime, timezone
from pathlib import Path

REPORTS = Path("reports")
REPORTS.mkdir(exist_ok=True)

STEPS = [
    ("rl_shadow_rerun",   "scripts.v10_rl_shadow_rerun",   "run"),
    ("walkforward_30d",   "scripts.v10_walkforward_30d",    "run"),
    ("metrics_dashboard", "scripts.v10_metrics_dashboard",  "run_dashboard"),
]

def _run_step(label: str, module: str, fn: str) -> dict:
    try:
        mod = importlib.import_module(module)
        result = getattr(mod, fn)()
        return {"step": label, "status": "OK", "result": result}
    except Exception:
        return {"step": label, "status": "ERROR", "traceback": traceback.format_exc()}

def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    batch = {"timestamp_utc": ts, "sprint": "S24", "steps": []}
    print(f"\n{'='*60}")
    print(f"  V10 CEO BATCH S24 — {ts}")
    print(f"{'='*60}")
    for label, module, fn in STEPS:
        print(f"\n▶️  {label} ...")
        r = _run_step(label, module, fn)
        batch["steps"].append(r)
        print(f"   {'OK' if r['status']=='OK' else 'ERROR: '+r.get('traceback','')[:200]}")
    ok = sum(1 for s in batch["steps"] if s["status"] == "OK")
    batch["summary"] = {"steps_ok": ok, "steps_total": len(STEPS),
                        "verdict": "PASS" if ok == len(STEPS) else f"PARTIAL ({ok}/{len(STEPS)})"}
    out = REPORTS / f"v10_s24_batch_{ts}.json"
    out.write_text(json.dumps(batch, indent=2, default=str, ensure_ascii=False))
    print(f"\n📊 Batch verdict : {batch['summary']['verdict']}")
    print(f"💾 Rapport : {out}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
