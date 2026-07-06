"""Schéma DB V9 — table scenes (data/v9_forces.db).

Couche Scènes : une scène référence son snapshot de forces source
(`forces_snapshot_ref`) et ne duplique jamais les données brutes de
forces. Voir docs/architecture/formats/FORMAT_SCENES.md.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection, migrate_source_type

SCENES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scene_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    timeframes_concernes TEXT,
    forces_snapshot_ref TEXT,
    forces_snapshot_timestamp TEXT,
    zone_json TEXT,
    coalitions_json TEXT,
    antagonismes_json TEXT,
    cinematique_json TEXT,
    confluences_mtf_json TEXT,
    contexte_temporel_json TEXT,
    stale BOOLEAN,
    source_type TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_scenes_timestamp
    ON scenes (timestamp);

CREATE INDEX IF NOT EXISTS idx_scenes_forces_snapshot_ref
    ON scenes (forces_snapshot_ref);
"""

# Colonnes de la table scenes hors id (auto-incrémenté), dans l'ordre
# de création — réutilisées par scene_builder.py pour l'INSERT.
SCENES_COLUMNS = [
    "scene_id", "schema_version", "timestamp", "timeframes_concernes",
    "forces_snapshot_ref", "forces_snapshot_timestamp",
    "zone_json", "coalitions_json", "antagonismes_json",
    "cinematique_json", "confluences_mtf_json", "contexte_temporel_json",
    "stale", "source_type", "created_at",
]


def init_scene_db(db_path: Path | None = None) -> None:
    """Crée la table scenes et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCENES_SCHEMA_SQL)
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()
