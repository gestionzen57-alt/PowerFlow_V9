#!/usr/bin/env python3
"""v9_ops.py — Point d'entrée unique opérateur PowerFlow V9.

Regroupe toutes les commandes opérationnelles V9 sous un seul script,
sans dupliquer la logique des scripts existants. Chaque sous-commande
délègue au script approprié via subprocess.

Usage :
    python scripts/v9_ops.py check          # deploy_v9.py --check
    python scripts/v9_ops.py start          # deploy_v9.py --start
    python scripts/v9_ops.py status         # deploy_v9.py --status
    python scripts/v9_ops.py stop           # deploy_v9.py --stop
    python scripts/v9_ops.py restart        # stop + start
    python scripts/v9_ops.py boot           # v9_bootstrap.py --boot
    python scripts/v9_ops.py market-open    # v9_market_open.py --market-open
    python scripts/v9_ops.py resume         # v9_session_resume.py --resume
    python scripts/v9_ops.py dashboard      # v9_dashboard.py --once
    python scripts/v9_ops.py watch          # v9_dashboard.py (interval 5s)
    python scripts/v9_ops.py signals        # v9_dashboard.py --watch signals
    python scripts/v9_ops.py decisions      # v9_dashboard.py --watch decisions
    python scripts/v9_ops.py calibrate      # v9_calibration.py --analyze
    python scripts/v9_ops.py principles     # v9_calibration.py --principes
    python scripts/v9_ops.py stats          # v9_calibration.py --stats
    python scripts/v9_ops.py health         # v9_supervisor.py --health
    python scripts/v9_ops.py log            # tail des logs capture (Get-Content -Wait)
    python scripts/v9_ops.py validate-ea    # validate_ea_output.py --once
    python scripts/v9_ops.py chain-regen    # regenerate_chain.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
CAPTURE_LOG = ROOT_DIR / "logs" / "v9_capture.log"


def _run(script: str, args: list[str] | None = None) -> int:
    """Run a script via subprocess, forwarding exit code."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script)]
    if args:
        cmd.extend(args)
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))
    return result.returncode


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0

    cmd = sys.argv[1]
    extra = sys.argv[2:]

    # Dispatch map
    dispatch = {
        # deploy_v9.py
        "check": ("deploy_v9.py", ["--check"]),
        "start": ("deploy_v9.py", ["--start"]),
        "status": ("deploy_v9.py", ["--status"]),
        "stop": ("deploy_v9.py", ["--stop"]),
        # ops scripts
        "boot": ("v9_bootstrap.py", ["--boot"] + extra),
        "market-open": ("v9_market_open.py", ["--market-open"] + extra),
        "resume": ("v9_session_resume.py", ["--resume"] + extra),
        "health": ("v9_supervisor.py", ["--health"]),
        # dashboard
        "dashboard": ("v9_dashboard.py", ["--once"]),
        "watch": ("v9_dashboard.py", ["--interval", "5"]),
        "signals": ("v9_dashboard.py", ["--watch", "signals"]),
        "decisions": ("v9_dashboard.py", ["--watch", "decisions"]),
        # calibration
        "calibrate": ("v9_calibration.py", ["--analyze"]),
        "principles": ("v9_calibration.py", ["--principes"]),
        "stats": ("v9_calibration.py", ["--stats"]),
        # chain
        "chain-regen": ("regenerate_chain.py", extra),
        # validation
        "validate-ea": ("validate_ea_output.py", ["--once"]),
    }

    if cmd == "restart":
        r1 = dispatch["stop"]
        if r1:
            _run(*r1)
        return _run(*dispatch["start"])

    if cmd == "log":
        """Suivi des logs du serveur de capture (PowerShell Get-Content -Wait)."""
        import os
        log_path = str(CAPTURE_LOG)
        if not CAPTURE_LOG.exists():
            print(f"Log introuvable : {log_path}")
            return 1
        print(f"Suivi des logs : {log_path}")
        print("Ctrl+C pour quitter.")
        print()
        os.execlp("powershell", "powershell",
                  "Get-Content", "-Path", log_path, "-Wait", "-Tail", "20")
        return 0

    if cmd in ("--help", "-h", "help"):
        print(__doc__)
        return 0

    if cmd in dispatch:
        return _run(*dispatch[cmd])

    print(f"Commande inconnue : {cmd}")
    print("Utilisez --help pour la liste des commandes.")
    return 1


if __name__ == "__main__":
    sys.exit(main())