"""Schéma DB V9 — table `zone_diagnostics` (data/v9_forces.db).

Migration du gap V8 identifié dans docs/audit_v8_v9_migration.md §2.2/§6 —
`zone_diagnostics` (36 808 lignes en V8, logique de zones extrêmes :
pullback, absorption, tension) n'a aucun équivalent V9. Colonnes reprises
telles quelles depuis les `CREATE TABLE` réels lus en §2.2 de l'audit,
plus `prev_state`/`prev_z_extreme_dir` (dénormalisés pour l'évaluation
directe des principes `node_rule` qui les référencent — ex.
`ZONE_RETEST`, `NODE_BIRTH_FAST` — sans recalcul par principle_engine.py).

GAP NON COMBLÉ CETTE PHASE (Phase 9) : cette table est créée mais
aucun détecteur ne l'alimente encore — porter la logique de détection
zones extrêmes (pullback/absorption/tension) est un chantier Priorité 2
distinct (~5-8 jours, cf. audit §7/§8), volontairement hors scope ici.
Tant qu'elle est vide, les principes `node_rule` qui en dépendent (9 des
27 principes migrés) sont chargés et évalués par principle_engine.py mais
ne se déclenchent jamais (champs de contexte absents -> conditions non
remplies), sans erreur — dégradation gracieuse documentée.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection

ZONE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS zone_diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_diagnostic_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    forces_snapshot_ref TEXT,
    symbol TEXT,
    timeframe TEXT,
    currency TEXT,
    state TEXT,
    prev_state TEXT,
    zone_level REAL,
    z_current REAL,
    z_extreme_dir TEXT,
    prev_z_extreme_dir TEXT,
    bars_in_extreme INTEGER,
    pullback_count INTEGER,
    absorbed_pullback_count INTEGER,
    depth_slope REAL,
    depth_acceleration REAL,
    absorption_factor REAL,
    tension_score REAL,
    context_score REAL,
    profile_name TEXT,
    rank_position INTEGER,
    rank_total INTEGER,
    duration_bars INTEGER,
    context_tags_json TEXT,
    raw_diagnosis_json TEXT,
    stale BOOLEAN,
    created_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_zone_diagnostic_currency
    ON zone_diagnostics (forces_snapshot_ref, currency);

CREATE INDEX IF NOT EXISTS idx_zone_symbol_tf_currency_timestamp
    ON zone_diagnostics (symbol, timeframe, currency, timestamp);
"""

# Colonnes hors id (auto-incrémenté), dans l'ordre de création —
# réservées pour un futur détecteur zone_diagnostics (hors scope Phase 9).
ZONE_DIAGNOSTICS_COLUMNS = [
    "zone_diagnostic_id", "schema_version", "timestamp", "forces_snapshot_ref",
    "symbol", "timeframe", "currency",
    "state", "prev_state", "zone_level", "z_current",
    "z_extreme_dir", "prev_z_extreme_dir", "bars_in_extreme",
    "pullback_count", "absorbed_pullback_count",
    "depth_slope", "depth_acceleration", "absorption_factor",
    "tension_score", "context_score", "profile_name",
    "rank_position", "rank_total", "duration_bars",
    "context_tags_json", "raw_diagnosis_json", "stale", "created_at",
]


def init_zone_db(db_path: Path | None = None) -> None:
    """Crée la table zone_diagnostics et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(ZONE_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
