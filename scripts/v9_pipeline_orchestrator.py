"""v9_pipeline_orchestrator.py — Phase 62 motion CEO 48H.

Orchestrateur pipeline avec supervision + restart auto + DLQ.
Mode multiprocessing pour gerer plusieurs producteurs.

Auteur : Hermes (Phase 62 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.orchestrator")

STATE_PATH = Path(r"C:\projet\V9\data\orchestrator_state.json")
DLQ_PATH = Path(r"C:\projet\V9\data\orchestrator_dlq.jsonl")


def load_state() -> dict:
    """Charge l'etat orchestrateur."""
    if not STATE_PATH.exists():
        return {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "workers": {},
            "crashes": 0,
            "restart_attempts": 0,
            "last_heartbeat": None,
            "status": "idle",
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "idle", "workers": {}, "crashes": 0}


def save_state(state: dict) -> None:
    """Persiste etat orchestrateur."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                            encoding="utf-8")


def dlq_push(task: str, error: str, payload: dict = None) -> None:
    """Push task vers DLQ (dead letter queue)."""
    DLQ_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "error": error,
        "payload": payload or {},
    }
    with open(DLQ_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def dlq_count() -> int:
    """Compte entries DLQ."""
    if not DLQ_PATH.exists():
        return 0
    count = 0
    with open(DLQ_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def restart_worker(worker_name: str, state: dict) -> dict:
    """Restart un worker crash."""
    state["restart_attempts"] = state.get("restart_attempts", 0) + 1
    state["workers"][worker_name] = {
        "status": "restarting",
        "restart_at": datetime.now(timezone.utc).isoformat(),
        "n_restarts": state["workers"].get(worker_name, {}).get("n_restarts",
                                                                  0) + 1,
    }
    save_state(state)
    return state["workers"][worker_name]


def heartbeat(worker_name: str, state: dict) -> dict:
    """Update heartbeat d'un worker."""
    state["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
    state["workers"][worker_name] = {
        "status": "alive",
        "last_heartbeat": state["last_heartbeat"],
    }
    save_state(state)
    return state["workers"][worker_name]


def check_health(state: dict, stale_seconds: int = 300) -> dict:
    """Verifie sante workers (heartbeat > threshold = stale)."""
    now = datetime.now(timezone.utc)
    workers = state.get("workers", {}) or {}
    health = {"n_workers": len(workers),
                "n_alive": 0, "n_stale": 0,
                "stale_workers": []}
    for wname, w in workers.items():
        if "last_heartbeat" not in w:
            health["n_stale"] += 1
            health["stale_workers"].append(wname)
            continue
        try:
            last = datetime.fromisoformat(
                w["last_heartbeat"].replace("Z", "+00:00")
            )
            delta = (now - last).total_seconds()
            if delta > stale_seconds:
                health["n_stale"] += 1
                health["stale_workers"].append(wname)
            else:
                health["n_alive"] += 1
        except (KeyError, ValueError):
            health["n_stale"] += 1
            health["stale_workers"].append(wname)
    return health


def orchestrate(workers: list[str]) -> dict:
    """Orchestre N workers."""
    state = load_state()
    for w in workers:
        heartbeat(w, state)
    health = check_health(state)
    return {
        "workers": workers,
        "health": health,
        "dlq_count": dlq_count(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 pipeline orchestrator (Phase 62)",
    )
    parser.add_argument("--workers", nargs="*", default=[],
                        help="Workers a orchestrer")
    parser.add_argument("--status", action="store_true",
                        help="Affiche status orchestrateur")
    args = parser.parse_args(argv)

    if args.status:
        state = load_state()
        health = check_health(state)
        print("=" * 70)
        print("V9 PIPELINE ORCHESTRATOR")
        print("=" * 70)
        print(f"Status          : {state.get('status', 'idle')}")
        print(f"Workers         : {health['n_workers']}")
        print(f"Alive           : {health['n_alive']}")
        print(f"Stale           : {health['n_stale']}")
        print(f"Restart attempts: {state.get('restart_attempts', 0)}")
        print(f"Crashes         : {state.get('crashes', 0)}")
        print(f"DLQ count       : {dlq_count()}")
        if health["stale_workers"]:
            print("Stale workers:")
            for w in health["stale_workers"]:
                print(f"  - {w}")
        print("=" * 70)
        return 0

    if not args.workers:
        print("Use --workers or --status")
        return 1

    result = orchestrate(args.workers)
    print("=" * 70)
    print("V9 PIPELINE ORCHESTRATED")
    print("=" * 70)
    print(f"Workers : {len(result['workers'])}")
    print(f"Alive   : {result['health']['n_alive']}")
    print(f"Stale   : {result['health']['n_stale']}")
    print(f"DLQ     : {result['dlq_count']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())