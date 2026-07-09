#!/usr/bin/env python3
"""v9_meta_agent_watch.py — Wrapper cron pour le meta-agent V9.

Cycle unique (scan + learn) puis exit. Idempotent : peut être appelé
toutes les 10 min sans accumulation. Log dans logs/meta_agent.log.

Usage :
    python scripts/v9_meta_agent_watch.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "meta_agent.log"
SCRIPT = ROOT_DIR / "scripts" / "v9_meta_agent.py"


def log(msg: str) -> None:
    """Append a timestamped line to the log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run_step(step_name: str, *args: str) -> int:
    """Run the meta-agent script with given args, log output, return exit code."""
    cmd = [sys.executable, str(SCRIPT), *args]
    log(f"=== {step_name} : {' '.join(cmd)} ===")
    t0 = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.time() - t0

    if result.stdout:
        for line in result.stdout.strip().splitlines():
            log(f"  {step_name}| {line}")
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            log(f"  {step_name}! {line}")

    if result.returncode == 0:
        log(f"✓ {step_name} terminé en {elapsed:.1f}s")
    else:
        log(f"✗ {step_name} échoué (code={result.returncode}) en {elapsed:.1f}s")

    return result.returncode


def main() -> int:
    log("╔══════════════════════════════════════════╗")
    log("║  META-AGENT V9 — CYCLE CRON             ║")
    log("╚══════════════════════════════════════════╝")

    # 1) Scan patterns
    rc1 = run_step("SCAN", "--scan", "--hours", "24")

    # 2) Learn cycle (produit des propositions)
    rc2 = run_step("LEARN", "--learn", "--hours", "24")

    # 3) Afficher les propositions en attente
    run_step("PROPOSALS", "--proposals", "--limit", "5")

    log(f"Cycle terminé — scan={rc1}, learn={rc2}")
    return max(rc1, rc2)


if __name__ == "__main__":
    sys.exit(main())
