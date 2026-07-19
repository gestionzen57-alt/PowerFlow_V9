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
    created_at TEXT,
    -- P1 DYNAMIC (autopilot 2026-07-13) — recommandation de stratégie
    -- de sortie calculée par session_marche au moment du signal.
    -- INEFFET JUSQU'À ACTIVATION OPÉRATEUR (cf DECISIONS_LOG Brief O4).
    exit_strategy_recommended TEXT,
    tp_pips_recommended REAL,
    sl_pips_recommended REAL
);
CREATE INDEX IF NOT EXISTS idx_signals_snapshot
    ON signals (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_timeframe_timestamp
    ON signals (symbol, timeframe, timestamp);
-- P0 2026-07-19 : coexistence live+shadow sur le même snapshot_id.
-- L'ancien index UNIQUE(idx_signals_snapshot_id) couvrait snapshot_id
-- seul, donc le shadow INSERT OR REPLACE écrasait silencieusement la
-- ligne live. Remplacé par idx_signals_snapshot_source_type (créé par
-- init_signal_db après DROP IF EXISTS de l'ancien). R6 idempotent.
CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_snapshot_source_type
    ON signals (snapshot_id, source_type);
"""
SIGNALS_COLUMNS = [
    "signal_id", "schema_version", "timestamp", "snapshot_id",
    "symbol", "timeframe", "currency",
    "direction", "confiance", "horizon",
    "principes_source_json", "regime_type",
    "exploitability_id", "exploitability_statut", "raison_absence",
    "stale", "source_type", "created_at",
    # P1 DYNAMIC (autopilot 2026-07-13) — colonnes
    # exit_strategy_recommended, tp_pips_recommended, sl_pips_recommended
    # ajoutées à la table signals. Rétrocompat : _ensure_column les ajoute
    # aux bases existantes.
    "exit_strategy_recommended", "tp_pips_recommended", "sl_pips_recommended",
]


def init_signal_db(db_path: Path | None = None) -> None:
    """Crée la table signals et ses index si absents, et applique les
    migrations rétrocompatibles (colonnes ajoutées après la création
    initiale)."""
    conn = get_connection(db_path)
    try:
        # P0 2026-07-19 : DROP défensif de l'ancien index UNIQUE
        # idx_signals_snapshot_id AVANT executescript (sinon le schema
        # tente de le re-créer et échoue si la base contient déjà des
        # doublons historiques). Idempotent.
        conn.execute("DROP INDEX IF EXISTS idx_signals_snapshot_id")
        conn.executescript(SIGNAL_SCHEMA_SQL)
        migrate_source_type(conn)
        # Migrations P1 DYNAMIC — ajouter les 3 nouvelles colonnes aux
        # bases créées avant 2026-07-13 (idempotent via _ensure_column).
        from core.v9.db_schema import _ensure_column
        _ensure_column(conn, "signals", "exit_strategy_recommended", "TEXT")
        _ensure_column(conn, "signals", "tp_pips_recommended", "REAL")
        _ensure_column(conn, "signals", "sl_pips_recommended", "REAL")
        # P0 2026-07-19 : re-drop défensif (le SCHEMA_SQL a pu
        # re-créer l'index par IF NOT EXISTS). Puis index enrichi.
        conn.execute("DROP INDEX IF EXISTS idx_signals_snapshot_id")
        from core.v9.db_schema import ensure_shadow_unique_index_signals
        ensure_shadow_unique_index_signals(conn)
        conn.commit()
    finally:
        conn.close()
