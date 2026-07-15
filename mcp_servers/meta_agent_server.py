#!/usr/bin/env python3
"""mcp-v9-meta-agent — MCP server ciblé pour apprentissage meta-agent V9.

Tools exposés :
- scan(hours: int) → list[dict]              (scan_patterns)
- learn(hours: int) → list[dict]             (learn_cycle, publie propositions)
- proposals(limit: int) → list[dict]         (get_proposals)
- emit(lookback_hours: int) → dict           (v9_meta_agent_emit.run)
- stats() → dict                              (compteurs bus agent_bus.db)

Communication inter-MCP = bus agent_bus.db (publish/subscribe SQLite).
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
AGENT_BUS_DB = ROOT_DIR / "data" / "v9_agent_bus.db"


def handle_scan(args: dict) -> dict:
    hours = int(args.get("hours", 24))
    try:
        result = subprocess.run(
            [sys.executable, "scripts/v9_meta_agent.py", "--scan", "--hours", str(hours)],
            capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=30,
        )
        return {"exit_code": result.returncode, "output": result.stdout[-1500:]}
    except Exception as e:
        return {"error": str(e)}


def handle_learn(args: dict) -> dict:
    hours = int(args.get("hours", 24))
    try:
        result = subprocess.run(
            [sys.executable, "scripts/v9_meta_agent.py", "--learn", "--hours", str(hours)],
            capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=60,
        )
        return {"exit_code": result.returncode, "output": result.stdout[-2000:]}
    except Exception as e:
        return {"error": str(e)}


def handle_proposals(args: dict) -> dict:
    limit = int(args.get("limit", 5))
    try:
        result = subprocess.run(
            [sys.executable, "scripts/v9_meta_agent.py", "--proposals", "--limit", str(limit)],
            capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=15,
        )
        return {"exit_code": result.returncode, "output": result.stdout[-2000:]}
    except Exception as e:
        return {"error": str(e)}


def handle_emit(args: dict) -> dict:
    lookback_hours = int(args.get("lookback_hours", 24))
    try:
        result = subprocess.run(
            [sys.executable, "scripts/v9_meta_agent_emit.py", "--once",
             "--lookback-hours", str(lookback_hours)],
            capture_output=True, text=True, cwd=str(ROOT_DIR), timeout=60,
        )
        return {"exit_code": result.returncode, "output": result.stdout[-1500:]}
    except Exception as e:
        return {"error": str(e)}


def handle_stats(args: dict) -> dict:
    """Compteurs bus agent_bus.db."""
    if not AGENT_BUS_DB.exists():
        return {"db_exists": False}
    try:
        conn = sqlite3.connect(str(AGENT_BUS_DB), timeout=10)
        try:
            stats = {}
            for tbl in ("events", "subscriptions", "agent_log"):
                n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                stats[tbl] = n
            # Top 5 event_types 24h
            try:
                rows = conn.execute("""
                    SELECT event_type, COUNT(*) as n FROM events
                    WHERE created_at > datetime('now', '-24 hours')
                    GROUP BY event_type ORDER BY n DESC LIMIT 5
                """).fetchall()
                stats["top_events_24h"] = [{"event_type": r[0], "count": r[1]} for r in rows]
            except Exception:
                stats["top_events_24h"] = []
            return stats
        finally:
            conn.close()
    except Exception as e:
        return {"error": str(e)}


HANDLERS = {
    "scan": handle_scan,
    "learn": handle_learn,
    "proposals": handle_proposals,
    "emit": handle_emit,
    "stats": handle_stats,
}


def main() -> None:
    from stdio_runtime import serve

    serve(HANDLERS, "v9-meta-agent")


if __name__ == "__main__":
    main()