"""Schéma DB V9 — table `signals` (data/v9_forces.db).

Couche Décision (Phase 9) : un signal agrège les évaluations de principes
déclenchées pour un snapshot donné (`snapshot_id`) — il ne recalcule
jamais la direction/force lui-même, il qualifie ce que les principes ont
déjà observé (charte cognitive V9).
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection, migrate_source_type

SIGNAL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    snapshot_id TEXT,
    symbol TEXT,
    timeframe TEXT,
    currency TEXT,
    direction TEXT,
    confiance INTEGER,
    horizon TEXT,
    principes_source_json TEXT,
    regime_type TEXT,
    exploitability_id TEXT,
    exploitability_statut TEXT,
    raison_absence TEXT,
    stale BOOLEAN,
    source_type TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_snapshot
    ON signals (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_timeframe_timestamp
    ON signals (symbol, timeframe, timestamp);
"""

# Colonnes hors id (auto-incrémenté), dans l'ordre de création —
# réutilisées par signal_generator.py pour l'INSERT.
SIGNALS_COLUMNS = [
    "signal_id", "schema_version", "timestamp", "snapshot_id",
    "symbol", "timeframe", "currency",
    "direction", "confiance", "horizon",
    "principes_source_json", "regime_type",
    "exploitability_id", "exploitability_statut", "raison_absence",
    "stale", "source_type", "created_at",
]


def init_signal_db(db_path: Path | None = None) -> None:
    """Crée la table signals et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SIGNAL_SCHEMA_SQL)
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()
