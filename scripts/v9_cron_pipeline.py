#!/usr/bin/env python3
"""v9_cron_pipeline.py — Phase 7 motion CEO « EDGE FUND MAX ».

Cron quotidien (Windows scheduler / Linux cron) qui execute :
1. walk_forward_evaluation (validation MEGA-EDGE 5 fenetres 90j)
2. force_promote_stars (3 stars ACTIVE idempotent)
3. force_close_aged_trades (L3 time_exit > 5min)

Production-ready, exit code 0 = OK, 1 = erreur.
Logs dans data/v9_cron_pipeline.log (file handler + stdout).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG_PATH = ROOT / "data" / "v9_cron_pipeline.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# Configure logging (file + stdout, append mode)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("v9.cron_pipeline")


def run_pipeline() -> dict:
    """Execute les 3 etapes du pipeline quotidien.

    Returns dict {walk_forward, auto_promote, time_exit, ok}.
    """
    started_at = datetime.utcnow().isoformat()
    log.info("=== v9_cron_pipeline START %s ===", started_at)

    result = {"started_at": started_at}

    # 1. Walk-forward evaluation
    try:
        from scripts.v9_walk_forward import walk_forward_evaluation
        wf = walk_forward_evaluation(n_windows=5, window_days=90)
        result["walk_forward"] = {
            "summary": wf.get("summary", {}),
            "n_windows": len(wf.get("windows", [])),
        }
        log.info(
            "walk_forward: %d fenetres, n_total=%d, WR avg=%.1f%%, "
            "total_pips=%.1fp",
            result["walk_forward"]["n_windows"],
            wf.get("summary", {}).get("n_total", 0),
            wf.get("summary", {}).get("wr_avg", 0.0),
            wf.get("summary", {}).get("total_pips", 0.0),
        )
    except Exception as exc:
        log.error("walk_forward FAILED: %s", exc)
        result["walk_forward"] = {"error": str(exc)}

    # 2. Auto-promote stars (idempotent)
    try:
        from scripts.v9_auto_promote_stars import force_promote_stars
        ap = force_promote_stars()
        result["auto_promote"] = ap
        log.info(
            "auto_promote: %d promotions, %d deja presents, written=%s",
            len(ap.get("promotions", [])),
            len(ap.get("already_present", [])),
            ap.get("written", False),
        )
    except Exception as exc:
        log.error("auto_promote FAILED: %s", exc)
        result["auto_promote"] = {"error": str(exc)}

    # 3. Time exit L3 force_close_aged_trades
    try:
        from scripts.v9_close_time_exit import force_close_aged_trades
        te = force_close_aged_trades()
        result["time_exit"] = te
        log.info(
            "time_exit: %d forced, %d skipped, %d artifact",
            te.get("forced", 0),
            te.get("skipped", 0),
            te.get("artifact", 0),
        )
    except Exception as exc:
        log.error("time_exit FAILED: %s", exc)
        result["time_exit"] = {"error": str(exc)}

    # Rollback check : si walk_forward WR < 60%, alerter
    wf_summary = result.get("walk_forward", {}).get("summary", {})
    if wf_summary.get("wr_avg", 0.0) < 60.0 and wf_summary.get("n_total", 0) > 20:
        log.warning(
            "ALERT: walk_forward WR=%.1f%% < 60%% (n_total=%d). "
            "Edge degrade, declenchement motion CEO recommandee.",
            wf_summary["wr_avg"], wf_summary["n_total"],
        )
        result["alert"] = "wr_below_threshold"

    result["finished_at"] = datetime.utcnow().isoformat()
    result["ok"] = (
        "error" not in result["walk_forward"]
        and "error" not in result["auto_promote"]
        and "error" not in result["time_exit"]
    )
    log.info("=== v9_cron_pipeline END ok=%s ===", result["ok"])
    return result


def main():
    res = run_pipeline()
    print(json.dumps(res, indent=2, default=str))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())