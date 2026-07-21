"""mcp-v9-meta-strategy-shadow — MCP server pour shadow logs Phase E (read-only strict).

Tools exposés :
- shadow_log_recent(since='24h', symbol=None, limit=100) → derniers shadow logs
- shadow_log_summary(since='24h') → agreement_rate + distributions par meta_strategy
- shadow_aggregate_overall(since='7d') → recalcule edge uplift (cohérent avec shadow.compute_edge_uplift)
- shadow_simulation_run(since='7d', limit=5000, force_meta=True) → wrapper v9_meta_strategy_simulation
- shadow_kill_switch_status() → V9_META_STRATEGY_SHADOW_ENABLED + V9_META_STRATEGY_OPTIMIZER_ENABLED

Sécurité : read-only via URI mode=ro. Wrapper Python sur modules core existants.

Origine : motion CEO 2026-07-21 08h00 UTC (auto-pilote maximal, gaps MCP Phase E).
Référence : commit `bf0ef9d` (Chemin A subset honnête + Chemin C shadow cron live).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"


def _connect() -> sqlite3.Connection:
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _since_ts(since: str) -> float:
    now = time.time()
    if since.endswith("h"):
        return now - int(since[:-1]) * 3600
    if since.endswith("d"):
        return now - int(since[:-1]) * 86400
    if since.endswith("m"):
        return now - int(since[:-1]) * 60
    raise ValueError(f"FORMAT since invalide ({since}): attendu '24h'/'7d'/'30d'")


def handle_shadow_log_recent(args: dict) -> dict:
    """Derniers shadow logs (legacy vs meta comparison)."""
    since = args.get("since", "24h")
    symbol = args.get("symbol")
    limit = min(int(args.get("limit", 100)), 500)
    since_ts = _since_ts(since)
    conn = _connect()
    try:
        where = ["s.created_at >= ?"]
        params: list = [since_ts]
        if symbol:
            where.append("s.symbol = ?")
            params.append(symbol)
        sql = f"""
            SELECT s.id, s.created_at, s.symbol, s.timeframe, s.regime_type,
                   s.phase, s.direction, s.legacy_strategy, s.legacy_confidence,
                   s.meta_strategy, s.meta_confidence, s.meta_source,
                   s.agreement, s.rationale
            FROM meta_strategy_shadow_log s
            WHERE {' AND '.join(where)}
            ORDER BY s.created_at DESC
            LIMIT ?
        """
        params.append(limit)
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return {
            "rows": [dict(zip(cols, r)) for r in rows],
            "count": len(rows),
            "since": since,
            "symbol_filter": symbol,
        }
    finally:
        conn.close()


def handle_shadow_log_summary(args: dict) -> dict:
    """Distribution par meta_strategy + agreement_rate global."""
    since = args.get("since", "24h")
    since_ts = _since_ts(since)
    conn = _connect()
    try:
        sql_agg = """
            SELECT COUNT(*) AS n,
                   AVG(agreement) AS agr,
                   AVG(meta_confidence) AS avg_meta_conf
            FROM meta_strategy_shadow_log
            WHERE created_at >= ?
        """
        row = conn.execute(sql_agg, (since_ts,)).fetchone()
        n = row["n"] if row else 0
        agreement_rate = round(row["agr"], 4) if row and row["agr"] is not None else 0.0
        avg_meta_conf = round(row["avg_meta_conf"], 4) if row and row["avg_meta_conf"] is not None else 0.0

        sql_meta = """
            SELECT meta_strategy, COUNT(*) AS n,
                   AVG(agreement) AS agr
            FROM meta_strategy_shadow_log
            WHERE created_at >= ?
            GROUP BY meta_strategy ORDER BY n DESC
        """
        by_meta = [dict(r) for r in conn.execute(sql_meta, (since_ts,)).fetchall()]
        sql_legacy = """
            SELECT legacy_strategy, COUNT(*) AS n
            FROM meta_strategy_shadow_log
            WHERE created_at >= ?
            GROUP BY legacy_strategy ORDER BY n DESC
        """
        by_legacy = [dict(r) for r in conn.execute(sql_legacy, (since_ts,)).fetchall()]
        sql_source = """
            SELECT meta_source, COUNT(*) AS n
            FROM meta_strategy_shadow_log
            WHERE created_at >= ?
            GROUP BY meta_source ORDER BY n DESC
        """
        by_source = [dict(r) for r in conn.execute(sql_source, (since_ts,)).fetchall()]
        return {
            "since": since,
            "n_shadows": n,
            "agreement_rate": agreement_rate,
            "avg_meta_confidence": avg_meta_conf,
            "by_meta_strategy": by_meta,
            "by_legacy_strategy": by_legacy,
            "by_meta_source": by_source,
        }
    finally:
        conn.close()


def handle_shadow_aggregate_overall(args: dict) -> dict:
    """Recalcule edge uplift legacy vs meta (cohérent avec compute_edge_uplift).

    Approche : JOIN shadow_log → decisions via snapshot_id, mais LIMIT 5000
    (perf acceptable sur 22k shadows). PAS subset honnête (cf simulation).
    """
    since = args.get("since", "7d")
    since_ts = _since_ts(since)
    limit = min(int(args.get("limit", 5000)), 20000)
    conn = _connect()
    try:
        sql = f"""
            SELECT s.legacy_strategy, s.meta_strategy,
                   COALESCE(d.resolution_pips, 0) AS pips,
                   COALESCE(d.is_win, 0) AS is_win
            FROM meta_strategy_shadow_log s
            JOIN decisions d ON d.symbol = s.symbol
                             AND d.timeframe = s.timeframe
                             AND d.regime_type = s.regime_type
                             AND d.direction = s.direction
            WHERE s.created_at >= ?
              AND d.is_win IS NOT NULL
              AND d.resolved_at IS NOT NULL
              AND d.resolved_at >= s.created_at - 86400  -- décision résolue dans la fenêtre
            LIMIT ?
        """
        rows = conn.execute(sql, (since_ts, limit)).fetchall()
        if not rows:
            return {"error": "no joined shadow+decision rows in window", "since": since}
        legacy_pips = [(r["legacy_strategy"], r["pips"]) for r in rows]
        meta_pips = [(r["meta_strategy"], r["pips"]) for r in rows]

        def _wr_pf(pairs):
            if not pairs:
                return 0.0, 0.0
            wins = [p for _, p in pairs if p > 0]
            losses = [p for _, p in pairs if p <= 0]
            wr = len(wins) / len(pairs)
            pf = (sum(wins) / max(1e-9, abs(sum(losses)))) if losses else float(sum(wins)) / 1e-9
            return wr, pf

        wr_l, pf_l = _wr_pf(legacy_pips)
        wr_m, pf_m = _wr_pf(meta_pips)
        return {
            "since": since,
            "n": len(rows),
            "limit": limit,
            "wr_legacy": round(wr_l, 4),
            "pf_legacy": round(pf_l, 2),
            "wr_meta": round(wr_m, 4),
            "pf_meta": round(pf_m, 2),
            "delta_wr": round(wr_m - wr_l, 4),
            "delta_pf": round(pf_m - pf_l, 2),
            "verdict": "GREEN_PROMOTE" if (wr_m - wr_l) >= 0.05 and (pf_m - pf_l) >= 0.5
                       else "RED_NO_UPLIFT" if (wr_m - wr_l) <= 0.01
                       else "YELLOW_MARGINAL",
        }
    finally:
        conn.close()


def handle_shadow_simulation_run(args: dict) -> dict:
    """Wrapper sur scripts/v9_meta_strategy_simulation.py run_simulation().

    Active temporairement V9_META_STRATEGY_SHADOW_ENABLED=1 (force_meta) sauf si explicitement False.
    """
    since = args.get("since", "7d")
    limit = min(int(args.get("limit", 5000)), 20000)
    force_meta = bool(args.get("force_meta", True))
    sys.path.insert(0, str(ROOT_DIR))
    try:
        os.environ["PYTHONPATH"] = str(ROOT_DIR)
        from scripts.v9_meta_strategy_simulation import run_simulation
        result = run_simulation(
            DB_PATH, since_ts=_since_ts(since), limit=limit, force_meta=force_meta,
        )
        return result
    except Exception as e:
        return {"error": str(e), "traceback": str(e.__class__.__name__)}


def handle_shadow_kill_switch_status(args: dict) -> dict:
    """Lit les kill switches shadow depuis env (process courant)."""
    return {
        "V9_META_STRATEGY_SHADOW_ENABLED": os.environ.get("V9_META_STRATEGY_SHADOW_ENABLED", "0"),
        "V9_META_STRATEGY_OPTIMIZER_ENABLED": os.environ.get("V9_META_STRATEGY_OPTIMIZER_ENABLED", "1"),
        "note": "valeurs = env process courant, peuvent différer du cron Windows",
    }


HANDLERS = {
    "shadow_log_recent": handle_shadow_log_recent,
    "shadow_log_summary": handle_shadow_log_summary,
    "shadow_aggregate_overall": handle_shadow_aggregate_overall,
    "shadow_simulation_run": handle_shadow_simulation_run,
    "shadow_kill_switch_status": handle_shadow_kill_switch_status,
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
                    {"name": "shadow_log_recent", "args": ["since", "symbol", "limit"]},
                    {"name": "shadow_log_summary", "args": ["since"]},
                    {"name": "shadow_aggregate_overall", "args": ["since"]},
                    {"name": "shadow_simulation_run", "args": ["since", "limit", "force_meta"]},
                    {"name": "shadow_kill_switch_status", "args": []},
                ]
            }))
        elif method.startswith("tools/call/"):
            name = method[len("tools/call/"):]
            args = req.get("args", {})
            handler = HANDLERS.get(name)
            if handler:
                print(json.dumps(handler(args), default=str))
            else:
                print(json.dumps({"error": f"unknown tool: {name}"}))


if __name__ == "__main__":
    main()