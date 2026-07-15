#!/usr/bin/env python3
"""mcp-v9-sqlite — MCP server ciblé pour lecture DB V9 (read-only strict).

Tools exposés :
- query(sql: str, params: list) → list[dict]
- table_info(table: str) → list[dict]  (PRAGMA table_info)
- list_tables() → list[str]
- snapshot_stats() → dict  (forces/decisions/scènes counts, last timestamp)
- principle_scores_top(limit: int) → list[dict]  (Brief O2, regénérés 2026-07-14 commit 080fb3f)
- paper_trades_audit() → dict  (compte + WR par session + après F=A+B+C+D)

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
        "principles", "principle_scores",  # Brief O2, regénérés 2026-07-14 commit 080fb3f
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


def handle_principle_scores_top(args: dict) -> dict:
    """Top combinaisons de principes par win_rate (Brief O2, regénérés
    2026-07-14 commit 080fb3f depuis 8131 décisions DYNAMIC résolues).

    Returns:
        list[dict] : {principle_id, n_trades, n_wins, n_losses,
                       total_pips, avg_pips, win_rate, last_updated}
    """
    limit = args.get("limit", 20)
    if not isinstance(limit, int) or limit < 1 or limit > 200:
        return {"error": "limit doit être un entier entre 1 et 200"}
    try:
        conn = _connect("forces")
        try:
            cur = conn.execute(
                """SELECT principle_id, n_trades, n_wins, n_losses,
                          total_pips, avg_pips, win_rate, last_updated
                   FROM principle_scores
                   ORDER BY win_rate DESC, n_trades DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            n_total = conn.execute("SELECT COUNT(*) FROM principle_scores").fetchone()[0]
            return {"rows": rows, "count": len(rows), "total_in_table": n_total}
        finally:
            conn.close()
    except Exception as e:
        return {"error": str(e)}


def handle_paper_trades_audit(args: dict) -> dict:
    """Audit paper_trades après F=A+B+C+D (commit 080fb3f) : 71 paper_trades
    administratifs effacés (Søn 6051277 les avait marqués 0/0 en bloc),
    DB=live à 0 rows.

    Returns:
        dict : {total, by_direction, by_confiance_bucket,
                last_opened, last_closed, status}
    """
    try:
        conn = _connect("forces")
        try:
            n = conn.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
            if n == 0:
                return {
                    "status": "cleaned",
                    "total": 0,
                    "note": "paper_trades vide depuis F=A+B+C+D (commit 080fb3f, "
                            "2026-07-14). 71 trades administratifs effacés, dump préservé "
                            "docs/calibration/backups/2026-07-14_pre_F_setup/paper_trades_admin/.",
                }
            by_dir = [dict(r) for r in conn.execute(
                "SELECT direction, COUNT(*) as n FROM paper_trades GROUP BY direction"
            )]
            by_conf = [dict(r) for r in conn.execute(
                """SELECT
                       CASE WHEN confiance < 70 THEN '<70'
                            WHEN confiance < 80 THEN '70-80'
                            WHEN confiance < 90 THEN '80-90'
                            ELSE '90-100' END as bucket,
                       COUNT(*) as n,
                       SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN is_win=0 THEN 1 ELSE 0 END) as losses,
                       ROUND(AVG(pips_simulated), 2) as avg_pips
                   FROM paper_trades
                   GROUP BY bucket"""
            )]
            last_op = conn.execute("SELECT MAX(opened_at) FROM paper_trades").fetchone()[0]
            last_cl = conn.execute("SELECT MAX(closed_at) FROM paper_trades").fetchone()[0]
            return {
                "status": "has_data",
                "total": n,
                "by_direction": by_dir,
                "by_confiance_bucket": by_conf,
                "last_opened": last_op,
                "last_closed": last_cl,
            }
        finally:
            conn.close()
    except Exception as e:
        return {"error": str(e)}


HANDLERS = {
    "query": handle_query,
    "table_info": handle_table_info,
    "list_tables": handle_list_tables,
    "snapshot_stats": handle_snapshot_stats,
    "principle_scores_top": handle_principle_scores_top,
    "paper_trades_audit": handle_paper_trades_audit,
}


def main() -> None:
    from stdio_runtime import serve

    serve(HANDLERS, "v9-sqlite")


if __name__ == "__main__":
    main()