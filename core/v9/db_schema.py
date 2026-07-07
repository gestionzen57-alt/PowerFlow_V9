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

-- Anti-doublon replay : une bougie clôturée (symbol+timeframe+bar_time)
-- ne doit exister qu'une fois, même si l'EA la renvoie avec un
-- snapshot_id différent (horodatage de capture réel) à chaque replay.
-- Ne s'applique pas aux bougies en cours (is_closed_bar = 0), qui
-- reçoivent légitimement plusieurs snapshots avant clôture.
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_closed_bar
    ON forces_snapshots (symbol, timeframe, bar_time)
    WHERE is_closed_bar = 1;
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


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    """Ajoute une colonne à une table existante si elle est absente (migration rétrocompatible)."""
    existing = {d[1] for d in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


MIGRATIONS_SOURCE_TYPE = [
    "scenes", "behaviors", "windows", "exploitability",
    "regime_snapshots", "principle_evaluations", "signals", "decisions",
]


def migrate_source_type(conn: sqlite3.Connection) -> None:
    """Migration rétrocompatible : ajoute source_type TEXT aux 8 tables
    dérivées si la colonne est absente (bases créées avant 2026-07-06).
    Utilise la connexion existante pour voir les tables créées dans la
    même transaction. Ignore les tables qui n'existent pas encore."""
    existing_tables = {
        d[0] for d in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table in MIGRATIONS_SOURCE_TYPE:
        if table in existing_tables:
            _ensure_column(conn, table, "source_type", "TEXT")


# ── Index canonique des tables V9 ───────────────────────────
# PowerFlow V9 = 9 tables SQLite sur data/v9_forces.db :
#   1. forces_snapshots       (couche 1, MT4)         — core/v9/db_schema.py
#   2. scenes                 (couche 2, SceneBuilder) — core/v9/scene_db.py
#   3. behaviors              (couche 3, BehaviorAn.)  — core/v9/behavior_db.py
#   4. windows                (couche 4, WindowGate)   — core/v9/window_db.py
#   5. exploitability         (couche 5, ExploitEval.) — core/v9/exploitability_db.py
#   6. regime_snapshots       (couche 6, Régime)       — core/v9/regime_db.py
#   7. principles + principle_evaluations (couche 7)   — core/v9/principle_db.py
#   8. signals                (couche 8, SignalGen.)   — core/v9/signal_db.py
#   9. decisions              (couche 9, DecisionLog.) — core/v9/decision_db.py
#  +10. paper_trades          (Phase 9.7)              — core/v9/paper_trades_db.py
#  +11. zone_diagnostics      (Phase 9, ZoneDetector)  — core/v9/zone_db.py
#
# Chaque module *_db.py expose un init_*_db(db_path) idempotent, conforme
# au pattern _ensure_column() pour les migrations rétrocompatibles (règle
# 14 doctrine). 8 des 9 tables principales portent la colonne source_type
# (cf. MIGRATIONS_SOURCE_TYPE) — règle 12.
#
# init_all_dbs() ci-dessous appelle les init_*_db() dans l'ordre des
# couches amont → aval pour respecter la dépendance inter-couches
# (règle 1 doctrine, primauté de la lecture).


def init_db(db_path: Path | None = None) -> None:
    """Crée la table forces_snapshots et ses index si absents."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def init_all_dbs(db_path: Path | None = None) -> None:
    """Initialise les 11 tables V9 dans l'ordre des couches (amont → aval).
    Idempotent : peut être appelé plusieurs fois sans effet. Utilisé par
    `scripts/v9_bootstrap.py` (déploiement VPS) et `tests/conftest.py`
    (fixtures pytest). Conforme à la règle 14 (Git = source de vérité
    pour le schéma DB)."""
    # Imports locaux pour éviter cycle (config importé en haut).
    from core.v9.scene_db import init_scene_db
    from core.v9.behavior_db import init_behavior_db
    from core.v9.window_db import init_window_db
    from core.v9.exploitability_db import init_exploitability_db
    from core.v9.regime_db import init_regime_db
    from core.v9.principle_db import init_principle_db
    from core.v9.signal_db import init_signal_db
    from core.v9.decision_db import init_decision_db
    from core.v9.paper_trades_db import init_paper_trades_db
    from core.v9.zone_db import init_zone_db

    # Ordre amont → aval : Forces (1) → ... → Décisions (9) → paper_trades (9.7) → zones
    init_db(db_path)                          # 1. forces_snapshots
    init_scene_db(db_path)                    # 2. scenes
    init_behavior_db(db_path)                 # 3. behaviors
    init_window_db(db_path)                   # 4. windows
    init_exploitability_db(db_path)           # 5. exploitability
    init_regime_db(db_path)                   # 6. regime_snapshots
    init_principle_db(db_path)                # 7. principles + principle_evaluations
    init_signal_db(db_path)                   # 8. signals
    init_decision_db(db_path)                 # 9. decisions
    init_paper_trades_db(db_path)             # 9.7. paper_trades (Phase 9.7)
    init_zone_db(db_path)                     # zone_diagnostics (Phase 9)

    # Migration source_type (8 tables) — rétrocompatible.
    conn = get_connection(db_path)
    try:
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()
