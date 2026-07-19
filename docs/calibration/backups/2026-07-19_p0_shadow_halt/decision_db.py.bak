"""Schéma DB V9 — table `decisions` (data/v9_forces.db).

Couche Décision (Phase 9) : une décision persiste le contexte complet
(signal + scène + comportement + fenêtre + exploitabilité + principes +
régime) nécessaire au replay intégral d'une décision. Aucune logique
d'exécution d'ordre — `action` est une recommandation qualitative
("observer" / "surveiller" / "preparer_entree" / "aucune_action"),
jamais un ordre.

Résolution manuelle (post-trade) — colonnes nullable ajoutées 2026-07-07
pour la saisie manuelle du résultat réel d'une décision :
  - is_win (INTEGER 0/1/NULL)
  - resolution_pips (REAL/NULL)
  - resolved_at (TEXT ISO UTC/NULL)
Aucune valeur rétroactive : les décisions existantes restent NULL.
Aucun chemin automatique : saisie opérateur uniquement via
`scripts/v9_resolve_decision.py`. Doctrine : aucune logique d'exécution
d'ordre avant Phase 12, ces colonnes sont des champs de collecte.
"""

from __future__ import annotations

from pathlib import Path

from core.v9.db_schema import _ensure_column, get_connection, migrate_source_type

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
    "low_confidence_block",
]

# Colonnes ajoutées en migration 2026-07-07 — résolution manuelle post-trade.
# Toutes nullable, idempotentes (ALTER guardé par _ensure_column).
RESOLUTION_COLUMNS = [
    ("is_win", "INTEGER"),           # 0=loss, 1=win, NULL=non résolu
    ("resolution_pips", "REAL"),     # gain/perte réalisée en pips, NULL=non résolu
    ("resolved_at", "TEXT"),         # timestamp ISO UTC de la saisie, NULL=non résolu
]

# Colonne ajoutée Brief O3 (2026-07-12) — branching HITL confiance 40-65.
# conf < 40 -> marquage explicite (pas de dérogation RiskManager, purement
# informatif/traçabilité). Défaut 0 (pas bloquée par ce marquage).
HITL_COLUMNS = [
    ("low_confidence_block", "INTEGER"),  # 0=normal, 1=confiance<40, NULL=legacy
]

# Colonnes ajoutées Phase 13.2 (2026-07-11, ExitSimulator) directement sur
# la DB prod via ALTER TABLE ad-hoc — JAMAIS enregistrées dans ce module de
# migration jusqu'à leur découverte pendant le Brief O5 (2026-07-12) : une
# DB fraîche initialisée via init_decision_db() n'avait pas ces colonnes,
# cassant scripts/v9_batch_resolve_dynamic_full.py, v9_regenerate_
# principle_scores.py et v9_export_dataset.py hors de la DB prod existante.
# Fix rétroactif — idempotent, no-op sur la DB prod (colonnes déjà présentes).
EXIT_SIMULATOR_COLUMNS = [
    ("resolution_strategy", "TEXT"),  # TP_SL/TRAILING/TIME_BASED/MFE_ONLY/DYNAMIC/SKIPPED
    ("resolution_details", "TEXT"),   # JSON ExitResult (exit_reason, MFE/MAE, bars_held...)
]


def _migrate_resolution_columns(conn) -> None:
    """Migration idempotente — ajoute les colonnes de résolution si absentes.

    Aucune valeur rétroactive : les décisions existantes restent NULL.
    Pas de try/except nu autour des ALTER : on utilise _ensure_column qui
    interroge PRAGMA table_info et n'exécute l'ALTER que si la colonne
    n'existe pas — donc safe à rejouer sans erreur.
    """
    for col_name, col_type in RESOLUTION_COLUMNS:
        _ensure_column(conn, "decisions", col_name, col_type)
    for col_name, col_type in EXIT_SIMULATOR_COLUMNS:
        _ensure_column(conn, "decisions", col_name, col_type)


def _migrate_hitl_columns(conn) -> None:
    """Migration idempotente — colonnes branching HITL (Brief O3)."""
    for col_name, col_type in HITL_COLUMNS:
        _ensure_column(conn, "decisions", col_name, col_type)


def init_decision_db(db_path: Path | None = None) -> None:
    """Crée la table decisions et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(DECISION_SCHEMA_SQL)
        migrate_source_type(conn)
        _migrate_resolution_columns(conn)
        _migrate_hitl_columns(conn)
        conn.commit()
    finally:
        conn.close()
