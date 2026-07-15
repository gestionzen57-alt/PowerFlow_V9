"""Schéma DB V9 — table `mtf_confirmations` (data/v9_forces.db).

Stratégie CEO Søn (audit régime GBPUSD, 2026-07-15) : lecture anticipée
multi-timeframe — un timeframe supérieur (H4 pour M15/M30, H1 pour M5/H1)
établit la thèse directionnelle (sortie de zone / cassure), un timeframe
inférieur la confirme par croisement ou déséquilibre de forces. Sans
thèse H4 = pas de contexte = pas de setup ; sans confirmation TF courant
= pas d'entrée. Une ligne par snapshot évalué (même convention "un
événement, une ligne" que les autres couches V9) — voir
`core/v9/mtf_confirmation_engine.py`.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import get_connection

MTF_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mtf_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mtf_id TEXT UNIQUE,
    schema_version TEXT,
    timestamp TEXT,
    forces_snapshot_ref TEXT,
    symbol TEXT,
    trigger_tf TEXT,
    context_tf TEXT,
    context_snapshot_ref TEXT,
    mtf_setup TEXT,
    context_thesis TEXT,
    trigger_confirmation TEXT,
    aligned BOOLEAN,
    conflict BOOLEAN,
    confidence_boost INTEGER,
    direction TEXT,
    reason TEXT,
    source_type TEXT,
    created_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mtf_forces_snapshot
    ON mtf_confirmations (forces_snapshot_ref);

CREATE INDEX IF NOT EXISTS idx_mtf_symbol_tf_timestamp
    ON mtf_confirmations (symbol, trigger_tf, timestamp);
"""

# Colonnes hors id (auto-incrémenté), dans l'ordre de création —
# réutilisées par mtf_confirmation_engine.py pour l'INSERT.
MTF_CONFIRMATIONS_COLUMNS = [
    "mtf_id", "schema_version", "timestamp", "forces_snapshot_ref",
    "symbol", "trigger_tf", "context_tf", "context_snapshot_ref",
    "mtf_setup", "context_thesis", "trigger_confirmation",
    "aligned", "conflict", "confidence_boost", "direction", "reason",
    "source_type", "created_at",
]


def init_mtf_confirmation_db(db_path: Path | None = None) -> None:
    """Crée la table mtf_confirmations et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(MTF_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
