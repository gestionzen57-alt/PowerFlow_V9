"""
Phase 159 — Kill doublon capture_server (anti-AutoRestart policy).

Problème observé 03/08/2026 ~20:44 UTC : le cron V9CaptureWatchdog
relance capture_server via .venv/Scripts/python.exe, mais un autre
processus capture_server tourne déjà (uv-managed Python) → 2 instances
écrivent en parallèle sur la même DB WAL = source de corruption.

Solution : à chaque exécution du watchdog, tuer TOUTES les instances
capture_server (sauf celle qu'on démarre) AVANT de lancer la nouvelle.

Doctrine :
  R2 additif (nouvelle fonction dans watchdog existant)
  R6 fail-open (try/except autour du kill, ne casse pas le watchdog)
  R14 audit SQL live = vérité (1 instance max)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def list_capture_server_pids() -> list[dict]:
    """Liste les PIDs de TOUS les process capture_server (PowerShell CIM)."""
    try:
        cmd = (
            "Get-Process python -ErrorAction SilentlyContinue | "
            "ForEach-Object { try { "
            "  $c = (Get-CimInstance Win32_Process -Filter \"ProcessId=$($_.Id)\").CommandLine; "
            "  if ($c -match 'capture_server') { "
            "    [PSCustomObject]@{PID=$_.Id; PPID=$_.ParentId; StartTime=$_.StartTime; Cmd=$c} "
            "  } "
            "} catch {} } | Select-Object PID,PPID,StartTime,Cmd | ConvertTo-Json -Depth 2"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15, check=False,
        )
        out = res.stdout.strip()
        if not out:
            return []
        # PS ConvertTo-Json retourne array ou object selon count
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception as e:
        return [{"error": str(e)}]


def kill_pid(pid: int) -> bool:
    """Tente de tuer un PID (Windows Stop-Process -Force)."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return True
    except Exception:
        return False


def ensure_single_instance(keep_pid: int | None = None) -> dict:
    """Tue toutes les instances capture_server SAUF celle à garder.

    Args:
        keep_pid: PID à conserver. None = tuer TOUT (avant start fresh).

    Returns:
        dict avec killed (liste PIDs tués), kept (PID conservé), errors.
    """
    pids = list_capture_server_pids()
    killed = []
    errors = []
    for entry in pids:
        if "error" in entry:
            errors.append(entry["error"])
            continue
        pid = entry.get("PID")
        if pid is None:
            continue
        if keep_pid is not None and pid == keep_pid:
            continue
        if kill_pid(pid):
            killed.append(pid)
    return {
        "killed": killed,
        "kept": keep_pid,
        "initial_count": len(pids),
        "errors": errors,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 159 kill doublon capture_server")
    parser.add_argument("--keep", type=int, default=None, help="PID à conserver (None = tout tuer)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    res = ensure_single_instance(args.keep)
    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        print("=== Phase 159 kill doublon capture_server ===")
        print(f"  Initial count : {res['initial_count']}")
        print(f"  Killed        : {res['killed']}")
        print(f"  Kept          : {res['kept']}")
        if res['errors']:
            print(f"  Errors        : {res['errors']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
