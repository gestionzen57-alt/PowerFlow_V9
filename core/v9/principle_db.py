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

-- Idempotence du rejeu par-devise (fix vote-devise NZD, 2026-07-17).
-- _write_evaluations_to_db() fait INSERT OR REPLACE : la clé d'unicite
-- DOIT inclure `currency`, sinon les 8 evaluations par-devise d'un meme
-- principe collapsent en une seule (la derniere du loop DEVISES = NZD),
-- P0 2026-07-19 : coexistence live+shadow sur le même snapshot_id.
-- L'ancien index UNIQUE(idx_pe_snapshot_principle_currency) couvrait
-- (snapshot_id, principle_id, currency) SANS source_type, donc le shadow
-- INSERT OR REPLACE écrasait silencieusement les evaluations live du
-- même snapshot. Remplacé par idx_pe_snapshot_principle_currency_source
-- créé par init_principle_db() après DROP de l'ancien. R6 idempotent.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pe_snapshot_principle_currency_source
    ON principle_evaluations (snapshot_id, principle_id, currency, source_type);
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
        # P0 2026-07-19 : on DROP d'abord l'ancien index UNIQUE
        # (snapshot_id, principle_id, currency) qui empêche la coexistence
        # live+shadow. Idempotent (IF EXISTS). Doit être fait AVANT
        # executescript() car la SCHEMA_SQL tente de re-créer cet
        # index et échoue si des doublons existent déjà (ligne live
        # insérée par la chaîne avant le shadow).
        conn.execute("DROP INDEX IF EXISTS idx_pe_snapshot_principle_currency")
        conn.executescript(PRINCIPLE_SCHEMA_SQL)
        migrate_source_type(conn)
        # P0 2026-07-19 : re-drop défensif (le SCHEMA_SQL a pu
        # re-créer l'index par IF NOT EXISTS). Puis index enrichi.
        conn.execute("DROP INDEX IF EXISTS idx_pe_snapshot_principle_currency")
        from core.v9.db_schema import ensure_shadow_unique_index_principle_evaluations
        ensure_shadow_unique_index_principle_evaluations(conn)
        conn.commit()
    finally:
        conn.close()
