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
    python scripts/v9_ops.py comportements  # v9_dashboard.py --watch comportements
    python scripts/v9_ops.py fenetres       # v9_dashboard.py --watch fenetres
    python scripts/v9_ops.py calibrate      # v9_calibration.py --analyze
    python scripts/v9_ops.py principles     # v9_calibration.py --principes
    python scripts/v9_ops.py stats          # v9_calibration.py --stats
    python scripts/v9_ops.py health         # v9_supervisor.py --health
    python scripts/v9_ops.py log            # tail -f natif (logs/v9_capture.log)
    python scripts/v9_ops.py validate-ea    # validate_ea_output.py --once
    python scripts/v9_ops.py chain-regen    # regenerate_chain.py [--dry-run|--replace-derived]
    python scripts/v9_ops.py live-test      # live_integration_test.py [--duration|--interval|...]
    python scripts/v9_ops.py replay         # v9_replay.py [--list|--show|--compare|--search]
    python scripts/v9_ops.py thresholds     # adaptive_thresholds.propose_thresholds_diff() (current vs proposed)
    python scripts/v9_ops.py propose [window_days]     # learning_loop.propose_from_outcomes() + résumé PENDING
    python scripts/v9_ops.py approve <proposal_id>     # learning_loop.approve_proposal(id)
    python scripts/v9_ops.py reject <proposal_id> [reason]  # learning_loop.reject_proposal(id, reason)
"""

from __future__ import annotations

import json
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


def cmd_thresholds(args: list[str]) -> int:
    """Handler 'thresholds' — affiche current vs proposed (adaptive_thresholds), + rationale."""
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    from core.v9.adaptive_thresholds import propose_thresholds_diff

    result = propose_thresholds_diff()
    print(json.dumps(result, indent=2, ensure_ascii=False))

    current = result.get("current", {})
    proposed = result.get("proposed", {})
    rationale = result.get("rationale", {})

    print("\n--- Seuils adaptatifs (current vs proposed) ---")
    for key in current:
        marker = "->" if current[key] != proposed.get(key) else "=="
        print(f"{key}: {current[key]} {marker} {proposed.get(key)}")
        if key in rationale:
            print(f"    {rationale[key]}")
    print(f"\nready_to_apply: {result.get('ready_to_apply')}")
    return 0


def cmd_propose(args: list[str]) -> int:
    """Handler 'propose' — génère des propositions (learning_loop) + résumé PENDING (max 5)."""
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    from core.v9.learning_loop import list_proposals, propose_from_outcomes

    window_days = 30
    if args and args[0].isdigit():
        window_days = int(args[0])

    propose_from_outcomes(window_days)
    pending = list_proposals("PENDING")[:5]

    print(f"--- Propositions PENDING (window_days={window_days}) ---")
    if not pending:
        print("Aucune proposition en attente.")
        return 0

    for p in pending:
        print(f"[{p['id']}] score={p['score']} target={p['target']}")
        print(f"    wr={p['observed_wr']:.0%} n={p['observed_n']} — {p['rationale']}")
    return 0


def cmd_approve(args: list[str]) -> int:
    """Handler 'approve' — approuve une proposition PENDING (learning_loop.approve_proposal)."""
    if "--help" in args or "-h" in args or not args:
        print(__doc__)
        return 0

    from core.v9.learning_loop import approve_proposal

    proposal_id = args[0]
    if approve_proposal(proposal_id):
        print(f"APPROVED id={proposal_id}")
        return 0
    print("NOT FOUND")
    return 1


def cmd_reject(args: list[str]) -> int:
    """Handler 'reject' — rejette une proposition PENDING (learning_loop.reject_proposal)."""
    if "--help" in args or "-h" in args or not args:
        print(__doc__)
        return 0

    from core.v9.learning_loop import reject_proposal

    proposal_id = args[0]
    reason = args[1] if len(args) > 1 else ""
    if reject_proposal(proposal_id, reason):
        print(f"REJECTED id={proposal_id}")
        return 0
    print("NOT FOUND")
    return 1


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
        "comportements": ("v9_dashboard.py", ["--watch", "comportements"]),
        "fenetres": ("v9_dashboard.py", ["--watch", "fenetres"]),
        # calibration
        "calibrate": ("v9_calibration.py", ["--analyze"]),
        "principles": ("v9_calibration.py", ["--principes"]),
        "stats": ("v9_calibration.py", ["--stats"]),
        # chain
        "chain-regen": ("regenerate_chain.py", extra),
        # validation
        "validate-ea": ("validate_ea_output.py", ["--once"]),
        # live integration test
        "live-test": ("live_integration_test.py", extra),
        # replay / inspection
        "replay": ("v9_replay.py", extra),
    }

    if cmd == "restart":
        r1 = dispatch["stop"]
        if r1:
            _run(*r1)
        return _run(*dispatch["start"])

    if cmd == "log":
        """Suivi des logs du serveur de capture (tail -f natif, compatible Windows/Git Bash/PowerShell)."""
        import time
        log_path = str(CAPTURE_LOG)
        if not CAPTURE_LOG.exists():
            print(f"Log introuvable : {log_path}")
            return 1
        print(f"Suivi des logs : {log_path}")
        print("Ctrl+C pour quitter.\n")
        # Python-native tail -f (compatible tous shells)
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            # Afficher les 20 dernieres lignes
            lines = f.readlines()
            for line in lines[-20:]:
                print(line, end="")
            # Puis suivre en temps reel
            try:
                while True:
                    line = f.readline()
                    if line:
                        print(line, end="")
                    else:
                        time.sleep(0.5)
            except KeyboardInterrupt:
                pass
        return 0

    if cmd in ("--help", "-h", "help"):
        print(__doc__)
        return 0

    if cmd == "thresholds":
        return cmd_thresholds(extra)

    if cmd == "propose":
        return cmd_propose(extra)

    if cmd == "approve":
        return cmd_approve(extra)

    if cmd == "reject":
        return cmd_reject(extra)

    if cmd in dispatch:
        return _run(*dispatch[cmd])

    print(f"Commande inconnue : {cmd}")
    print("Utilisez --help pour la liste des commandes.")
    return 1


if __name__ == "__main__":
    sys.exit(main())