#!/usr/bin/env python3
"""mcp-v9-strategy-pole — MCP server pour le pôle stratégie V9.

Tools exposés (11) :
- meta() → dict                        (métriques méta globales)
- catalogue(min_n) → list              (recalcule + retourne tous les segments)
- top(n, by) → list                    (top N stratégies par métrique)
- worst(n, min_n) → list               (bottom N stratégies)
- recommend(principle, session, regime) → dict
- tune(min_n) → list                   (grid search TP/SL + sauvegarde overrides)
- save_catalogue() → str               (chemin du fichier sauvegardé)
- live_snapshot(symbol) → dict         (forces H1/M15/M5 + dernière décision + trade ouvert)
- pair_breakdown(symbol) → dict        (stats paper-trade par direction baissière/baissière)
- principle_leaderboard(metric, limit) → list  (top N principes par métrique)
- dashboard_summary() → dict           (chiffres clés temps réel + kill switches)

Doctrine R18 : pas de LLM. Code pur sur data/v9_forces.db.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Permet l'import des modules core.v9
ROOT_DIR = Path(r"C:\projet\V9")
sys.path.insert(0, str(ROOT_DIR))

from core.v9.kill_switches import (  # noqa: E402
    adaptive_thresholds_wired_enabled,
    execution_enabled,
    shadow_mode_enabled,
    trader_mini_enabled,
)
from core.v9.v9_strategy_pole import (  # noqa: E402
    StrategyCatalogue,
    StrategySelector,
    StrategyTuner,
    compute_meta_metrics,
    get_connection,
)


def _serialize(obj: Any) -> Any:
    """Sérialise récursivement les dataclasses en dicts."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj


def handle_meta(args: dict) -> dict:
    """Métriques méta globales du paper-trade."""
    try:
        return _serialize(compute_meta_metrics())
    except Exception as exc:
        return {"error": str(exc)}


def handle_catalogue(args: dict) -> dict:
    """Recalcule le catalogue des stratégies. Retourne liste des segments."""
    try:
        min_n = int(args.get("min_n", 20))
        cat = StrategyCatalogue()
        n = cat.recompute(min_n=min_n)
        segments = _serialize(list(cat._cache.values()))
        return {"count": n, "min_n": min_n, "segments": segments}
    except Exception as exc:
        return {"error": str(exc)}


def handle_top(args: dict) -> dict:
    """Top N stratégies par métrique (avg_pips / confidence_score / profit_factor)."""
    try:
        n = int(args.get("n", 5))
        by = args.get("by", "avg_pips")
        min_n = int(args.get("min_n", 10))
        cat = StrategyCatalogue()
        cat.recompute(min_n=min_n)
        top = cat.top(n=n, by=by)
        return {"by": by, "count": len(top), "segments": _serialize(top)}
    except Exception as exc:
        return {"error": str(exc)}


def handle_worst(args: dict) -> dict:
    """Bottom N stratégies par expectancy (n >= min_n)."""
    try:
        n = int(args.get("n", 5))
        min_n = int(args.get("min_n", 20))
        cat = StrategyCatalogue()
        cat.recompute(min_n=min_n)
        worst = cat.worst(n=n, min_n=min_n)
        return {"count": len(worst), "segments": _serialize(worst)}
    except Exception as exc:
        return {"error": str(exc)}


def handle_recommend(args: dict) -> dict:
    """Recommandation stratégique pour (principle, session, regime)."""
    try:
        principle = args.get("principle")
        session = args.get("session")
        regime = args.get("regime")
        if not principle or not session or not regime:
            return {
                "error": "Missing required args: principle, session, regime",
            }
        cat = StrategyCatalogue()
        cat.recompute(min_n=10)
        selector = StrategySelector(catalogue=cat, tuner=StrategyTuner())
        rec = selector.recommend(principle, session, regime)
        return _serialize({
            "principle": rec.principle,
            "session": rec.session,
            "regime": rec.regime,
            "recommended_tp": rec.recommended_tp,
            "recommended_sl": rec.recommended_sl,
            "recommended_strategy": rec.recommended_strategy,
            "confidence": rec.confidence,
            "sample_size": rec.sample_size,
            "source": rec.source,
            "rationale": rec.rationale,
        })
    except Exception as exc:
        return {"error": str(exc)}


def handle_tune(args: dict) -> dict:
    """Tune tous les segments du catalogue (grid search TP/SL)."""
    try:
        min_n = int(args.get("min_n", 20))
        apply_overrides = bool(args.get("apply", True))

        cat = StrategyCatalogue()
        cat.recompute(min_n=min_n)
        tuner = StrategyTuner()
        results = tuner.tune_all(catalogue=cat)

        out = {"count": len(results), "min_n": min_n, "segments": results}
        if apply_overrides and results:
            path = tuner.save_overrides(results)
            out["overrides_path"] = str(path)
        return out
    except Exception as exc:
        return {"error": str(exc)}


def handle_save_catalogue(args: dict) -> dict:
    """Sauvegarde le catalogue dans data/strategy_pole/catalogue.json."""
    try:
        min_n = int(args.get("min_n", 20))
        cat = StrategyCatalogue()
        n = cat.recompute(min_n=min_n)
        path = cat.save_cache()
        return {"saved_segments": n, "path": str(path)}
    except Exception as exc:
        return {"error": str(exc)}


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convertit un sqlite3.Row en dict (None si absent)."""
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def handle_live_snapshot(args: dict) -> dict:
    """Snapshot temps réel pour un symbole : forces H1/M15/M5 + décision + trade ouvert.

    Args:
        symbol: ex. EURUSD, GBPUSD. Requis.

    Returns:
        {symbol, h1: {...}, m15: {...}, m5: {...},
         last_decision: {...} | null, open_trade: {...} | null}
    """
    try:
        symbol = (args.get("symbol") or "").upper()
        if not symbol:
            return {"error": "Missing required arg: symbol"}

        conn = get_connection(None)
        conn.row_factory = sqlite3.Row
        try:
            # Dernières forces par timeframe
            forces: dict[str, dict | None] = {}
            for tf in ("H1", "M15", "M5"):
                row = conn.execute(
                    """
                    SELECT timestamp, direction, force_usd, force_eur, force_gbp,
                           force_jpy, force_cad, force_chf, force_aud, force_nzd,
                           vitesse, croisement_detecte, stale
                    FROM forces_snapshots
                    WHERE symbol = ? AND timeframe = ?
                    ORDER BY timestamp DESC LIMIT 1
                    """,
                    (symbol, tf),
                ).fetchone()
                forces[tf.lower()] = _row_to_dict(row)

            # Dernière décision pour ce symbole (toutes TF)
            dec_row = conn.execute(
                """
                SELECT decision_id, timestamp, snapshot_id, action, direction,
                       confiance, regime_type, principes_json
                FROM decisions
                WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT 1
                """,
                (symbol,),
            ).fetchone()
            last_decision = _row_to_dict(dec_row)

            # Trade ouvert pour ce symbole (closed_at IS NULL)
            open_row = conn.execute(
                """
                SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.confiance,
                       pt.opened_at, pt.principes_source
                FROM paper_trades pt
                JOIN decisions d ON d.snapshot_id = pt.snapshot_id
                WHERE d.symbol = ? AND pt.closed_at IS NULL
                ORDER BY pt.opened_at DESC LIMIT 1
                """,
                (symbol,),
            ).fetchone()
            open_trade = _row_to_dict(open_row)
        finally:
            conn.close()

        return {
            "symbol": symbol,
            "h1": forces["h1"],
            "m15": forces["m15"],
            "m5": forces["m5"],
            "last_decision": last_decision,
            "open_trade": open_trade,
        }
    except Exception as exc:
        return {"error": str(exc)}


def handle_pair_breakdown(args: dict) -> dict:
    """Stats paper-trade par direction (baissiere/haussiere) pour un symbole.

    Args:
        symbol: ex. GBPUSD. Requis.

    Returns:
        {symbol, baissiere: {n, wr, pips}, haussiere: {n, wr, pips},
         total: {n, wr, pips}}
    """
    try:
        symbol = (args.get("symbol") or "").upper()
        if not symbol:
            return {"error": "Missing required arg: symbol"}

        conn = get_connection(None)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT d.direction AS direction,
                       COUNT(*) AS n,
                       ROUND(100.0 * SUM(CASE WHEN pt.is_win = 1 THEN 1 ELSE 0 END)
                             / COUNT(*), 2) AS wr,
                       ROUND(COALESCE(SUM(pt.pips_simulated), 0), 2) AS pips
                FROM paper_trades pt
                JOIN decisions d ON d.snapshot_id = pt.snapshot_id
                WHERE pt.closed_at IS NOT NULL
                  AND pt.pips_simulated IS NOT NULL
                  AND d.symbol = ?
                GROUP BY d.direction
                """,
                (symbol,),
            ).fetchall()
        finally:
            conn.close()

        by_dir = {r["direction"]: {"n": int(r["n"]),
                                   "wr": float(r["wr"] or 0),
                                   "pips": float(r["pips"] or 0)}
                  for r in rows}
        baissiere = by_dir.get("baissiere", {"n": 0, "wr": 0.0, "pips": 0.0})
        haussiere = by_dir.get("haussiere", {"n": 0, "wr": 0.0, "pips": 0.0})

        total_n = baissiere["n"] + haussiere["n"]
        total_pips = round(baissiere["pips"] + haussiere["pips"], 2)
        total_wins = round((baissiere["n"] * baissiere["wr"]
                            + haussiere["n"] * haussiere["wr"]) / 100, 2) \
            if total_n else 0.0
        total_wr = round(100.0 * total_wins / total_n, 2) if total_n else 0.0

        return {
            "symbol": symbol,
            "baissiere": baissiere,
            "haussiere": haussiere,
            "total": {"n": total_n, "wr": total_wr, "pips": total_pips},
        }
    except Exception as exc:
        return {"error": str(exc)}


# Métriques autorisées pour principle_leaderboard (colonne SQL ou alias).
_LEADERBOARD_METRICS: dict[str, str] = {
    "avg_pips": "avg_pips",
    "wr_pct": "wr_pct",
    "profit_factor": "profit_factor",
    "total_pips": "total_pips",
}


def handle_principle_leaderboard(args: dict) -> dict:
    """Top N principes par métrique (avg_pips / wr_pct / profit_factor / total_pips).

    Args:
        metric: nom métrique (défaut: avg_pips).
        limit: nb de lignes (défaut: 10).
        min_n: nb trades minimum par principe (défaut: 20).

    Returns:
        {metric, limit, min_n, count, principles: [{principle, n, wins, wr_pct,
         avg_pips, total_pips, profit_factor}, ...]}
    """
    try:
        metric = str(args.get("metric", "avg_pips")).lower()
        if metric not in _LEADERBOARD_METRICS:
            return {"error": f"Unknown metric: {metric!r}",
                    "available": list(_LEADERBOARD_METRICS.keys())}
        limit = int(args.get("limit", 10))
        min_n = int(args.get("min_n", 20))

        conn = get_connection(None)
        conn.row_factory = sqlite3.Row
        try:
            order_col = _LEADERBOARD_METRICS[metric]
            rows = conn.execute(
                f"""
                SELECT json_extract(pt.principes_source, '$[0]') AS principle,
                       COUNT(*) AS n,
                       SUM(CASE WHEN pt.is_win = 1 THEN 1 ELSE 0 END) AS wins,
                       ROUND(100.0 * SUM(CASE WHEN pt.is_win = 1 THEN 1 ELSE 0 END)
                             / COUNT(*), 2) AS wr_pct,
                       ROUND(AVG(pt.pips_simulated), 2) AS avg_pips,
                       ROUND(SUM(pt.pips_simulated), 2) AS total_pips,
                       ROUND(
                         CAST(SUM(CASE WHEN pt.is_win = 1
                                       THEN pt.pips_simulated ELSE 0 END) AS REAL)
                         / NULLIF(ABS(SUM(CASE WHEN pt.is_win = 0
                                               THEN pt.pips_simulated ELSE 0 END)), 0)
                       , 2) AS profit_factor
                FROM paper_trades pt
                JOIN decisions d ON d.snapshot_id = pt.snapshot_id
                WHERE pt.closed_at IS NOT NULL
                  AND pt.pips_simulated IS NOT NULL
                  AND json_extract(pt.principes_source, '$[0]') IS NOT NULL
                GROUP BY principle
                HAVING n >= ?
                ORDER BY {order_col} DESC
                LIMIT ?
                """,
                (min_n, limit),
            ).fetchall()
        finally:
            conn.close()

        principles = [{
            "principle": r["principle"],
            "n": int(r["n"]),
            "wins": int(r["wins"] or 0),
            "wr_pct": float(r["wr_pct"] or 0),
            "avg_pips": float(r["avg_pips"] or 0),
            "total_pips": float(r["total_pips"] or 0),
            "profit_factor": float(r["profit_factor"] or 0),
        } for r in rows]

        return {
            "metric": metric,
            "limit": limit,
            "min_n": min_n,
            "count": len(principles),
            "principles": principles,
        }
    except Exception as exc:
        return {"error": str(exc)}


def handle_dashboard_summary(args: dict) -> dict:
    """Snapshot condensé pour dashboard web temps réel.

    Combine : WR/PF/total_pips globaux, trades ouverts/fermés,
    last_snapshot timestamp, top 3 stratégies, kill switches clés.

    Args: aucun.

    Returns:
        {totals: {...}, open_trades: int, closed_trades: int,
         last_snapshot: str|None, top_3: [...], kill_switches: {...}}
    """
    try:
        meta = compute_meta_metrics()
        totals = meta.get("totals", {})

        conn = get_connection(None)
        conn.row_factory = sqlite3.Row
        try:
            counts = conn.execute(
                """
                SELECT SUM(CASE WHEN closed_at IS NULL THEN 1 ELSE 0 END) AS open_n,
                       SUM(CASE WHEN closed_at IS NOT NULL THEN 1 ELSE 0 END) AS closed_n
                FROM paper_trades
                """
            ).fetchone()
            last_snap = conn.execute(
                "SELECT MAX(timestamp) AS ts FROM forces_snapshots"
            ).fetchone()
        finally:
            conn.close()

        # Top 3 stratégies via le catalogue existant (DRY).
        cat = StrategyCatalogue()
        cat.recompute(min_n=20)
        top3 = cat.top(n=3, by="avg_pips")

        return {
            "totals": totals,
            "open_trades": int(counts["open_n"] or 0),
            "closed_trades": int(counts["closed_n"] or 0),
            "last_snapshot": last_snap["ts"] if last_snap else None,
            "top_3": _serialize(top3),
            "kill_switches": {
                "trader_mini": trader_mini_enabled(),
                "shadow_mode": shadow_mode_enabled(),
                "adaptive_thresholds_wired": adaptive_thresholds_wired_enabled(),
                "execution": execution_enabled(),
            },
            "generated_at": meta.get("generated_at"),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── Router stdio MCP ────────────────────────────────────────────────


HANDLERS = {
    "meta": handle_meta,
    "catalogue": handle_catalogue,
    "top": handle_top,
    "worst": handle_worst,
    "recommend": handle_recommend,
    "tune": handle_tune,
    "save_catalogue": handle_save_catalogue,
    "live_snapshot": handle_live_snapshot,
    "pair_breakdown": handle_pair_breakdown,
    "principle_leaderboard": handle_principle_leaderboard,
    "dashboard_summary": handle_dashboard_summary,
}


def main() -> int:
    """Point d'entrée stdio MCP. Lit les requêtes JSON-lines sur stdin."""
    print(json.dumps({"ready": True, "server": "v9_strategy_pole", "version": "1.0"}),
          flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            tool = req.get("tool")
            args = req.get("args", {})
            handler = HANDLERS.get(tool)
            if handler is None:
                resp = {"error": f"unknown tool: {tool!r}",
                        "available": list(HANDLERS.keys())}
            else:
                resp = handler(args)
        except json.JSONDecodeError as exc:
            resp = {"error": f"invalid JSON: {exc}"}
        except Exception as exc:
            resp = {"error": f"handler failed: {exc}"}
        print(json.dumps(resp, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())