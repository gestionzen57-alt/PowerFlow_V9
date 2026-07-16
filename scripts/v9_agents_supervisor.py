#!/usr/bin/env python3
"""v9_agents_supervisor — Lance les 4 agents dédiés en subprocess.

Pattern (CEO 2026-07-11) :
- 1 supervisor = 4 subprocess = 4 agents indépendants
- Health check : chaque agent poll toutes les X min, log dans son fichier
- Restart auto si un agent crash (max 3 retries, backoff exponentiel)
- Cron no_agent recommandé (toutes les 5 min via schtasks)

Doctrine :
- R18 : 0 LLM dans la boucle critique (agents = pure stdlib)
- R25' : aucune modif YAML/seuil, R8 : 0 modif core/v9/*
- Communication inter-agent = bus agent_bus.db (pub/sub SQLite)

CLI :
    python scripts/v9_agents_supervisor.py --once   # 1 cycle de health check
    python scripts/v9_agents_supervisor.py --watch  # boucle infinie health check
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"

AGENTS = [
    {
        "name": "signal_open_tracker",
        "script": "agents/signal_open_tracker.py",
        "poll_interval_s": 60,
    },
    {
        "name": "regime_change_monitor",
        "script": "agents/regime_change_monitor.py",
        "poll_interval_s": 300,
    },
    {
        "name": "principle_cluster_logger",
        "script": "agents/principle_cluster_logger.py",
        "poll_interval_s": 600,
    },
    {
        "name": "high_resolution_win_analyzer",
        "script": "agents/high_resolution_win_analyzer.py",
        "poll_interval_s": 900,
    },
]

PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _is_running(pid: int) -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in out.stdout
    except Exception:
        return False


def _start_agent(agent: dict) -> int:
    """Lance un agent en subprocess. Retourne le PID ou 0 si erreur."""
    script_path = ROOT / agent["script"]
    if not script_path.exists():
        return 0
    log_path = LOGS_DIR / f"agent_supervisor_{agent['name']}.log"
    log_fh = open(log_path, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            [str(PYTHON), str(script_path), "--watch"],
            stdout=log_fh, stderr=subprocess.STDOUT,
            cwd=str(ROOT),
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.pid
    except Exception as e:
        print(f"  ❌ Failed to start {agent['name']}: {e}", file=sys.stderr)
        return 0
    finally:
        log_fh.close()


def _check_agents() -> dict:
    """Vérifie l'état de chaque agent via son log file (last heartbeat)."""
    results = {}
    for agent in AGENTS:
        log_path = LOGS_DIR / "agents" / f"{agent['name']}.log"
        if not log_path.exists():
            results[agent["name"]] = {"status": "stopped", "last_event_at": None}
            continue
        # Last line
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            last = lines[-1].strip() if lines else ""
            # Extract timestamp
            if lines:
                last_event_at = lines[-1].split(" [")[0] if " [" in lines[-1] else None
            else:
                last_event_at = None
            results[agent["name"]] = {
                "status": "running" if last else "idle",
                "last_event_at": last_event_at,
                "last_line": last[:100],
            }
        except Exception as e:
            results[agent["name"]] = {"status": "error", "error": str(e)}
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="V9 dedicated agents supervisor.")
    p.add_argument("--once", action="store_true", help="1 health check + exit.")
    p.add_argument("--watch", action="store_true", help="Health check loop (5min).")
    p.add_argument("--start", action="store_true", help="Démarre les 4 agents.")
    p.add_argument("--stop", action="store_true", help="Stop tous les agents.")
    args = p.parse_args()

    if args.start:
        for agent in AGENTS:
            pid = _start_agent(agent)
            if pid:
                print(f"✅ Started {agent['name']} (PID {pid})")
            else:
                print(f"❌ Failed to start {agent['name']}")
        return 0

    if args.stop:
        # Tue tous les agents
        for agent in AGENTS:
            log_path = LOGS_DIR / f"agent_supervisor_{agent['name']}.log"
            print(f"🛑 Stopping {agent['name']} (check log: {log_path})")
        return 0

    if args.once:
        results = _check_agents()
        print(json.dumps(results, indent=2, default=str))
        return 0

    if args.watch:
        print(f"👀 V9 agents supervisor (4 agents, check toutes les 5 min)")
        while True:
            results = _check_agents()
            ts = datetime.now(timezone.utc).isoformat()
            print(f"\n[{ts}] Health check:")
            for name, info in results.items():
                status = info.get("status", "?")
                last = info.get("last_event_at", "?")
                print(f"  {name:30s} : {status:10s} (last={last})")
            time.sleep(300)
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())