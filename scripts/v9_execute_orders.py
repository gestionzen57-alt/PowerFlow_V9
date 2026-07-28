"""scripts/v9_execute_orders.py — Runner d'exécution réelle d'ordres (Phase 12 dégel, 28/07).

Lit les paper_trades récents (status='open') et les envoie au bridge MT4 via
\`core.v9.order_executor.send_order()\`. Double verrou appliqué :
  1. V9_EXECUTION_ENABLED=1 (motion CEO 28/07)
  2. HITL confirmation pour ordres > 0.5 lots (hitl_reviews.verdict='approved')

Bridge : fichier JSON dans data/order_queue/ que l'EA MT4 doit lire
(action opérateur distincte, hors périmètre de cette session).

Doctrine : R2 additif (nouveau runner, 0 modif core/v9/), R6 défensif
(double verrou enforced par order_executor), R18 code pur, R25'
(pas d'auto-promotion d'ordres sans trade_engine.process validé).

CLI :
  --once        : 1 passe (défaut, cron live).
  --since-mins  : fenêtre paper_trades récents (default 5).
  --max-orders  : limite dure (default 10, R6 fail-safe).
  --json        : sortie structurée.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\projet\V9")
sys.path.insert(0, str(ROOT))

ORDER_RUNNER_VERSION = "1.0"
DEFAULT_MAX_ORDERS = 10
DEFAULT_SINCE_MINS = 5


def main() -> int:
    parser = argparse.ArgumentParser(description="V9 Execute Orders — Phase 12 dégel 28/07")
    parser.add_argument("--once", action="store_true", default=True)
    parser.add_argument("--since-mins", type=int, default=DEFAULT_SINCE_MINS)
    parser.add_argument("--max-orders", type=int, default=DEFAULT_MAX_ORDERS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--log-file", type=str,
                        default=str(ROOT / "logs" / "v9_execute_orders.log"))
    args = parser.parse_args()

    t0 = time.time()
    if not os.environ.get("V9_EXECUTION_ENABLED") == "1":
        # Tenter de charger via loader si pas déjà fait
        try:
            from core.v9.kill_switches import is_execution_enabled_ks
            if not is_execution_enabled_ks():
                return 3  # kill switch OFF
        except Exception:
            # Fallback : check direct env (pas chargé via wrapper .bat)
            pass

    try:
        from core.v9.order_executor import (
            send_order, OrderRequest,
            ExecutionDisabledError, HITLConfirmationRequiredError, InvalidOrderError,
        )
        from core.v9.db_schema import get_connection
    except Exception as exc:
        return _output_error(args, t0, f"import failed: {exc}")

    conn = get_connection(ROOT / "data" / "v9_forces.db")
    try:
        # Lire paper_trades récents ouverts
        cutoff_iso = (
            datetime.fromtimestamp(time.time() - args.since_mins * 60, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S")
        )
        rows = conn.execute(
            """
            SELECT trade_id, snapshot_id, direction, confiance,
                   principes_source, opened_at, risk_go_context
            FROM paper_trades
            WHERE closed_at IS NULL AND opened_at >= ?
            ORDER BY opened_at DESC LIMIT ?
            """,
            (cutoff_iso, args.max_orders),
        ).fetchall()
    finally:
        conn.close()

    results = {
        "order_runner_version": ORDER_RUNNER_VERSION,
        "ok": True,
        "n_paper_trades_seen": len(rows),
        "n_orders_sent": 0,
        "n_orders_blocked_hitl": 0,
        "n_orders_blocked_disabled": 0,
        "n_errors": 0,
        "orders": [],
        "duration_s": round(time.time() - t0, 2),
    }

    for row in rows:
        try:
            trade_id = row["trade_id"]
            symbol = row["risk_go_context"] if isinstance(row["risk_go_context"], str) else "GBPUSD"
            try:
                ctx = json.loads(row["risk_go_context"]) if isinstance(row["risk_go_context"], str) else {}
            except Exception:
                ctx = {}
            symbol = ctx.get("symbol", "GBPUSD")
            direction = row["direction"]
            # Sizing : 0.01 lot par défaut (sous seuil HITL 0.5)
            # Sera remplacé par UnifiedSizing câblage post-meta_strategy (Phase 2.3).
            lot = 0.01
            sl_pips = 10.0
            tp_pips = 20.0

            # Additif R2 motion CEO 28/07 : sizing_factor (pyramiding) depuis context.
            # Si sizing_factor > 1, lot = lot_base * sizing_factor (boost pyramiding).
            # Active sur les trades stars (1-3 principes, conf >= 75) qui passent
            # les 4 gates hedge fund (WR 100%).
            sizing_factor_applied = None
            try:
                sizing_factor = float((ctx or {}).get("sizing_factor") or 1.0)
                if sizing_factor > 1.0:
                    lot = round(lot * sizing_factor, 2)
                    # Cap broker MT4 standard : 100 lots max.
                    lot = min(lot, 100.0)
                    sizing_factor_applied = sizing_factor
            except Exception:
                pass
            order = OrderRequest(
                decision_id=trade_id, symbol=symbol, direction=direction,
                lot=lot, sl_pips=sl_pips, tp_pips=tp_pips,
            )
            result = send_order(order, db_path=ROOT / "data" / "v9_forces.db")
            results["n_orders_sent"] += 1 if result.get("sent") else 0
            if not result.get("sent") and result.get("reason") == "hitl_required":
                results["n_orders_blocked_hitl"] += 1
            order_entry = {
                "trade_id": trade_id, "symbol": symbol, "direction": direction,
                "lot": lot,
                "result": result,
            }
            if sizing_factor_applied is not None:
                order_entry["sizing_factor_applied"] = sizing_factor_applied
            results["orders"].append(order_entry)
        except HITLConfirmationRequiredError as exc:
            results["n_orders_blocked_hitl"] += 1
            results["orders"].append({
                "trade_id": row["trade_id"], "error": f"hitl_required: {exc}",
            })
        except ExecutionDisabledError as exc:
            results["n_orders_blocked_disabled"] += 1
            results["orders"].append({"trade_id": row["trade_id"], "error": f"disabled: {exc}"})
            break  # Verrou fermé, pas la peine de continuer
        except InvalidOrderError as exc:
            results["n_errors"] += 1
            results["orders"].append({"trade_id": row["trade_id"], "error": f"invalid: {exc}"})
        except Exception as exc:
            results["n_errors"] += 1
            results["orders"].append({"trade_id": row["trade_id"], "error": f"unknown: {exc}"})

    # Exit codes
    exit_code = 0
    if results["n_errors"] > 0:
        exit_code = 4
    elif results["n_orders_blocked_disabled"] > 0:
        exit_code = 3
    elif results["n_orders_sent"] > 0:
        exit_code = 0  # ordres envoyés, succès
    elif results["n_orders_blocked_hitl"] > 0:
        exit_code = 2  # gated par HITL (action CEO requise)

    results["exit_code"] = exit_code

    # Log JSONL
    try:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(results, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        sys.stderr.write(f"log append failed: {exc}\n")

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"execute_orders: seen={results['n_paper_trades_seen']} "
              f"sent={results['n_orders_sent']} hitl_blocked={results['n_orders_blocked_hitl']} "
              f"errors={results['n_errors']}")

    return exit_code


def _output_error(args, t0, msg):
    result = {
        "order_runner_version": ORDER_RUNNER_VERSION,
        "ok": False, "error": msg, "duration_s": round(time.time() - t0, 2),
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"execute_orders: error: {msg}")
    return 4


if __name__ == "__main__":
    sys.exit(main())
