"""mcp-v9-meta-agent-bus — MCP server pour le bus agent V9 → V10 (Phase 10 infra).

🚨 V10 doctrine (2026-08-04 05:00 UTC) : V9 verrouillé → V10 libre.
CEO mandate libération agentive. V10 = V11. Phase 10 (fédération agents)
dégelée par V10 R1-AGIR. Héritage V9 conservé.

Expose le bus agent `data/v9_agent_bus.db` aux clients MCP :
  - publish_event(type, source, payload, severity) → publie un événement
  - poll_events(profile, source, limit)             → consomme les événements
  - get_bus_stats(hours)                           → stats activité bus

Sécurité : write contrôlé (publish_event avec whitelist event_type).
Origine : motion CEO auto-pilote 2026-07-28 (top-3 MCP à levier, Phase 10 infra).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
BUS_DB = ROOT_DIR / "data" / "v9_agent_bus.db"

# Whitelist event_type pour publish_event (R6 défensif, R25' strict).
# Unpublished = R6 fail-safe.
EVENT_TYPE_WHITELIST = {
    # Auto-calibrator outputs
    "threshold_proposed", "calibration_applied", "overrides_updated",
    # Pipeline signals
    "decision_resolved", "force_anomaly_detected", "edge_decay_alert",
    # Strategy pole
    "strategy_pole_updated", "best_strategy_changed",
    # Hedge fund
    "risk_parity_rebalanced", "dd_palier_changed", "unified_sizing_applied",
    # Agent bus meta
    "agent_action_log", "agent_error", "agent_heartbeat",
}
SOURCE_WHITELIST = {"zcode", "hermes", "claude-cli", "mcp", "human-ceo"}


def _bus_connect_ro():
    """Connexion read-only pour poll/stats."""
    sys.path.insert(0, str(ROOT_DIR))
    from core.v9.agent_bus import get_connection, init_agent_bus_db
    init_agent_bus_db(BUS_DB)  # idempotent
    uri = f"file:{BUS_DB}?mode=ro"
    import sqlite3
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def handle_publish_event(args: dict) -> dict:
    """Publie un événement sur le bus (write contrôlé).

    Args : event_type (whitelist), source (whitelist), payload (dict), severity (default 'info').
    Returns : {ok, event_id, timestamp}.
    """
    event_type = args.get("event_type")
    source = args.get("source", "mcp")
    payload = args.get("payload") or {}
    severity = args.get("severity", "info")
    if event_type not in EVENT_TYPE_WHITELIST:
        return {
            "ok": False,
            "error": f"event_type '{event_type}' hors whitelist R6",
            "whitelist": sorted(EVENT_TYPE_WHITELIST),
        }
    if source not in SOURCE_WHITELIST:
        return {
            "ok": False,
            "error": f"source '{source}' hors whitelist",
            "whitelist": sorted(SOURCE_WHITELIST),
        }
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload doit être un dict JSON"}
    sys.path.insert(0, str(ROOT_DIR))
    from core.v9.agent_bus import publish
    event_id = publish(
        event_type=event_type, source=source,
        payload=payload, severity=severity, db_path=BUS_DB,
    )
    return {"ok": True, "event_id": event_id, "event_type": event_type, "source": source}


def handle_poll_events(args: dict) -> dict:
    """Consomme les événements en attente pour un profile.

    Args : agent_name (str), source (str, default None = all), limit (int, default 10).
    Returns : {ok, n_consumed, events: [...]}.
    """
    agent = args.get("agent_name") or args.get("profile")
    source = args.get("source")
    limit = min(int(args.get("limit", 10)), 50)
    if not agent:
        return {"ok": False, "error": "agent_name (ou profile) requis"}
    conn = _bus_connect_ro()
    try:
        if source:
            rows = conn.execute(
                "SELECT * FROM events WHERE source=? AND consumed_by IS NULL "
                "ORDER BY created_at ASC LIMIT ?",
                (source, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE consumed_by IS NULL "
                "ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        events = []
        for r in rows:
            ev = dict(r)
            try:
                ev["payload"] = json.loads(ev["payload"]) if ev.get("payload") else {}
            except Exception:
                pass
            events.append(ev)
        return {
            "ok": True,
            "n_consumed": len(events),
            "agent_name": agent,
            "source_filter": source,
            "events": events,
        }
    finally:
        conn.close()


def handle_get_bus_stats(args: dict) -> dict:
    """Stats activité bus (par type, par source, par sévérité).

    Args : hours (int, default 24).
    Returns : {ok, n_events_total, by_type: {...}, by_source: {...}, by_severity: {...}}.
    """
    hours = max(1, min(int(args.get("hours", 24)), 168))
    cutoff = (
        __import__("datetime").datetime.fromtimestamp(
            time.time() - hours * 3600, tz=__import__("datetime").timezone.utc
        ).isoformat()
    )
    conn = _bus_connect_ro()
    try:
        n_total = conn.execute(
            "SELECT count(*) FROM events WHERE created_at >= ?",
            (cutoff,),
        ).fetchone()[0]
        by_type = dict(conn.execute(
            "SELECT event_type, count(*) n FROM events WHERE created_at >= ? "
            "GROUP BY event_type ORDER BY n DESC",
            (cutoff,),
        ).fetchall())
        by_source = dict(conn.execute(
            "SELECT source, count(*) n FROM events WHERE created_at >= ? "
            "GROUP BY source ORDER BY n DESC",
            (cutoff,),
        ).fetchall())
        by_severity = dict(conn.execute(
            "SELECT severity, count(*) n FROM events WHERE created_at >= ? "
            "GROUP BY severity ORDER BY n DESC",
            (cutoff,),
        ).fetchall())
        n_consumed = conn.execute(
            "SELECT count(*) FROM events WHERE created_at >= ? AND consumed_by IS NOT NULL",
            (cutoff,),
        ).fetchone()[0]
        return {
            "ok": True,
            "lookback_hours": hours,
            "n_events_total": n_total,
            "n_consumed": n_consumed,
            "n_pending": n_total - n_consumed,
            "by_type": {k: v for k, v in (by_type or {}).items()},
            "by_source": {k: v for k, v in (by_source or {}).items()},
            "by_severity": {k: v for k, v in (by_severity or {}).items()},
        }
    finally:
        conn.close()


HANDLERS = {
    "bus_publish_event": handle_publish_event,
    "bus_poll_events": handle_poll_events,
    "bus_get_stats": handle_get_bus_stats,
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
                    {"name": "bus_publish_event", "args": ["event_type", "source", "payload", "severity"]},
                    {"name": "bus_poll_events", "args": ["agent_name", "source", "limit"]},
                    {"name": "bus_get_stats", "args": ["hours"]},
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
