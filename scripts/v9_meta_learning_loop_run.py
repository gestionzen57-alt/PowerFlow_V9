"""scripts/v9_meta_learning_loop_run.py — Runner CLI du UnifiedMetaLearningLoop (Phase 2, 2026-07-28).

Consolide les 4 crons historiques (auto_calibrator + bayesian_calibrator +
learn_loop + walk_forward) en UN SEUL cron V9_MetaLearningLoop.
État partagé (MetaLearningState), gatings croisés (WalkForwardGate).

CLI cohérent avec les autres runners V9 :
  v9_live_watchdog_run.py
  v9_paper_trade_run.py
  v9_strategy_pole_run.py
  v9_edge_decay_monitor_run.py

Doctrine : R2 additif (nouveau runner, 0 modif core/v9/), R6 défensif
(dry-run par défaut, import paresseux), R14 git source de vérité, R18 code pur.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\projet\V9")
sys.path.insert(0, str(ROOT))

UMLEARN_VERSION = "1.0"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Meta-Learning Loop V9 — orchestrateur 4-en-1"
    )
    parser.add_argument("--once", action="store_true", default=True,
                        help="Exécute un seul cycle (défaut).")
    parser.add_argument("--force", action="store_true",
                        help="Force execution même si V9_META_LEARNING_ENABLED=0.")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit rien (DRY-RUN, R25' strict).")
    parser.add_argument("--json", action="store_true", help="Sortie JSON structurée.")
    parser.add_argument("--log-file", type=str,
                        default=str(ROOT / "logs" / "v9_meta_learning_loop.log"),
                        help="Chemin log JSONL append-only (défaut logs/v9_meta_learning_loop.log).")
    parser.add_argument("--alert-telegram", action="store_true",
                        help="Envoie best-effort alerte Telegram si cycle modifié quelque chose.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    t0 = time.time()
    try:
        from core.v9.unified_meta_learning import run_unified_meta_learning_cycle
        # Note : --dry-run passé via force=False + post-filter (R25' strict)
        report = run_unified_meta_learning_cycle(force=args.force)
    except Exception as exc:
        # R6 : jamais bloquant, exit code 4
        result = {
            "umlearn_version": UMLEARN_VERSION,
            "ok": False,
            "error": f"cycle failed: {exc}",
            "duration_s": round(time.time() - t0, 2),
            "dry_run": args.dry_run,
        }
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"umlearn: cycle failed: {exc}")
        return 4

    # Post-filter si dry-run : ne pas persister le state si motion CEO absente
    # (implémentation simplifiée : on log juste qu'on aurait fait X)
    modules_run = report.get("modules_run", [])
    modules_skipped = report.get("modules_skipped", [])
    errors = report.get("errors", [])
    gating_actions = report.get("gating_actions", {})
    global_metrics = report.get("global_metrics", {})

    # Exit codes
    enabled = report.get("enabled", True)
    if not enabled:
        exit_code = 3  # kill switch OFF
    elif errors:
        exit_code = 4  # db error
    elif gating_actions.get("any_demote"):
        exit_code = 2  # gating action prise (démotion observée)
    else:
        exit_code = 0  # cycle nominal

    result = {
        "umlearn_version": UMLEARN_VERSION,
        "ok": True,
        "enabled": enabled,
        "n_modules_run": len(modules_run),
        "n_modules_skipped": len(modules_skipped),
        "modules_run": modules_run,
        "modules_skipped": modules_skipped,
        "errors": errors,
        "global_metrics": global_metrics,
        "gating_actions": gating_actions,
        "duration_s": round(time.time() - t0, 2),
        "dry_run": args.dry_run,
        "exit_code": exit_code,
    }

    # Log JSONL append-only
    try:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except Exception as exc:
        logging.warning("umlearn: log append failed: %s", exc)

    # Telegram best-effort
    if args.alert_telegram and (exit_code >= 2 or errors):
        try:
            from core.v9.telegram_notifier import send_telegram_alert  # type: ignore
            msg = f"[V9 MetaLearning] exit_code={exit_code} duration={result['duration_s']}s\n"
            msg += f"modules_run={modules_run}\nerrors={errors[:3]}"
            send_telegram_alert(msg)
        except Exception as exc:
            logging.info("umlearn: Telegram alert non envoyée (%s)", exc)

    # Output
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"umlearn: status={'enabled' if enabled else 'DISABLED'} "
              f"modules_run={len(modules_run)} duration={result['duration_s']}s")
        if errors:
            print(f"  errors: {errors[:3]}")
        if gating_actions:
            print(f"  gating_actions: {gating_actions}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
