"""v9_auto_commit.py — Phase 61.3 motion CEO 48H non-stop.

Git ops automatise : add + commit + push inline.
Pas de batch en fin de session.

Auteur : Hermes (Phase 61.3 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.auto_commit")

BRANCH = "feat/v9-foundation-clean"


def run_git(args: list[str], cwd: Path = None) -> tuple[int, str, str]:
    """Run git command et retourne (returncode, stdout, stderr)."""
    cmd = ["git"] + args
    result = subprocess.run(
        cmd, cwd=cwd or _ROOT, capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def stage_files(files: list[str]) -> tuple[int, str, str]:
    """git add files specifiques."""
    if not files:
        return run_git(["add", "-A"])
    return run_git(["add"] + files)


def commit_phase(phase_id: str, message: str) -> tuple[int, str, str]:
    """Commit avec message convention."""
    full_msg = f"feat(v9): {phase_id} - {message}"
    return run_git(["commit", "-m", full_msg])


def push_inline(branch: str = BRANCH) -> tuple[int, str, str]:
    """Push inline sur la branche."""
    return run_git(["push", "origin", branch])


def auto_commit_phase(phase_id: str, message: str,
                        files: list[str] = None) -> dict:
    """Pipeline complet : stage + commit + push."""
    rc, out, err = stage_files(files or [])
    if rc != 0:
        return {"error": "stage_failed", "stderr": err}
    rc, out, err = commit_phase(phase_id, message)
    if rc != 0:
        # Rien a commit peut-etre
        if "nothing to commit" in (out + err).lower():
            return {"noop": "nothing_to_commit"}
        return {"error": "commit_failed", "stderr": err}
    rc, out, err = push_inline()
    if rc != 0:
        return {"error": "push_failed", "stderr": err}
    return {
        "staged": len(files) if files else "all",
        "committed": True,
        "pushed": True,
        "branch": BRANCH,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 auto commit (Phase 61.3)",
    )
    parser.add_argument("--phase-id", required=True,
                        help="Phase ID (eg Phase 62)")
    parser.add_argument("--message", required=True,
                        help="Commit message")
    parser.add_argument("--files", nargs="*", default=None,
                        help="Files specifiques (defaut: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Dry run (no real git ops)")
    args = parser.parse_args(argv)

    if args.dry_run:
        print("=" * 70)
        print("V9 AUTO COMMIT — DRY RUN")
        print("=" * 70)
        print(f"Phase ID : {args.phase_id}")
        print(f"Message  : {args.message}")
        print(f"Files    : {args.files or 'all'}")
        print("=" * 70)
        return 0

    result = auto_commit_phase(args.phase_id, args.message, args.files)
    print("=" * 70)
    print("V9 AUTO COMMIT")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        if "stderr" in result:
            print(f"Details : {result['stderr'][:200]}")
        return 1
    if "noop" in result:
        print(f"No-op   : {result['noop']}")
        return 0
    print(f"Staged  : {result.get('staged', '?')}")
    print(f"Pushed  : {result.get('pushed', False)}")
    print(f"Branch  : {result.get('branch', '?')}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())