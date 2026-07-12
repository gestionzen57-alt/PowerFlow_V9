#!/usr/bin/env python3
"""v9_auto_calibrator.py — Wrapper CLI/cron pour core/v9/auto_calibrator.py (Brief Q2).

No-op si le kill switch V9_AUTO_CALIBRATOR_ENABLED est OFF (defaut) — log
et sortie 0, aucune lecture DB, aucune notification. Conforme au meme
pattern que v9_calibration_loop.py (wrapper cron no_agent).

Doctrine :
- R18 : 0 LLM
- R8  : 0 modif core/v9/* (wrapper pur)
- Aucun auto-apply — le module ne fait que journaliser/notifier des
  propositions (cognitive_journal + Telegram best-effort).

Usage :
    python scripts/v9_auto_calibrator.py --once
    python scripts/v9_auto_calibrator.py --once --output-dir docs/reports/calibration/
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.auto_calibrator import auto_calibrator_enabled, run_calibration_cycle  # noqa: E402

LOG_PATH = ROOT_DIR / "logs" / "v9_auto_calibrator.log"


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(
        description="Wrapper cron/CLI pour l'auto-calibrateur V9 (Brief Q2, propose-only)."
    )
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT_DIR / "docs" / "reports" / "calibration",
    )
    args = parser.parse_args(argv)

    if not auto_calibrator_enabled():
        _log("SKIP — V9_AUTO_CALIBRATOR_ENABLED=0 (kill switch OFF), no-op.")
        print("V9_AUTO_CALIBRATOR_ENABLED=0 — no-op (kill switch OFF).")
        return 0

    _log("=== Cycle auto-calibrateur démarré ===")
    report = run_calibration_cycle()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = args.output_dir / f"auto_calibrator_{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    n_prop = report.get("n_session_proposals", 0)
    thr_proposed = report.get("threshold_adjustment", {}).get("proposed", False)
    _log(
        f"=== Cycle terminé : {n_prop} proposition(s) session, "
        f"seuils proposés={thr_proposed} -> {out_path} ==="
    )
    print(f"Rapport écrit : {out_path}")
    print(f"Propositions session : {n_prop} | Ajustement seuils proposé : {thr_proposed}")
    print("Aucune application automatique — validation manuelle requise (R25').")
    return 0


if __name__ == "__main__":
    sys.exit(main())
