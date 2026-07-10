#!/usr/bin/env python3
"""v9_calibration_loop.py — Wrapper cron no_agent pour calibration périodique.

Phase 3 du chantier H24 autopilot. Lance v9_calibration.py --analyze
et --principes à intervalles réguliers, écrit rapport horodaté.

Doctrine :
- R18 : zéro LLM (subprocess stdlib)
- R8 : 0 modif core/v9/*
- R26 : 1 commit par livrable
- Lecture seule sur DB

Usage :
    python scripts/v9_calibration_loop.py --once
    python scripts/v9_calibration_loop.py --once --output-dir docs/reports/calibration/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT_DIR / "logs" / "v9_calibration_loop.log"
SCRIPT_CAL = ROOT_DIR / "scripts" / "v9_calibration.py"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def run_step(name: str, output_path: Path, *args: str) -> int:
    """Run calibration subcommand, write stdout to output_path. Return exit code."""
    cmd = [sys.executable, str(SCRIPT_CAL), *args]
    log(f"{name}: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300, cwd=str(ROOT_DIR),
        )
        output_path.write_text(result.stdout or "", encoding="utf-8")
        out_tail = result.stdout[-500:] if result.stdout else ""
        log(f"{name} EXIT={result.returncode} → {output_path}")
        if result.stderr:
            log(f"{name} STDERR: {result.stderr[-300:]}")
        return result.returncode
    except subprocess.TimeoutExpired:
        log(f"{name} TIMEOUT > 300s")
        return 2
    except Exception as e:
        log(f"{name} ERROR: {e}")
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Wrapper cron no_agent pour calibration V9."
    )
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT_DIR / "docs" / "reports" / "calibration",
    )
    args = parser.parse_args(argv)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    log(f"=== Calibration cycle {ts} ===")
    rc1 = run_step("STATS", args.output_dir / f"stats_{ts}.txt", "--stats")
    rc2 = run_step("PRINCIPLES", args.output_dir / f"principes_{ts}.txt", "--principes")
    rc3 = run_step("ANALYZE", args.output_dir / f"analyze_{ts}.txt", "--analyze")
    log(f"=== Cycle terminé : stats={rc1} principes={rc2} analyze={rc3} ===")

    return max(rc1, rc2, rc3)


if __name__ == "__main__":
    sys.exit(main())