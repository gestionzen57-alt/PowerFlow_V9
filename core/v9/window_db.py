"""Schéma DB V9 — table windows (couche Fenêtres).

Aligné sur docs/architecture/formats/FORMAT_FENETRES.md. Chaque ligne
correspond à une évaluation de fenêtre produite par WindowGate pour un
comportement donné (behavior_id). Aucune logique de trading ni
d'exécution d'ordre.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.v9.config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    window_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    behavior_id TEXT,
    behavior_qualification TEXT,
    behavior_confiance INTEGER,
    statut TEXT,
    type_fenetre TEXT,
    niveau_confiance INTEGER,
    timestamp_ouverture TEXT,
    timestamp_fermeture TEXT,
    fragilite_detectee BOOLEAN,
    fragilite_raison TEXT,
    conditions_invalidation_json TEXT,
    stale BOOLEAN,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_windows_behavior_id
    ON windows (behavior_id);

CREATE INDEX IF NOT EXISTS idx_windows_statut_timestamp
    ON windows (statut, timestamp);

CREATE INDEX IF NOT EXISTS idx_windows_timestamp_ouverture
    ON windows (timestamp_ouverture);
"""

# Colonnes de windows hors id (auto-incrémenté), dans l'ordre de
# création — réutilisées par window_gate.py pour l'INSERT.
WINDOWS_COLUMNS = [
    "window_id", "schema_version", "timestamp",
    "behavior_id", "behavior_qualification", "behavior_confiance",
    "statut", "type_fenetre", "niveau_confiance",
    "timestamp_ouverture", "timestamp_fermeture",
    "fragilite_detectee", "fragilite_raison",
    "conditions_invalidation_json", "stale",
    "created_at",
]


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Ouvre une connexion sqlite3 avec les pragmas V9 (WAL, busy_timeout 30s)."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init_window_db(db_path: Path | None = None) -> None:
    """Crée la table windows et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
