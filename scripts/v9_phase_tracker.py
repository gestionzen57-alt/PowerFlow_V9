"""v9_phase_tracker.py — Phase 61.1 motion CEO 48H non-stop.

State persistence de la session auto-perpetuante.
Lit/ecrit data/v9_autonomous_state.json : compact-json pour restart.

Auteur : Hermes (Phase 61.1 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.phase_tracker")

STATE_PATH = Path(r"C:\projet\V9\data\v9_autonomous_state.json")


def load_state() -> dict:
    """Charge le state depuis disk. Init si absent."""
    if not STATE_PATH.exists():
        return init_state()
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return init_state()


def save_state(state: dict) -> None:
    """Persiste state sur disk (atomic write)."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                     encoding="utf-8")
    tmp.replace(STATE_PATH)


def init_state() -> dict:
    """Init state par defaut."""
    return {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_update": datetime.now(timezone.utc).isoformat(),
        "elapsed_hours": 0.0,
        "commits_session": 0,
        "phases_delivered": [],
        "phases_pending": [
            "Phase 62 — Pipeline orchestrator",
            "Phase 63 — FTMO compliance",
            "Phase 64 — Real money preflight",
            "Phase 65 — Smart order router",
            "Phase 66 — Live metrics dashboard",
            "Phase 67 — ML forecaster",
            "Phase 68 — Performance persistence",
            "Phase 69 — Cross-pair correlation live",
            "Phase 70 — Chaos engineering advanced",
            "Phase 71 — Adversarial testing",
            "Phase 72 — E2E pipeline test",
            "Phase 73 — Docs coherence auto-sync",
            "Phase 74 — User guide enrichi",
            "Phase 75 — Auto-pr + merge",
            "Phase 76 — Advanced backtest",
            "Phase 77 — Risk parity",
            "Phase 78 — Drawdown protector",
            "Phase 79 — Final bilan 48h",
            "Phase 80 — Auto-pr + tag release",
        ],
        "current_focus": None,
        "auto_loop_enabled": True,
        "max_hours": 48.0,
        "kill_switch_count": 0,
        "tests_red_streak": 0,
    }


def add_phase_delivered(state: dict, phase_name: str) -> dict:
    """Marque phase comme livree + rotate pending -> next."""
    if phase_name not in state["phases_delivered"]:
        state["phases_delivered"].append(phase_name)
    if phase_name in state["phases_pending"]:
        state["phases_pending"].remove(phase_name)
    state["current_focus"] = None
    state["last_update"] = datetime.now(timezone.utc).isoformat()
    return state


def update_elapsed(state: dict, hours: float) -> dict:
    """Update elapsed time."""
    state["elapsed_hours"] = round(hours, 3)
    state["last_update"] = datetime.now(timezone.utc).isoformat()
    return state


def compute_elapsed_hours(state: dict) -> float:
    """Calcule heures ecoulees depuis started_at."""
    try:
        started = datetime.fromisoformat(
            state["started_at"].replace("Z", "+00:00")
        )
        now = datetime.now(timezone.utc)
        delta = (now - started).total_seconds() / 3600
        return round(delta, 3)
    except (KeyError, ValueError):
        return 0.0


def status(state: dict) -> dict:
    """Retourne status resumee."""
    return {
        "elapsed_hours": state.get("elapsed_hours", 0.0),
        "max_hours": state.get("max_hours", 48.0),
        "remaining_hours": round(
            state.get("max_hours", 48.0) - state.get("elapsed_hours", 0.0),
            3,
        ),
        "commits_session": state.get("commits_session", 0),
        "phases_delivered": len(state.get("phases_delivered", [])),
        "phases_pending": len(state.get("phases_pending", [])),
        "current_focus": state.get("current_focus"),
        "auto_loop_enabled": state.get("auto_loop_enabled", True),
    }


def should_terminate(state: dict) -> bool:
    """Decide si la boucle doit s'arreter."""
    if state.get("elapsed_hours", 0) > state.get("max_hours", 48.0):
        return True
    if state.get("tests_red_streak", 0) > 3:
        return True
    if state.get("commits_session", 0) > 200:
        return True
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 phase tracker (Phase 61.1)",
    )
    parser.add_argument("--status", action="store_true",
                        help="Affiche status")
    parser.add_argument("--reset", action="store_true",
                        help="Reset state")
    parser.add_argument("--add", metavar="PHASE",
                        help="Ajoute phase comme livree")
    parser.add_argument("--next", action="store_true",
                        help="Affiche prochaine phase")
    parser.add_argument("--elapsed", type=float, default=None,
                        help="Set elapsed hours")
    args = parser.parse_args(argv)

    if args.reset:
        state = init_state()
        save_state(state)
        print("State reset.")
        return 0

    state = load_state()
    state["elapsed_hours"] = compute_elapsed_hours(state)

    if args.add:
        state["commits_session"] = state.get("commits_session", 0) + 1
        state = add_phase_delivered(state, args.add)
        save_state(state)
        print(f"Phase livree : {args.add}")
        return 0

    if args.elapsed is not None:
        state = update_elapsed(state, args.elapsed)
        save_state(state)
        print(f"Elapsed : {args.elapsed}h")
        return 0

    if args.next:
        pending = state.get("phases_pending", [])
        if pending:
            print(pending[0])
        else:
            print("Aucune phase pending")
        return 0

    if args.status:
        s = status(state)
        print("=" * 70)
        print("V9 PHASE TRACKER — STATUS")
        print("=" * 70)
        print(f"Elapsed          : {s['elapsed_hours']}h / {s['max_hours']}h")
        print(f"Remaining        : {s['remaining_hours']}h")
        print(f"Commits session  : {s['commits_session']}")
        print(f"Phases delivered : {s['phases_delivered']}")
        print(f"Phases pending   : {s['phases_pending']}")
        print(f"Current focus    : {s['current_focus']}")
        print(f"Auto loop        : {s['auto_loop_enabled']}")
        print(f"Should terminate : {should_terminate(state)}")
        print("=" * 70)
        # Print 5 next phases
        for p in state.get("phases_pending", [])[:5]:
            print(f"  NEXT : {p}")
        return 0

    # Default : status
    s = status(state)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())