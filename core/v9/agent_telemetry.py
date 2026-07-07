"""Module télémétrie agents Mode A V9.

Table séparée `agent_telemetry` (SQLite, alongside forces_snapshots).
Vue `v_agent_precision_report` pour rapport journalier de précision par agent.

Conçu pour répondre au problème Søn : "intervenir sur une couche et mesurer
l'effet sans casser la chaîne".

Sprint V9 2026-07-07 — Hermes autonomous.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from core.v9.config import DB_PATH


SCHEMA_TELEMETRY = """
CREATE TABLE IF NOT EXISTS agent_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    snapshot_id TEXT,
    input_hash TEXT,
    output_hash TEXT,
    latency_ms REAL,
    status TEXT,
    drift_signal REAL DEFAULT 0.0,
    notes TEXT,
    source_type TEXT DEFAULT 'live'
);

CREATE INDEX IF NOT EXISTS idx_telemetry_agent_ts
    ON agent_telemetry (agent_name, ts);

CREATE VIEW IF NOT EXISTS v_agent_precision_report AS
SELECT
    agent_name,
    DATE(ts) AS jour,
    COUNT(*) AS hits,
    SUM(CASE WHEN status='ERROR' THEN 1 ELSE 0 END) AS errors,
    AVG(latency_ms) AS latence_moy_ms,
    MAX(latency_ms) AS latence_max_ms,
    AVG(drift_signal) AS drift_moy
FROM agent_telemetry
WHERE source_type='live'
GROUP BY agent_name, DATE(ts);
"""


@contextmanager
def _conn():
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_telemetry_db() -> None:
    """Crée la table agent_telemetry + vue si absentes. Idempotent."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript(SCHEMA_TELEMETRY)


def record(
    agent_name: str,
    snapshot_id: str | None = None,
    input_hash: str | None = None,
    output_hash: str | None = None,
    latency_ms: float = 0.0,
    status: str = "OK",
    drift_signal: float = 0.0,
    notes: str | None = None,
) -> int:
    """Enregistre un hit agent_telemetry. Retourne l'id inséré."""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO agent_telemetry
               (ts, agent_name, snapshot_id, input_hash, output_hash,
                latency_ms, status, drift_signal, notes, source_type)
               VALUES (?,?,?,?,?,?,?,?,?, 'live')""",
            (ts, agent_name, snapshot_id, input_hash, output_hash,
             latency_ms, status, drift_signal, notes),
        )
        return cur.lastrowid


def report(window_days: int = 7) -> list[dict]:
    """Rapport précision par agent sur les N derniers jours."""
    with _conn() as c:
        rows = c.execute(
            """SELECT agent_name,
                      SUM(hits) AS total_hits,
                      SUM(errors) AS total_errors,
                      AVG(latence_moy_ms) AS avg_latency_ms,
                      MAX(latence_max_ms) AS max_latency_ms,
                      AVG(drift_moy) AS avg_drift
               FROM v_agent_precision_report
               WHERE jour >= DATE('now', ?)
               GROUP BY agent_name
               ORDER BY agent_name""",
            (f"-{window_days} day",),
        ).fetchall()
        return [dict(r) for r in rows]
