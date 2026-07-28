"""scripts/v9_auto_promotion_run.py — Runner CLI AutoPromotionEngine (Phase 2.2, 2026-07-28).

Auto-promotion R25'' stricte : évalue chaque principe et propose
promote/demote/keep basé sur WR, n_trades, sharpe (Bayesian posterior).

Modes :
  --evaluate   : dry-run, affiche les décisions sans muter.
  --apply      : motion CEO explicite, écrit en DB.
  --min-wr     : seuil WR minimum (default 0.70).
  --min-n      : nombre trades minimum (default 100).
  --min-sharpe : Sharpe minimum (default 1.0).

Doctrine : R25'' strict (motion CEO explicite pour --apply). R6 défensif.
Run daily 05:00 UTC via cron V9_AutoPromotionEvaluate (DRY-RUN, alerte CEO).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\projet\V9")
sys.path.insert(0, str(ROOT))

AP_VERSION = "1.0"


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-promotion R25'' (motion CEO 28/07)")
    parser.add_argument("--evaluate", action="store_true", default=True,
                        help="Dry-run, affiche décisions (défaut).")
    parser.add_argument("--apply", action="store_true",
                        help="Applique (motion CEO explicite, écrit en DB).")
    parser.add_argument("--min-wr", type=float, default=0.70)
    parser.add_argument("--min-n", type=int, default=100)
    parser.add_argument("--min-sharpe", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--alert-telegram", action="store_true",
                        help="Alerte CEO best-effort si démotions détectées.")
    args = parser.parse_args()

    if args.apply:
        print("[WARN] --apply : motion CEO explicite requise, écriture en DB.", file=sys.stderr)

    t0 = time.time()
    try:
        from core.v9.v9_auto_promotion import AutoPromotionEngine
        engine = AutoPromotionEngine(
            min_wr=args.min_wr, min_n_trades=args.min_n, min_sharpe=args.min_sharpe,
        )
        if args.apply:
            # Step 1: evaluate
            raw = engine.evaluate_principles()
            # Convert to dicts for compatibility
            decisions = [d.to_dict() if hasattr(d, "to_dict") else d.__dict__ for d in raw]
            # Step 2: apply (motion CEO explicite)
            n_applied = engine.apply_promotions(raw)  # raw = list[PromotionDecision]
            decisions_applied = [d for d in decisions if d.get("action") in ("promote", "demote")]
        else:
            raw = engine.evaluate_principles()
            decisions = [d.to_dict() if hasattr(d, "to_dict") else (d.__dict__ if hasattr(d, "__dict__") else d) for d in raw]
            n_applied = 0
            decisions_applied = []
    except Exception as exc:
        result = {
            "ap_version": AP_VERSION,
            "ok": False,
            "error": f"evaluate failed: {exc}",
            "duration_s": round(time.time() - t0, 2),
        }
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"auto_promotion: failed: {exc}")
        return 4

    # Stats
    n_total = len(decisions)
    n_promote = sum(1 for d in decisions if d.get("action") == "promote")
    n_demote = sum(1 for d in decisions if d.get("action") == "demote")
    n_keep = sum(1 for d in decisions if d.get("action") == "keep")
    exit_code = 0
    if args.apply and n_applied > 0:
        exit_code = 2  # motion appliquée

    result = {
        "ap_version": AP_VERSION,
        "ok": True,
        "applied": args.apply,
        "n_applied": n_applied,
        "thresholds": {"min_wr": args.min_wr, "min_n": args.min_n, "min_sharpe": args.min_sharpe},
        "n_total": n_total,
        "n_promote": n_promote,
        "n_demote": n_demote,
        "n_keep": n_keep,
        "decisions": decisions_applied if args.apply else decisions,
        "duration_s": round(time.time() - t0, 2),
        "exit_code": exit_code,
    }

    # Telegram best-effort si démotions détectées
    if args.alert_telegram and n_demote > 0:
        try:
            from core.v9.telegram_notifier import send_telegram_alert  # type: ignore
            msg = f"[V9 AutoPromotion] {n_demote} démotions recommandées:\n"
            for d in decisions[:5]:
                if d.get("action") == "demote":
                    msg += f"  {d['principle_id']} : {d['current_status']}→{d['new_status']}\n"
            send_telegram_alert(msg)
        except Exception as exc:
            print(f"[INFO] Telegram alert non envoyée ({exc})", file=sys.stderr)

    # Output
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"auto_promotion: applied={args.apply} promote={n_promote} demote={n_demote} keep={n_keep}")
        if n_demote > 0:
            print(f"  {n_demote} démotions recommandées (motion CEO requise pour apply)")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
