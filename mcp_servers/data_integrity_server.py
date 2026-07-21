"""mcp-v9-data-integrity — MCP server pour audit DB integrity (read-only strict).

Tools exposés :
- stream_freshness(symbol=None, timeframe=None, max_stale_min=10) → LIVE/LENT/MORT par stream
- db_table_stats() → n_lignes + first/last timestamp + distribution source_type par table
- duplicates_check(table='forces_snapshots') → ratio total/unique par symbol
- disk_size() → taille DB + tables lourdes
- streams_health_summary(max_stale_min=10) → % LIVE/LENT/MORT + alert si >30% MORT

Sécurité : read-only via URI mode=ro. Audit 2026-07-21 04:56 UTC : 28/42 streams
MT4 morts (67%) — ce MCP automatise la détection.

Origine : motion CEO 2026-07-21 08h00 UTC (auto-pilote maximal, gaps MCP).
Référence : docs/audits/DATA_INTEGRITY_REPORT_20260721.md.
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


def handle_stream_freshness(args: dict) -> dict:
    """Fraicheur par (symbol, timeframe). LIVE/LENT/MORT selon max_stale_min."""
    symbol = args.get("symbol")
    timeframe = args.get("timeframe")
    max_stale_min = int(args.get("max_stale_min", 10))
    conn = _connect()
    try:
        where = []
        params: list = []
        if symbol:
            where.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            where.append("timeframe = ?")
            params.append(timeframe)
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        sql = f"""
            SELECT symbol, timeframe,
                   MAX(created_at) AS last_capture,
                   CAST((julianday('now') - julianday(MAX(created_at))) * 24 * 60 AS INTEGER) AS minutes_ago,
                   COUNT(*) AS n_captures
            FROM regime_snapshots
            {where_sql}
            GROUP BY symbol, timeframe
            ORDER BY minutes_ago DESC
        """
        rows = []
        for r in conn.execute(sql, params).fetchall():
            ma = r["minutes_ago"]
            status = "MORT" if ma > 60 else ("LENT" if ma > max_stale_min else "LIVE")
            rows.append({
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "last_capture": r["last_capture"],
                "minutes_ago": ma,
                "n_captures": r["n_captures"],
                "status": status,
            })
        return {"streams": rows, "max_stale_min": max_stale_min, "count": len(rows)}
    finally:
        conn.close()


def handle_db_table_stats(args: dict) -> dict:
    """Stats par table : n_lignes + first/last timestamp + source_type distribution."""
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [r[0] for r in cur.fetchall()]
        stats = []
        for t in tables:
            try:
                cols = [d[1] for d in conn.execute(f"PRAGMA table_info({t})").fetchall()]
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                first = last = None
                if "created_at" in cols:
                    first = conn.execute(f"SELECT MIN(created_at) FROM {t}").fetchone()[0]
                    last = conn.execute(f"SELECT MAX(created_at) FROM {t}").fetchone()[0]
                elif "timestamp" in cols:
                    first = conn.execute(f"SELECT MIN(timestamp) FROM {t}").fetchone()[0]
                    last = conn.execute(f"SELECT MAX(timestamp) FROM {t}").fetchone()[0]
                src_dist = {}
                if "source_type" in cols:
                    for sr in conn.execute(
                        f"SELECT source_type, COUNT(*) AS n FROM {t} GROUP BY source_type ORDER BY n DESC"
                    ).fetchall():
                        src_dist[sr["source_type"]] = sr["n"]
                stats.append({
                    "table": t,
                    "n_rows": n,
                    "first": first,
                    "last": last,
                    "source_type_distribution": src_dist if src_dist else None,
                })
            except Exception as e:
                stats.append({"table": t, "error": str(e)})
        return {"tables": stats, "count": len(stats)}
    finally:
        conn.close()


def handle_duplicates_check(args: dict) -> dict:
    """Ratio total/unique sur table (défaut forces_snapshots)."""
    table = args.get("table", "forces_snapshots")
    conn = _connect()
    try:
        cols = [d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        id_col = "snapshot_id" if "snapshot_id" in cols else (cols[1] if len(cols) > 1 else cols[0])
        n_total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        n_unique = conn.execute(f"SELECT COUNT(DISTINCT {id_col}) FROM {table}").fetchone()[0]
        ratio = round(n_total / max(1, n_unique), 4)
        verdict = "OK" if ratio <= 1.0 else "DUP_DETECTED"
        # Top duplicated
        sql = f"""
            SELECT {id_col}, COUNT(*) AS n
            FROM {table}
            GROUP BY {id_col}
            HAVING n > 1
            ORDER BY n DESC
            LIMIT 10
        """
        dups = [dict(r) for r in conn.execute(sql).fetchall()]
        return {
            "table": table,
            "id_column": id_col,
            "n_total": n_total,
            "n_unique": n_unique,
            "ratio": ratio,
            "n_dup_groups": len(dups),
            "dup_top": dups,
            "verdict": verdict,
        }
    finally:
        conn.close()


def handle_disk_size(args: dict) -> dict:
    """Taille DB + breakdown par table."""
    db_bytes = DB_PATH.stat().st_size
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [r[0] for r in cur.fetchall()]
        breakdown = []
        for t in tables:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            breakdown.append({"table": t, "n_rows": n})
        breakdown.sort(key=lambda x: -x["n_rows"])
        return {
            "db_path": str(DB_PATH),
            "db_size_bytes": db_bytes,
            "db_size_gb": round(db_bytes / 1e9, 3),
            "tables_breakdown": breakdown,
            "n_tables": len(tables),
        }
    finally:
        conn.close()


def handle_streams_health_summary(args: dict) -> dict:
    """% LIVE/LENT/MORT global + alert si >30% MORT."""
    max_stale_min = int(args.get("max_stale_min", 10))
    res = handle_stream_freshness({"max_stale_min": max_stale_min})
    streams = res.get("streams", [])
    if not streams:
        return {"error": "no streams"}
    by_status = {"LIVE": 0, "LENT": 0, "MORT": 0}
    for s in streams:
        by_status[s["status"]] = by_status.get(s["status"], 0) + 1
    n = len(streams)
    pct_mort = round(by_status["MORT"] / n * 100, 1)
    alert = None
    if pct_mort > 30:
        alert = f"🔴 ALERT: {pct_mort}% streams MORT (>30% seuil)"
    elif pct_mort > 10:
        alert = f"🟡 WARN: {pct_mort}% streams MORT"
    return {
        "max_stale_min": max_stale_min,
        "n_streams": n,
        "by_status": by_status,
        "pct_mort": pct_mort,
        "pct_live": round(by_status["LIVE"] / n * 100, 1),
        "pct_lent": round(by_status["LENT"] / n * 100, 1),
        "alert": alert,
        "verdict": "HEALTHY" if pct_mort <= 10 else ("DEGRADED" if pct_mort <= 30 else "CRITICAL"),
    }


HANDLERS = {
    "stream_freshness": handle_stream_freshness,
    "db_table_stats": handle_db_table_stats,
    "duplicates_check": handle_duplicates_check,
    "disk_size": handle_disk_size,
    "streams_health_summary": handle_streams_health_summary,
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
                    {"name": "stream_freshness", "args": ["symbol", "timeframe", "max_stale_min"]},
                    {"name": "db_table_stats", "args": []},
                    {"name": "duplicates_check", "args": ["table"]},
                    {"name": "disk_size", "args": []},
                    {"name": "streams_health_summary", "args": ["max_stale_min"]},
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