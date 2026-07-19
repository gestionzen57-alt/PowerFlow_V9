#!/usr/bin/env python3
"""v9_audit_cron_wiring.py — Audit du câblage des crons V9.

Vérifie que les 11 crons V9_* Windows Scheduled Tasks chargent bien
l'env via v9_load_kill_switches.py AVANT d'invoquer leur script.
Si un cron n'est pas wrappé, log WARNING et exit 1.

Motion implicite : câblage cron (R8 strict — pas de modif de logique).

Usage:
    python scripts/v9_audit_cron_wiring.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CRONS = [
    "V9_ArbiterRecal",
    "V9_AutoCalibrator",
    "V9_CalibrationLoop",
    "V9_HeartbeatAlert",
    "V9_HeartbeatCheck",
    "V9_LearningLoop",
    "V9_LiveWatchdogLoop",
    "V9_MetaAgentScan",
    "V9_PaperTradeLoop",
    "V9_ResolveLoop",
    "V9_StrategyPoleRecompute",
]

WRAPPER = "v9_load_kill_switches.py"


def _get_task_args(task_name: str) -> str:
    """Récupère les arguments d'un Scheduled Task via PowerShell."""
    r = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-Command",
            f"(Get-ScheduledTask -TaskName {task_name} | "
            f"Select-Object -ExpandProperty Actions | "
            f"Select-Object -ExpandProperty Arguments)"
        ],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def main() -> int:
    print(f"Audit câblage crons V9 ({len(CRONS)} tâches)")
    print("=" * 60)
    failures: list[str] = []
    for task in CRONS:
        args = _get_task_args(task)
        wrapped = WRAPPER in args
        status = "✅" if wrapped else "❌"
        print(f"  {status} {task:30} wrapped={wrapped}")
        if not wrapped:
            failures.append(task)

    print()
    if failures:
        print(f"❌ {len(failures)} crons NON wrappés : {failures}")
        print()
        print("Fix : utiliser scripts/v9_recable_cron_wiring.py (TODO)")
        return 1

    print(f"✅ {len(CRONS)}/{len(CRONS)} crons wrappés OK (load env avant script).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
