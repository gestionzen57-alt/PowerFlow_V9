"""mcp-v9-walk-forward — MCP server pour validation walk-forward (motion CEO 28/07).

Expose le WalkForwardValidator aux clients MCP (CEO self-service OOS) :
  - run_walk_forward(n_windows, symbol) → WalkForwardReport.to_dict()
  - compare_folds(fold_a, fold_b)       → delta expectancy OOS
  - get_oos_metrics(days)               → expectancy OOS + verdict
  - get_shadow_promotion_candidates()   → SHADOW avec meilleur OOS

Sécurité : lecture seule (URI mode=ro). Aucun write sur DB ou KS.
Origine : motion CEO auto-pilote 28/07, top-5 MCP à levier #4.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"
WF_DB_PATH = ROOT_DIR / "data" / "v9_forces.db"  # WalkForwardValidator lit decisions


def _connect_ro() -> sqlite3.Connection:
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def handle_run_walk_forward(args: dict) -> dict:
    """Lance la validation walk-forward complète.

    Args : n_windows (int, default 5), symbol (str|None).
    Returns : WalkForwardReport dict + folds détaillés.
    """
    n_windows = max(3, min(int(args.get("n_windows", 5)), 20))
    symbol = args.get("symbol")
    t0 = time.time()
    try:
        sys.path.insert(0, str(ROOT_DIR))
        from core.v9.walk_forward import WalkForwardValidator
        validator = WalkForwardValidator(db_path=WF_DB_PATH)
        report = validator.run(n_windows=n_windows, symbol=symbol)
        return {
            "ok": True,
            "duration_s": round(time.time() - t0, 2),
            "n_windows": n_windows,
            "symbol": symbol or "all",
            "report": {
                "verdict": report.verdict,
                "n_trades": report.n_trades,
                "n_windows": report.n_windows,
                "scope": report.scope,
                "mean_is_expectancy": round(report.mean_is_expectancy, 3),
                "mean_oos_expectancy": round(report.mean_oos_expectancy, 3),
                "degradation_ratio": round(report.degradation_ratio, 3),
                "oos_positive_folds": report.oos_positive_folds,
                "pooled_oos_p_value": round(report.pooled_oos_p_value, 6),
                "folds": [
                    {
                        "fold_idx": i,
                        "is_expectancy": round(f.is_expectancy, 3),
                        "oos_expectancy": round(f.oos_expectancy, 3),
                        "is_n_trades": f.is_n_trades,
                        "oos_n_trades": f.oos_n_trades,
                        "is_optimal_threshold": f.is_optimal_threshold,
                        "oos_positive": f.oos_expectancy > 0,
                    }
                    for i, f in enumerate(report.folds)
                ],
            },
        }
    except Exception as exc:
        return {"ok": False, "error": f"run_walk_forward failed: {exc}", "duration_s": round(time.time() - t0, 2)}


def handle_compare_folds(args: dict) -> dict:
    """Compare deux folds walk-forward (delta expectancy OOS).

    Args : n_windows (int, default 5), fold_a (int), fold_b (int).
    Returns : {fold_a: {...}, fold_b: {...}, delta: {...}}.
    """
    n_windows = max(3, min(int(args.get("n_windows", 5)), 20))
    fold_a = int(args.get("fold_a", 0))
    fold_b = int(args.get("fold_b", 1))
    try:
        sys.path.insert(0, str(ROOT_DIR))
        from core.v9.walk_forward import WalkForwardValidator
        validator = WalkForwardValidator(db_path=WF_DB_PATH)
        report = validator.run(n_windows=n_windows)
        if fold_a >= len(report.folds) or fold_b >= len(report.folds):
            return {"ok": False, "error": f"fold_idx out of range (n={len(report.folds)})"}
        fa = report.folds[fold_a]
        fb = report.folds[fold_b]
        return {
            "ok": True,
            "fold_a": {"idx": fold_a, "is_exp": round(fa.is_expectancy, 3), "oos_exp": round(fa.oos_expectancy, 3)},
            "fold_b": {"idx": fold_b, "is_exp": round(fb.is_expectancy, 3), "oos_exp": round(fb.oos_expectancy, 3)},
            "delta": {
                "is_delta": round(fa.is_expectancy - fb.is_expectancy, 3),
                "oos_delta": round(fa.oos_expectancy - fb.oos_expectancy, 3),
            },
        }
    except Exception as exc:
        return {"ok": False, "error": f"compare_folds failed: {exc}"}


def handle_get_oos_metrics(args: dict) -> dict:
    """Métriques OOS synthétiques (pour dashboard).

    Args : days (int, default 30), symbol (str|None).
    Returns : {n_trades, oos_expectancy, n_positive_folds, verdict}.
    """
    days = max(7, min(int(args.get("days", 30)), 90))
    symbol = args.get("symbol")
    conn = _connect_ro()
    try:
        # Filtre par date
        from datetime import datetime, timezone
        cutoff = datetime.fromtimestamp(time.time() - days * 86400, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        if symbol:
            row = conn.execute(
                "SELECT count(*) n, COALESCE(AVG(resolution_pips), 0) avg_pips, "
                "COALESCE(SUM(resolution_pips), 0) cum_pips, "
                "SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) wins "
                "FROM decisions WHERE is_win IS NOT NULL AND timestamp >= ? AND symbol = ?",
                (cutoff, symbol),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT count(*) n, COALESCE(AVG(resolution_pips), 0) avg_pips, "
                "COALESCE(SUM(resolution_pips), 0) cum_pips, "
                "SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) wins "
                "FROM decisions WHERE is_win IS NOT NULL AND timestamp >= ?",
                (cutoff,),
            ).fetchone()
        n, avg, cum, wins = row["n"], row["avg_pips"], row["cum_pips"], row["wins"] or 0
        wr = wins / max(n, 1)
        # Verdict OOS-like
        if n < 30:
            verdict = "DONNEES_INSUFFISANTES"
        elif avg > 1.0 and wr > 0.55:
            verdict = "EDGE_REEL"
        elif avg > 0 and wr > 0.45:
            verdict = "EDGE_REEL_DEGRADE"
        elif avg > 0:
            verdict = "NON_CONCLUANT"
        else:
            verdict = "OVERFITTING"
        return {
            "ok": True,
            "lookback_days": days,
            "symbol": symbol or "all",
            "n_trades": n,
            "wins": wins,
            "wr": round(wr, 4),
            "avg_pips_per_trade": round(avg, 3),
            "cum_pips": round(cum, 1),
            "verdict": verdict,
        }
    finally:
        conn.close()


def handle_get_shadow_promotion_candidates(args: dict) -> dict:
    """Identifie les SHADOW avec meilleur edge OOS (candidats promotion flash).

    Args : limit (int, default 5), min_trades (int, default 30), min_wr (float, default 0.50),
           min_cum_pips (float, default 0.0 — filtre edge expectancy positive).
    Returns : {ok, candidates: [{principle_id, n, wr, cum_pips, ...}], n_shadow}.
    """
    limit = max(1, min(int(args.get("limit", 5)), 20))
    min_trades = max(10, min(int(args.get("min_trades", 30)), 500))
    min_wr = max(0.0, min(float(args.get("min_wr", 0.50)), 1.0))
    min_cum_pips = float(args.get("min_cum_pips", 0.0))
    sys.path.insert(0, str(ROOT_DIR))
    try:
        from core.v9.config import PRINCIPLE_ACTIVE_IDS
        # Tous les principes YAML = ACTIVE ∪ SHADOW ; on prend les SHADOW = pas dans ACTIVE
        all_yaml_dir = ROOT_DIR / "core" / "v9" / "principles"
        all_ids = {p.stem for p in all_yaml_dir.glob("*.yaml")}
        shadow_ids = sorted(all_ids - set(PRINCIPLE_ACTIVE_IDS))
    except Exception as e:
        return {"ok": False, "error": f"failed to load PRINCIPLE_ACTIVE_IDS: {e}"}

    conn = _connect_ro()
    try:
        candidates = []
        for principle in shadow_ids:
            # Triggered evaluations → décisions résolues
            row = conn.execute(
                """
                SELECT count(*) n,
                       AVG(CASE WHEN d.is_win=1 THEN 1.0 ELSE 0.0 END) wr,
                       COALESCE(SUM(d.resolution_pips), 0) cum_pips,
                       COALESCE(AVG(d.resolution_pips), 0) avg_pips
                FROM decisions d
                INNER JOIN principle_evaluations pe
                    ON pe.snapshot_id = d.snapshot_id AND pe.triggered = 1
                WHERE pe.principle_id = ?
                  AND d.is_win IS NOT NULL
                """,
                (principle,),
            ).fetchone()
            n = row["n"] or 0
            if n < min_trades:
                continue
            wr = row["wr"] or 0
            if wr < min_wr:
                continue
            cum = row["cum_pips"] or 0
            if cum < min_cum_pips:
                continue
            avg = row["avg_pips"] or 0
            candidates.append({
                "principle_id": principle,
                "n_trades": n,
                "wr": round(wr, 4),
                "cum_pips": round(cum, 1),
                "avg_pips_per_trade": round(avg, 3),
                "promotion_score": round(wr * 100 + cum / 10, 2),
            })
        candidates.sort(key=lambda x: x["promotion_score"], reverse=True)
        return {
            "ok": True,
            "n_shadow_total": len(shadow_ids),
            "n_candidates": len(candidates),
            "min_trades": min_trades,
            "min_wr": min_wr,
            "min_cum_pips": min_cum_pips,
            "candidates": candidates[:limit],
        }
    finally:
        conn.close()


HANDLERS = {
    "walk_forward_run": handle_run_walk_forward,
    "walk_forward_compare_folds": handle_compare_folds,
    "walk_forward_get_oos_metrics": handle_get_oos_metrics,
    "walk_forward_get_shadow_promotion_candidates": handle_get_shadow_promotion_candidates,
}


def main() -> None:
    """MCP stdio loop."""
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            print(json.dumps({"error": f"invalid json: {e}"}))
            continue
        method = req.get("method", "")
        if method == "tools/list":
            print(json.dumps({
                "tools": [
                    {"name": "walk_forward_run", "args": ["n_windows", "symbol"]},
                    {"name": "walk_forward_compare_folds", "args": ["n_windows", "fold_a", "fold_b"]},
                    {"name": "walk_forward_get_oos_metrics", "args": ["days", "symbol"]},
                    {"name": "walk_forward_get_shadow_promotion_candidates", "args": ["limit", "min_trades", "min_wr", "min_cum_pips"]},
                ]
            }))
        elif method.startswith("tools/call/"):
            name = method[len("tools/call/"):]
            args = req.get("args", {})
            handler = HANDLERS.get(name)
            if handler:
                print(json.dumps(handler(args), ensure_ascii=False, default=str))
            else:
                print(json.dumps({"error": f"unknown tool: {name}"}))


if __name__ == "__main__":
    main()
