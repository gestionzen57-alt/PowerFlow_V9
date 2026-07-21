"""mcp-v9-paper-trade — MCP server pour paper_trades (read-only strict).

Tools exposés :
- paper_trades_recent(since='24h', symbol=None, limit=100) → liste filtrée
- paper_trades_stats(since='24h') → WR/PF/DD par symbol×TF×regime
- paper_trades_open() → positions non clôturées (closed_at NULL)
- paper_trades_resolution_breakdown() → distribution par resolution_strategy
- paper_trades_idempotency_check() → vérifie pas de doublons (motion #32)

Sécurité : read-only via URI mode=ro + whitelist tables autorisées.
Jointure snapshot_id → forces_snapshots.symbol (schéma live 2026-07-21).

Origine : motion CEO 2026-07-21 08h00 UTC (auto-pilote maximal, gaps MCP).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DB_PATH = ROOT_DIR / "data" / "v9_forces.db"


def _connect() -> sqlite3.Connection:
    """Read-only URI strict."""
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _since_ts(since: str) -> float:
    """Convertit '24h' / '7d' / '30d' / 'Nm' en timestamp epoch."""
    now = time.time()
    if since.endswith("h"):
        return now - int(since[:-1]) * 3600
    if since.endswith("d"):
        return now - int(since[:-1]) * 86400
    if since.endswith("m"):
        return now - int(since[:-1]) * 60
    raise ValueError(f"FORMAT since invalide ({since}): attendu '24h'/'7d'/'30d'")


def handle_paper_trades_recent(args: dict) -> dict:
    """Liste filtrée des paper_trades récentes.

    Args : since (str défaut '24h'), symbol (str|None), limit (int défaut 100 max 500).
    """
    since = args.get("since", "24h")
    symbol = args.get("symbol")
    limit = min(int(args.get("limit", 100)), 500)
    since_ts = _since_ts(since)
    conn = _connect()
    try:
        where = ["pt.closed_at IS NOT NULL", "pt.closed_at >= ?"]
        params: list = [since_ts]
        if symbol:
            where.append("fs.symbol = ?")
            params.append(symbol)
        sql = f"""
            SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.confiance,
                   pt.opened_at, pt.closed_at, pt.pips_simulated, pt.is_win,
                   pt.risk_go_context, fs.symbol, fs.timeframe
            FROM paper_trades pt
            JOIN forces_snapshots fs ON fs.snapshot_id = pt.snapshot_id
            WHERE {' AND '.join(where)}
            ORDER BY pt.closed_at DESC
            LIMIT ?
        """
        params.append(limit)
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return {
            "rows": [dict(zip(cols, r)) for r in rows],
            "count": len(rows),
            "truncated": cur.fetchone() is not None,
            "since": since,
            "symbol_filter": symbol,
        }
    finally:
        conn.close()


def handle_paper_trades_stats(args: dict) -> dict:
    """WR / PF / DD par (symbol, timeframe, regime_type) sur fenêtre temporelle."""
    since = args.get("since", "24h")
    since_ts = _since_ts(since)
    conn = _connect()
    try:
        sql = """
            SELECT pt.pips_simulated, pt.is_win
            FROM paper_trades pt
            WHERE pt.closed_at IS NOT NULL AND pt.closed_at >= ?
        """
        rows = conn.execute(sql, (since_ts,)).fetchall()
        if not rows:
            return {"error": "no data", "since": since}
        wins = [r["pips_simulated"] for r in rows if r["is_win"] == 1]
        losses = [r["pips_simulated"] for r in rows if r["is_win"] == 0]
        n = len(rows)
        gross_win = sum(wins)
        gross_loss = abs(sum(losses)) or 1e-9
        wr = len(wins) / n
        pf = gross_win / gross_loss
        cum = []
        running = 0
        peak = 0
        dd = 0
        for r in rows:
            running += r["pips_simulated"]
            peak = max(peak, running)
            dd = min(dd, running - peak)
        global_stats = {
            "n_trades": n,
            "wr": round(wr, 4),
            "pf": round(pf, 2),
            "gross_win_pips": round(gross_win, 2),
            "gross_loss_pips": round(sum(losses), 2),
            "max_drawdown_pips": round(dd, 2),
        }
        sql_seg = """
            SELECT fs.symbol, fs.timeframe,
                   COUNT(*) AS n,
                   SUM(CASE WHEN pt.is_win=1 THEN 1 ELSE 0 END) AS wins,
                   SUM(pt.pips_simulated) AS total_pips
            FROM paper_trades pt
            JOIN forces_snapshots fs ON fs.snapshot_id = pt.snapshot_id
            WHERE pt.closed_at IS NOT NULL AND pt.closed_at >= ?
            GROUP BY fs.symbol, fs.timeframe
            ORDER BY n DESC
            LIMIT 50
        """
        segs = []
        for r in conn.execute(sql_seg, (since_ts,)).fetchall():
            segs.append({
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "n": r["n"],
                "wr": round(r["wins"] / r["n"], 4),
                "total_pips": round(r["total_pips"], 2),
            })
        return {"since": since, "global": global_stats, "by_segment": segs}
    finally:
        conn.close()


def handle_paper_trades_open(args: dict) -> dict:
    """Positions non clôturées (closed_at NULL)."""
    conn = _connect()
    try:
        sql = """
            SELECT pt.trade_id, pt.snapshot_id, pt.direction, pt.confiance,
                   pt.opened_at, pt.risk_go_context,
                   fs.symbol, fs.timeframe, rs.regime_type
            FROM paper_trades pt
            JOIN forces_snapshots fs ON fs.snapshot_id = pt.snapshot_id
            LEFT JOIN regime_snapshots rs ON rs.symbol = fs.symbol AND rs.timeframe = fs.timeframe
            WHERE pt.closed_at IS NULL
            ORDER BY pt.opened_at DESC
        """
        cur = conn.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return {
            "rows": [dict(zip(cols, r)) for r in rows],
            "count": len(rows),
        }
    finally:
        conn.close()


def handle_paper_trades_resolution_breakdown(args: dict) -> dict:
    """Distribution par resolution_strategy (DYNAMIC vs SKIPPED vs UNKNOWN)."""
    since = args.get("since", "7d")
    since_ts = _since_ts(since)
    conn = _connect()
    try:
        sql = """
            SELECT COALESCE(d.resolution_strategy, 'UNKNOWN') AS strat,
                   COUNT(*) AS n,
                   SUM(CASE WHEN d.is_win=1 THEN 1 ELSE 0 END) AS wins,
                   ROUND(100.0 * SUM(CASE WHEN d.is_win=1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS wr,
                   SUM(d.resolution_pips) AS total_pips
            FROM decisions d
            WHERE d.is_win IS NOT NULL
              AND d.resolved_at IS NOT NULL
              AND d.resolved_at >= ?
            GROUP BY COALESCE(d.resolution_strategy, 'UNKNOWN')
            ORDER BY n DESC
        """
        rows = conn.execute(sql, (since_ts,)).fetchall()
        return {
            "since": since,
            "by_strategy": [dict(r) for r in rows],
            "n_total": sum(r["n"] for r in rows),
        }
    finally:
        conn.close()


def handle_paper_trades_idempotency_check(args: dict) -> dict:
    """Vérifie qu'aucun doublon (snapshot_id, opened_at) — cf motion #32 dedup."""
    conn = _connect()
    try:
        sql = """
            SELECT snapshot_id, opened_at, COUNT(*) AS n
            FROM paper_trades
            GROUP BY snapshot_id, opened_at
            HAVING n > 1
            LIMIT 20
        """
        dups = conn.execute(sql).fetchall()
        n_total = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        n_unique = conn.execute(
            "SELECT COUNT(DISTINCT (snapshot_id || '|' || opened_at)) FROM paper_trades"
        ).fetchone()[0]
        return {
            "n_total": n_total,
            "n_unique": n_unique,
            "n_dup_groups": len(dups),
            "dup_examples": [
                {"snapshot_id": r["snapshot_id"], "opened_at": r["opened_at"], "count": r["n"]}
                for r in dups[:5]
            ],
            "verdict": "OK" if not dups else "DUP_DETECTED",
        }
    finally:
        conn.close()


HANDLERS = {
    "paper_trades_recent": handle_paper_trades_recent,
    "paper_trades_stats": handle_paper_trades_stats,
    "paper_trades_open": handle_paper_trades_open,
    "paper_trades_resolution_breakdown": handle_paper_trades_resolution_breakdown,
    "paper_trades_idempotency_check": handle_paper_trades_idempotency_check,
}


def main() -> None:
    """MCP stdio loop (lit JSON-RPC lines from stdin, écrit sur stdout)."""
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
                    {"name": "paper_trades_recent", "args": ["since", "symbol", "limit"]},
                    {"name": "paper_trades_stats", "args": ["since"]},
                    {"name": "paper_trades_open", "args": []},
                    {"name": "paper_trades_resolution_breakdown", "args": ["since"]},
                    {"name": "paper_trades_idempotency_check", "args": []},
                ]
            }))
        elif method.startswith("tools/call/"):
            name = method[len("tools/call/"):]
            args = req.get("args", {})
            handler = HANDLERS.get(name)
            if handler:
                print(json.dumps(handler(args)))
            else:
                print(json.dumps({"error": f"unknown tool: {name}"}))


if __name__ == "__main__":
    main()