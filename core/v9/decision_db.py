"""Schéma DB V9 — table `decisions` (data/v9_forces.db).

Couche Décision (Phase 9) : une décision persiste le contexte complet
(signal + scène + comportement + fenêtre + exploitabilité + principes +
régime) nécessaire au replay intégral d'une décision. Aucune logique
d'exécution d'ordre — `action` est une recommandation qualitative
("observer" / "surveiller" / "preparer_entree" / "aucune_action"),
jamais un ordre.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection, migrate_source_type

DECISION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    snapshot_id TEXT,
    signal_id TEXT,
    action TEXT,
    symbol TEXT,
    timeframe TEXT,
    currency TEXT,
    scene_id TEXT,
    behavior_id TEXT,
    window_id TEXT,
    exploitability_id TEXT,
    regime_type TEXT,
    direction TEXT,
    confiance INTEGER,
    principes_json TEXT,
    contexte_complet_json TEXT,
    source_type TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_decisions_snapshot
    ON decisions (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_decisions_signal
    ON decisions (signal_id);

CREATE INDEX IF NOT EXISTS idx_decisions_symbol_timeframe_timestamp
    ON decisions (symbol, timeframe, timestamp);
"""

# Colonnes hors id (auto-incrémenté), dans l'ordre de création —
# réutilisées par decision_logger.py pour l'INSERT.
DECISIONS_COLUMNS = [
    "decision_id", "schema_version", "timestamp", "snapshot_id", "signal_id",
    "action", "symbol", "timeframe", "currency",
    "scene_id", "behavior_id", "window_id", "exploitability_id",
    "regime_type", "direction", "confiance",
    "principes_json", "contexte_complet_json", "source_type", "created_at",
]


def init_decision_db(db_path: Path | None = None) -> None:
    """Crée la table decisions et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(DECISION_SCHEMA_SQL)
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()
