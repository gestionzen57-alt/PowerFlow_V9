"""Schéma DB V9 — table `regime_snapshots` (data/v9_forces.db).

Migration du gap V8 identifié dans docs/audit_v8_v9_migration.md §2.2/§6 —
la table de production V8 (`core/powerflow_fresh.db.regime_snapshots`,
327 112 lignes) n'avait aucun équivalent V9. Le schéma ci-dessous reprend
les colonnes de `core/pf_regime_detector.py` (V8), adapté au modèle
événementiel V9 : une ligne référence toujours son snapshot de forces
source (`forces_snapshot_ref`) au lieu d'une clé (symbol, currency, ts)
par minute, et porte `timeframe` (V9 traite plusieurs timeframes, pas
seulement M1 comme V8). `tick_freq_hz` / `spread_mean` / `delta_vol`
restent NULL tant que V9 n'a pas de couche tick (même dégradation
gracieuse que V8 quand `tick_aggregated_5s` ne couvre pas la fenêtre —
voir core/v9/regime_detector.py).
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection, migrate_source_type

REGIME_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS regime_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    forces_snapshot_ref TEXT,
    symbol TEXT,
    timeframe TEXT,
    currency TEXT,
    force_value REAL,
    regime_type TEXT,
    cassure_type TEXT,
    cassure_direction TEXT,
    palier_start_ts TEXT,
    palier_duration_bars INTEGER,
    palier_level REAL,
    tick_freq_hz REAL,
    spread_mean REAL,
    delta_vol INTEGER,
    mean_reversion_zone BOOLEAN,
    stale BOOLEAN,
    source_type TEXT,
    created_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_regime_snapshot_currency
    ON regime_snapshots (forces_snapshot_ref, currency);

CREATE INDEX IF NOT EXISTS idx_regime_symbol_tf_currency_timestamp
    ON regime_snapshots (symbol, timeframe, currency, timestamp);

CREATE INDEX IF NOT EXISTS idx_regime_type
    ON regime_snapshots (regime_type);
"""

# Colonnes hors id (auto-incrémenté), dans l'ordre de création —
# réutilisées par regime_detector.py pour l'INSERT.
REGIME_SNAPSHOTS_COLUMNS = [
    "regime_id", "schema_version", "timestamp", "forces_snapshot_ref",
    "symbol", "timeframe", "currency", "force_value",
    "regime_type", "cassure_type", "cassure_direction",
    "palier_start_ts", "palier_duration_bars", "palier_level",
    "tick_freq_hz", "spread_mean", "delta_vol",
    "mean_reversion_zone", "stale", "source_type", "created_at",
]


def init_regime_db(db_path: Path | None = None) -> None:
    """Crée la table regime_snapshots et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(REGIME_SCHEMA_SQL)
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()
