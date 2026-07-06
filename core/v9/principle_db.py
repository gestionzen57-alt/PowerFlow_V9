"""Schéma DB V9 — tables `principles` et `principle_evaluations` (data/v9_forces.db).

Couche Décision (Phase 9) : `principles` est le catalogue des principes de
trading migrés tels quels depuis les 27 grammaires ACTIVE de V8
(`core/v9/principles/*.yaml`, voir docs/audit_v8_v9_migration.md §4.3).
`principle_evaluations` référence toujours son snapshot source
(`snapshot_id`) — une évaluation ne duplique jamais la scène/le
comportement/la fenêtre/l'exploitabilité, elle en tire une lecture
tardive et subordonnée (charte cognitive V9), au même titre que les
couches Fenêtres/Exploitabilité.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection, migrate_source_type

PRINCIPLE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS principles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    principle_id TEXT UNIQUE,
    version INTEGER,
    origin TEXT,
    kind TEXT,
    source_status TEXT,
    v9_status TEXT,
    scope_timeframes_json TEXT,
    scope_currencies_json TEXT,
    conditions_json TEXT,
    emits_json TEXT,
    bounds_json TEXT,
    anti_signal_bias BOOLEAN,
    notes TEXT,
    created_by TEXT,
    created_at_source TEXT,
    synced_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_principles_v9_status
    ON principles (v9_status);

CREATE TABLE IF NOT EXISTS principle_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    snapshot_id TEXT,
    principle_id TEXT,
    v9_status TEXT,
    kind TEXT,
    symbol TEXT,
    timeframe TEXT,
    currency TEXT,
    triggered BOOLEAN,
    direction TEXT,
    confidence INTEGER,
    anti_signal_bias BOOLEAN,
    reason TEXT,
    context_json TEXT,
    source_type TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_principle_evaluations_snapshot
    ON principle_evaluations (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_principle_evaluations_principle_triggered
    ON principle_evaluations (principle_id, triggered);
"""

# Colonnes hors id (auto-incrémenté), dans l'ordre de création —
# réutilisées par principle_engine.py pour les INSERT.
PRINCIPLES_COLUMNS = [
    "principle_id", "version", "origin", "kind", "source_status", "v9_status",
    "scope_timeframes_json", "scope_currencies_json",
    "conditions_json", "emits_json", "bounds_json",
    "anti_signal_bias", "notes", "created_by", "created_at_source", "synced_at",
]

PRINCIPLE_EVALUATIONS_COLUMNS = [
    "evaluation_id", "schema_version", "timestamp", "snapshot_id",
    "principle_id", "v9_status", "kind", "symbol", "timeframe", "currency",
    "triggered", "direction", "confidence", "anti_signal_bias", "reason",
    "context_json", "source_type", "created_at",
]


def init_principle_db(db_path: Path | None = None) -> None:
    """Crée les tables principles / principle_evaluations et leurs index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(PRINCIPLE_SCHEMA_SQL)
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()
