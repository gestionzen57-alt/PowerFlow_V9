"""Schéma DB V9 — table forces_snapshots (data/v9_forces.db)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.v9.config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS forces_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    source TEXT,
    symbol TEXT,
    timeframe TEXT,
    bar_time INTEGER,
    bar_close_time INTEGER,
    server_time INTEGER,
    capture_time INTEGER,
    shift INTEGER,
    is_closed_bar BOOLEAN,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    tick_volume INTEGER,
    spread_points INTEGER,
    spread_price REAL,
    bid REAL,
    ask REAL,
    mid REAL,
    force_usd REAL,
    force_gbp REAL,
    force_eur REAL,
    force_jpy REAL,
    force_cad REAL,
    force_chf REAL,
    force_aud REAL,
    force_nzd REAL,
    direction TEXT,
    vitesse REAL,
    croisement_detecte BOOLEAN,
    croisement_partenaire TEXT,
    croisement_direction TEXT,
    recroisement_detecte BOOLEAN,
    recroisement_contexte TEXT,
    rejet_repulsion_detecte BOOLEAN,
    rejet_intensite REAL,
    compression_extension_etat TEXT,
    compression_extension_intensite REAL,
    stale BOOLEAN,
    age_ms INTEGER,
    stale_threshold_ms INTEGER,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_forces_timeframe_bartime
    ON forces_snapshots (timeframe, bar_time);
"""

# Colonnes de forces_snapshots hors id (auto-incrémenté), dans l'ordre
# de création — réutilisées par capture_server.py pour l'INSERT.
FORCES_COLUMNS = [
    "snapshot_id", "schema_version", "timestamp", "source", "symbol", "timeframe",
    "bar_time", "bar_close_time", "server_time", "capture_time", "shift", "is_closed_bar",
    "open", "high", "low", "close", "tick_volume", "spread_points", "spread_price",
    "bid", "ask", "mid",
    "force_usd", "force_gbp", "force_eur", "force_jpy",
    "force_cad", "force_chf", "force_aud", "force_nzd",
    "direction", "vitesse",
    "croisement_detecte", "croisement_partenaire", "croisement_direction",
    "recroisement_detecte", "recroisement_contexte",
    "rejet_repulsion_detecte", "rejet_intensite",
    "compression_extension_etat", "compression_extension_intensite",
    "stale", "age_ms", "stale_threshold_ms",
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


def init_db(db_path: Path | None = None) -> None:
    """Crée la table forces_snapshots et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
