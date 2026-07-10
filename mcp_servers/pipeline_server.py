#!/usr/bin/env python3
"""mcp-v9-pipeline — MCP server ciblé pour orchestration pipeline V9.

Tools exposés :
- start() → bool         (lance capture_server.py)
- stop() → bool          (kill capture_server.py proprement)
- status() → dict         (port, DB freshness, dernier snapshot)
- health() → dict         (health snapshot complet)
- run_script(name: str, args: str) → str  (sous-processus V9, capture stdout)
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"
LISTEN_PORT = 31685
SCRIPTS_DIR = ROOT_DIR / "scripts"

# Whitelist des scripts V9 invocables via run_script
ALLOWED_SCRIPTS = {
    "v9_ops", "v9_calibration", "v9_dashboard", "v9_replay_param",
    "v9_resolve_decision_auto", "v9_paper_trade_offline",
    "v9_recalibrate_arbiter", "v9_meta_agent", "v9_meta_agent_emit",
    "v9_principle_alert", "v9_db_hygiene", "v9_principles",
}


def _check_port(port: int) -> bool:
    """Vérifie si le port est LISTEN (pas besoin d'envoyer quoi que ce soit)."""
    import socket
    try:
        s = socket.socket()
        s.settimeout(2)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False


def _pid_running(pid: int) -> bool:
    try:
        import psutil  # type: ignore
        return psutil.pid_exists(pid)
    except ImportError:
        # Fallback : tasklist
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in out.stdout
        except Exception:
            return False


def handle_start(args: dict) -> dict:
    """Lance capture_server.py via v9_ops.py start."""
    try:
        result = subprocess.run(
            [sys.executable, "scripts/v9_ops.py", "start"],
            capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=30,
        )
        return {"started": result.returncode == 0, "output": result.stdout[-500:]}
    except Exception as e:
        return {"error": str(e)}


def handle_stop(args: dict) -> dict:
    """Stop le capture_server en killant le PID du port 31685."""
    try:
        # Trouver le PID via netstat
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=5,
        )
        for line in out.stdout.splitlines():
            if f":{LISTEN_PORT}" in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True, timeout=5,
                    )
                    return {"stopped": True, "pid": pid}
        return {"stopped": False, "reason": "no process on port"}
    except Exception as e:
        return {"error": str(e)}


def handle_status(args: dict) -> dict:
    """Status compact : port + DB freshness + snapshot count."""
    try:
        port_up = _check_port(LISTEN_PORT)
        if not DB_PATH.exists():
            return {"port": port_up, "db_exists": False}
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        try:
            n_snap = conn.execute("SELECT COUNT(*) FROM forces_snapshots").fetchone()[0]
            ts = conn.execute("SELECT MAX(timestamp) FROM forces_snapshots").fetchone()[0]
            n_dec = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        finally:
            conn.close()
        age_s = None
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                age_s = int((datetime.now(timezone.utc) - dt).total_seconds())
            except Exception:
                pass
        return {
            "port_31685": port_up,
            "snapshots_total": n_snap,
            "decisions_total": n_dec,
            "last_snapshot_ts": ts,
            "last_snapshot_age_s": age_s,
        }
    except Exception as e:
        return {"error": str(e)}


def handle_health(args: dict) -> dict:
    """Health snapshot complet (équivalent v9_supervisor.py --health)."""
    try:
        result = subprocess.run(
            [sys.executable, "scripts/v9_supervisor.py", "--health"],
            capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=30,
        )
        return {
            "exit_code": result.returncode,
            "output_tail": result.stdout[-1500:],
            "stderr_tail": result.stderr[-300:] if result.stderr else "",
        }
    except Exception as e:
        return {"error": str(e)}


def handle_run_script(args: dict) -> dict:
    """Lance un script V9 whitelisté avec capture stdout (60s timeout)."""
    name = args.get("name", "")
    extra_args = args.get("args", "")
    if name not in ALLOWED_SCRIPTS:
        return {"error": f"script '{name}' non whitelisté. Whitelist: {sorted(ALLOWED_SCRIPTS)}"}
    try:
        parts = [sys.executable, f"scripts/{name}.py"] + (extra_args.split() if extra_args else [])
        result = subprocess.run(
            parts, capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=60,
        )
        return {
            "exit_code": result.returncode,
            "stdout_tail": result.stdout[-3000:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout 60s"}
    except Exception as e:
        return {"error": str(e)}


HANDLERS = {
    "start": handle_start,
    "stop": handle_stop,
    "status": handle_status,
    "health": handle_health,
    "run_script": handle_run_script,
}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            tool = req.get("tool")
            args = req.get("args", {})
            handler = HANDLERS.get(tool)
            if not handler:
                result = {"error": f"unknown tool: {tool}"}
            else:
                result = handler(args)
            print(json.dumps({"id": req.get("id"), "result": result}), flush=True)
        except Exception as e:
            print(json.dumps({"error": f"parse/handle error: {e}"}), flush=True)


if __name__ == "__main__":
    main()