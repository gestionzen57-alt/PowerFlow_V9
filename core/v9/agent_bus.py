"""Agent Bus V9 — bus d'événements SQLite (data/v9_agent_bus.db).

Découplage inter-composants : un composant V9 (pipeline, YAML, scoring,
dashboard, futur agent) publie un événement sans connaître qui le
consommera ; un agent s'abonne à un type d'événement sans connaître qui
le publie. Aucune dépendance externe (stdlib uniquement — sqlite3, json,
uuid, datetime). N'importe et ne modifie ni config.py, ni
orchestrator.py, ni principle_engine.py, ni principles/*.yaml.

3 tables :
  - events         : file d'événements publiés (consommation par agent).
  - subscriptions  : abonnements agent_name -> event_type -> callback.
  - agent_log      : historique des actions des agents (audit + stats).

Toutes les fonctions publiques acceptent un `db_path` optionnel (défaut
`data/v9_agent_bus.db`, cohérent avec le pattern `db_path: Path | None`
des autres modules `*_db.py` de V9).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.v9.config import ROOT_DIR
from core.v9.db_schema import get_connection as _base_get_connection

AGENT_BUS_DB_PATH = ROOT_DIR / "data" / "v9_agent_bus.db"

# Rétention fixe de agent_log (indépendante du paramètre `days` de
# cleanup(), qui ne s'applique qu'à `events` — voir spec).
AGENT_LOG_RETENTION_DAYS = 30

AGENT_BUS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    payload TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    created_at TEXT NOT NULL,
    consumed_by TEXT,
    consumed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_consumed
    ON events (consumed_by, created_at);

CREATE INDEX IF NOT EXISTS idx_events_type
    ON events (event_type);

CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    callback TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'free',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_agent_type
    ON subscriptions (agent_name, event_type);

CREATE TABLE IF NOT EXISTS agent_log (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    event_id TEXT,
    action TEXT NOT NULL,
    result TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_log_agent_created
    ON agent_log (agent_name, created_at);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Connexion sqlite3 (WAL, busy_timeout 30s) sur v9_agent_bus.db par défaut."""
    return _base_get_connection(db_path or AGENT_BUS_DB_PATH)


def init_agent_bus_db(db_path: Path | None = None) -> None:
    """Crée les 3 tables du bus si absentes. Idempotent."""
    conn = get_connection(db_path)
    try:
        conn.executescript(AGENT_BUS_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _log_action(
    conn: sqlite3.Connection,
    agent_name: str,
    event_id: str | None,
    action: str,
    result: dict[str, Any],
    duration_ms: int,
) -> None:
    conn.execute(
        "INSERT INTO agent_log (id, agent_name, event_id, action, result, "
        "duration_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_new_id(), agent_name, event_id, action, json.dumps(result), duration_ms, _now_iso()),
    )


def publish(
    event_type: str,
    source: str,
    payload: dict[str, Any],
    severity: str = "info",
    db_path: Path | None = None,
) -> str:
    """Publie un événement sur le bus. Retourne l'event_id créé."""
    start = time.monotonic()
    event_id = _new_id()
    created_at = _now_iso()
    conn = get_connection(db_path)
    try:
        init_agent_bus_db(db_path)
        conn.execute(
            "INSERT INTO events (id, event_type, source, payload, severity, "
            "created_at, consumed_by, consumed_at) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)",
            (event_id, event_type, source, json.dumps(payload), severity, created_at),
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        _log_action(
            conn, source, event_id, "publish",
            {"event_type": event_type, "severity": severity}, duration_ms,
        )
        conn.commit()
    finally:
        conn.close()
    return event_id


def subscribe(
    agent_name: str,
    event_type: str,
    callback: str,
    provider: str = "free",
    db_path: Path | None = None,
) -> str:
    """Enregistre un abonnement agent_name -> event_type. Retourne subscription_id."""
    subscription_id = _new_id()
    conn = get_connection(db_path)
    try:
        init_agent_bus_db(db_path)
        conn.execute(
            "INSERT INTO subscriptions (id, agent_name, event_type, callback, "
            "provider, enabled, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (subscription_id, agent_name, event_type, callback, provider, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return subscription_id


def _row_to_event_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
    except (TypeError, json.JSONDecodeError):
        d["payload"] = {}
    return d


def poll(agent_name: str, limit: int = 5, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Récupère jusqu'à `limit` événements non consommés correspondant aux
    abonnements actifs de `agent_name`, et les marque consumed_by=agent_name.
    Retourne [] si l'agent n'a aucun abonnement actif."""
    start = time.monotonic()
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        init_agent_bus_db(db_path)
        sub_rows = conn.execute(
            "SELECT DISTINCT event_type FROM subscriptions "
            "WHERE agent_name = ? AND enabled = 1",
            (agent_name,),
        ).fetchall()
        event_types = [r["event_type"] for r in sub_rows]
        if not event_types:
            return []

        placeholders = ",".join("?" for _ in event_types)
        rows = conn.execute(
            f"SELECT * FROM events WHERE consumed_by IS NULL "
            f"AND event_type IN ({placeholders}) "
            f"ORDER BY created_at ASC LIMIT ?",
            (*event_types, limit),
        ).fetchall()

        events = [_row_to_event_dict(r) for r in rows]
        consumed_at = _now_iso()
        for ev in events:
            conn.execute(
                "UPDATE events SET consumed_by = ?, consumed_at = ? WHERE id = ?",
                (agent_name, consumed_at, ev["id"]),
            )
            ev["consumed_by"] = agent_name
            ev["consumed_at"] = consumed_at

        duration_ms = int((time.monotonic() - start) * 1000)
        _log_action(
            conn, agent_name, None, "poll",
            {"n_events": len(events)}, duration_ms,
        )
        conn.commit()
        return events
    finally:
        conn.close()


def get_pending_events(limit: int = 20, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Événements non consommés, tous agents confondus, triés created_at ASC.
    Vue globale pour le meta-agent de supervision — ne marque rien consommé."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        init_agent_bus_db(db_path)
        rows = conn.execute(
            "SELECT * FROM events WHERE consumed_by IS NULL "
            "ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_event_dict(r) for r in rows]
    finally:
        conn.close()


def get_agent_stats(hours: int = 24, db_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Statistiques par agent sur les `hours` dernières heures : nombre
    d'événements traités (action='publish'|'poll'|'consume'), durée
    moyenne (ms), nombre d'erreurs (action='error'). Pour le dashboard."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        init_agent_bus_db(db_path)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT agent_name, action, duration_ms FROM agent_log "
            "WHERE created_at >= ?",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    stats: dict[str, dict[str, Any]] = {}
    for r in rows:
        agent = r["agent_name"]
        entry = stats.setdefault(
            agent, {"events_processed": 0, "avg_duration_ms": 0.0, "errors": 0}
        )
        entry["events_processed"] += 1
        entry["errors"] += 1 if r["action"] == "error" else 0

    durations: dict[str, list[int]] = {}
    for r in rows:
        if r["duration_ms"] is not None:
            durations.setdefault(r["agent_name"], []).append(r["duration_ms"])
    for agent, values in durations.items():
        stats[agent]["avg_duration_ms"] = sum(values) / len(values)

    return stats


def cleanup(days: int = 7, db_path: Path | None = None) -> dict[str, int]:
    """Purge les `events` de plus de `days` jours et les `agent_log` de
    plus de AGENT_LOG_RETENTION_DAYS (30) jours. Retourne les compteurs
    supprimés."""
    conn = get_connection(db_path)
    try:
        init_agent_bus_db(db_path)
        events_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        log_cutoff = (
            datetime.now(timezone.utc) - timedelta(days=AGENT_LOG_RETENTION_DAYS)
        ).isoformat()

        cur = conn.execute("DELETE FROM events WHERE created_at < ?", (events_cutoff,))
        events_purged = cur.rowcount

        cur = conn.execute("DELETE FROM agent_log WHERE created_at < ?", (log_cutoff,))
        agent_log_purged = cur.rowcount

        conn.commit()
    finally:
        conn.close()

    return {"events_purged": events_purged, "agent_log_purged": agent_log_purged}
