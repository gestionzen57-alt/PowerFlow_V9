"""Schéma DB V9 — table behaviors (data/v9_forces.db).

Couche Comportements : un comportement référence toujours sa scène
source (`scene_id_ref`) — il ne duplique jamais la scène, il la
qualifie dans le temps. Voir docs/architecture/formats/FORMAT_COMPORTEMENTS.md.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection, migrate_source_type

BEHAVIORS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS behaviors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    behavior_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    scene_id_ref TEXT,
    scene_timestamp TEXT,
    symbol TEXT,
    timeframe TEXT,
    window_start TEXT,
    window_end TEXT,
    qualification TEXT,
    intensite TEXT,
    phase TEXT,
    confiance_qualification INTEGER,
    description_courte TEXT,
    comportement_precedent TEXT,
    point_de_rupture_detecte BOOLEAN,
    point_de_rupture_timestamp TEXT,
    point_de_rupture_declencheur TEXT,
    sens_transition TEXT,
    similarite_score REAL,
    cas_references_json TEXT,
    singularites_locales_json TEXT,
    est_variante BOOLEAN,
    comportement_reference TEXT,
    ecarts_json TEXT,
    stale BOOLEAN,
    source_type TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_behaviors_scene_id_ref
    ON behaviors (scene_id_ref);

CREATE INDEX IF NOT EXISTS idx_behaviors_symbol_timeframe_timestamp
    ON behaviors (symbol, timeframe, timestamp);

CREATE INDEX IF NOT EXISTS idx_behaviors_qualification_intensite
    ON behaviors (qualification, intensite);
"""

# Colonnes de la table behaviors hors id (auto-incrémenté), dans l'ordre
# de création — réutilisées par behavior_analyzer.py pour l'INSERT.
BEHAVIOR_COLUMNS = [
    "behavior_id", "schema_version", "timestamp",
    "scene_id_ref", "scene_timestamp",
    "symbol", "timeframe", "window_start", "window_end",
    "qualification", "intensite", "phase", "confiance_qualification", "description_courte",
    "comportement_precedent",
    "point_de_rupture_detecte", "point_de_rupture_timestamp", "point_de_rupture_declencheur",
    "sens_transition",
    "similarite_score", "cas_references_json", "singularites_locales_json",
    "est_variante", "comportement_reference", "ecarts_json",
    "stale", "source_type", "created_at",
]


def init_behavior_db(db_path: Path | None = None) -> None:
    """Crée la table behaviors et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(BEHAVIORS_SCHEMA_SQL)
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()
