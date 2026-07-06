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
    risk_assessment_json TEXT,
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
    "risk_assessment_json",
    "stale", "source_type", "created_at",
]


def _ensure_column(conn, table: str, column: str, col_type: str) -> None:
    """Ajoute une colonne à une table existante si elle est absente
    (migration rétrocompatible, pattern identique à db_schema._ensure_column)."""
    existing = {d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def init_scene_db(db_path: Path | None = None) -> None:
    """Crée la table scenes et ses index si absents.

    Migration rétrocompatible : si une table ``scenes`` existait avant
    l'ajout de la colonne ``risk_assessment_json`` (Tâche B), celle-ci
    est ajoutée via ``ALTER TABLE`` sans recréer la table.
    """
    conn = get_connection(db_path)
    try:
        conn.executescript(SCENES_SCHEMA_SQL)
        # Migration ALTER TABLE pour les bases créées avant 2026-07-06
        # (colonne risk_assessment_json absente). Le CREATE TABLE ci-
        # dessus inclut déjà la colonne pour les nouvelles bases.
        existing_tables = {
            d[0] for d in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "scenes" in existing_tables:
            _ensure_column(conn, "scenes", "risk_assessment_json", "TEXT")
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()