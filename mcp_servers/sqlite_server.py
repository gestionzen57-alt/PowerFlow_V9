#!/usr/bin/env python3
"""mcp-v9-sqlite — MCP server ciblé pour lecture DB V9 (read-only strict).

Tools exposés :
- query(sql: str, params: list) → list[dict]
- table_info(table: str) → list[dict]  (PRAGMA table_info)
- list_tables() → list[str]
- snapshot_stats() → dict  (forces/decisions/scènes counts, last timestamp)

Sécurité : read-only via URI mode=ro + whitelist tables autorisées.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
DB_PATHS = {
    "forces": ROOT_DIR / "data" / "v9_forces.db",
    "agent_bus": ROOT_DIR / "data" / "v9_agent_bus.db",
}

# Whitelist des tables accessibles (read-only strict)
ALLOWED_TABLES = {
    "forces": [
        "forces_snapshots", "scenes", "behaviors", "windows", "exploitability",
        "regime_snapshots", "principle_evaluations", "signals", "decisions",
        "paper_trades", "agent_telemetry", "probe_events", "zone_diagnostics",
        "principles",
    ],
    "agent_bus": ["events", "subscriptions", "agent_log", "cognitive_journal"],
}


def _connect(db_name: str) -> sqlite3.Connection:
    if db_name not in DB_PATHS:
        raise ValueError(f"unknown db: {db_name}")
    path = DB_PATHS[db_name]
    # Read-only URI pour SQLite (impossible d'écrire)
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def handle_query(args: dict) -> dict:
    sql = args.get("sql", "").strip()
    db = args.get("db", "forces")
    params = args.get("params", [])
    if not sql:
        return {"error": "sql manquant"}
    # Garde-fou : interdiction DELETE/INSERT/UPDATE/DROP/REPLACE
    sql_upper = sql.upper().lstrip()
    if any(sql_upper.startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "REPLACE", "CREATE", "ALTER")):
        return {"error": f"opération interdite (read-only): {sql_upper.split()[0]}"}
    try:
        conn = _connect(db)
        try:
            cur = conn.execute(sql, params)
            rows = cur.fetchmany(500)  # limite à 500 lignes
            cols = [d[0] for d in cur.description]
            return {
                "rows": [dict(zip(cols, r)) for r in rows],
                "count": len(rows),
                "truncated": cur.fetchone() is not None,
            }
        finally:
            conn.close()
    except Exception as e:
        return {"error": str(e)}


def handle_table_info(args: dict) -> dict:
    table = args.get("table", "")
    db = args.get("db", "forces")
    if table not in ALLOWED_TABLES.get(db, []):
        return {"error": f"table '{table}' not in whitelist for db '{db}'"}
    try:
        conn = _connect(db)
        try:
            cur = conn.execute(f"PRAGMA table_info({table})")
            cols = [dict(r) for r in cur.fetchall()]
            # Compte
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            return {"table": table, "columns": cols, "row_count": n}
        finally:
            conn.close()
    except Exception as e:
        return {"error": str(e)}


def handle_list_tables(args: dict) -> dict:
    db = args.get("db", "forces")
    return {"db": db, "tables": ALLOWED_TABLES.get(db, [])}


def handle_snapshot_stats(args: dict) -> dict:
    """Compteurs rapides + dernier snapshot."""
    try:
        conn = _connect("forces")
        try:
            stats = {}
            for tbl in ("forces_snapshots", "scenes", "signals", "decisions",
                        "principle_evaluations", "paper_trades"):
                n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                stats[tbl] = n
            # Last snapshot timestamp
            ts = conn.execute("SELECT MAX(timestamp) FROM forces_snapshots").fetchone()[0]
            stats["last_snapshot_ts"] = ts
            if ts:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                age_s = (datetime.now(timezone.utc) - dt).total_seconds()
                stats["last_snapshot_age_s"] = int(age_s)
            # WR global
            wr = conn.execute("""
                SELECT
                    SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN is_win IS NULL AND action='preparer_entree' THEN 1 ELSE 0 END)
                FROM decisions
            """).fetchone()
            wins, losses, open_dec = wr[0] or 0, wr[1] or 0, wr[2] or 0
            stats["win_loss"] = {"wins": wins, "losses": losses, "open": open_dec,
                                 "wr_pct": round(wins / (wins + losses) * 100, 2) if (wins + losses) > 0 else 0}
            return stats
        finally:
            conn.close()
    except Exception as e:
        return {"error": str(e)}


HANDLERS = {
    "query": handle_query,
    "table_info": handle_table_info,
    "list_tables": handle_list_tables,
    "snapshot_stats": handle_snapshot_stats,
}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            tool = req.get("tool")
            args = req.get("args", {})
            handler = HANDLERS.get(tool)
            if not handler:
                result = {"error": f"unknown tool: {tool}"}
            else:
                result = handler(args)
            print(json.dumps({"id": req.get("id"), "result": result}, default=str), flush=True)
        except Exception as e:
            print(json.dumps({"error": f"parse/handle error: {e}"}), flush=True)


if __name__ == "__main__":
    main()