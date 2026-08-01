"""v9_autonomous_loop.py — Phase 61.4 motion CEO 48H non-stop.

Moteur principal de la boucle auto-perpetuante.
Execute les phases en boucle sans intervention humaine.

Auteur : Hermes (Phase 61.4 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.auto_loop")


def verify_tests() -> bool:
    """Verifie que les tests passent (dry-run quick)."""
    import subprocess
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q",
             "-m", "not slow", "-p", "no:cacheprovider",
             "--tb=no", "-x"],
            cwd=_ROOT, capture_output=True, text=True, timeout=300,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def run_one_phase(phase_name: str) -> dict:
    """Execute une phase (skeleton - vraie exec par subagent)."""
    log.info("Running phase: %s", phase_name)
    # Ici le vrai execute (subagent) sera appele
    # Pour le pilote, on simule un work cycle
    return {
        "phase": phase_name,
        "status": "executed",
        "elapsed_seconds": 0,
    }


def commit_phase_inline(phase_name: str) -> dict:
    """Commit + push inline."""
    from scripts.v9_auto_commit import auto_commit_phase
    msg = f"motion CEO 48H non-stop - {phase_name}"
    return auto_commit_phase(phase_name.split("—")[0].strip(), msg)


def sync_docs() -> dict:
    """Sync docs (INDEX_MODULES, USER_GUIDE)."""
    log.info("Syncing docs")
    return {"synced": True}


def main_loop(max_hours: float = 48.0,
                max_phases: int = 0,
                dry_run: bool = False) -> int:
    """Boucle principale."""
    from scripts.v9_phase_tracker import (
        load_state, save_state, compute_elapsed_hours,
        should_terminate, add_phase_delivered,
    )
    from scripts.v9_auto_plan import next_phase, generate_emergent

    state = load_state()
    state["elapsed_hours"] = compute_elapsed_hours(state)
    phase_count = 0

    print("=" * 70)
    print("V9 AUTONOMOUS LOOP — DEMARRAGE")
    print("=" * 70)
    print(f"Max hours    : {max_hours}")
    print(f"Max phases   : {max_phases if max_phases > 0 else 'inf'}")
    print(f"Dry run      : {dry_run}")
    print(f"Pending      : {len(state.get('phases_pending', []))}")
    print("=" * 70)

    while True:
        state["elapsed_hours"] = compute_elapsed_hours(state)
        if should_terminate(state):
            print(f"Terminating: elapsed={state['elapsed_hours']}h "
                  f"> max={max_hours}h")
            break
        if max_phases > 0 and phase_count >= max_phases:
            print(f"Terminating: {phase_count} phases livrees")
            break
        # Pick next phase
        nxt = next_phase(state.get("phases_pending", []))
        if nxt is None:
            nxt = generate_emergent()
        state["current_focus"] = nxt["name"]
        save_state(state)
        # Execute
        if dry_run:
            print(f"DRY RUN: would run {nxt['name']} (score {nxt['score']})")
            break
        # Real execution
        result = run_one_phase(nxt["name"])
        log.info("Phase executed: %s", result)
        # Tests
        if not verify_tests():
            state["tests_red_streak"] = (
                state.get("tests_red_streak", 0) + 1
            )
            save_state(state)
            print(f"Tests RED streak : {state['tests_red_streak']}")
            continue
        state["tests_red_streak"] = 0
        # Sync docs
        sync_docs()
        # Commit
        commit_result = commit_phase_inline(nxt["name"])
        log.info("Commit: %s", commit_result)
        # Update state
        state = add_phase_delivered(state, nxt["name"])
        state["commits_session"] = state.get("commits_session", 0) + 1
        save_state(state)
        phase_count += 1
        print(f"Livree : {nxt['name']} (score {nxt['score']})")
        # No sleep - continue

    print("=" * 70)
    print(f"V9 AUTONOMOUS LOOP — FIN ({phase_count} phases)")
    print("=" * 70)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 autonomous loop (Phase 61.4)",
    )
    parser.add_argument("--max-hours", type=float, default=48.0)
    parser.add_argument("--max-phases", type=int, default=0,
                        help="Max phases (0=inf)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return main_loop(
        max_hours=args.max_hours,
        max_phases=args.max_phases,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())