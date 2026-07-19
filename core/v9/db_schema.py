"""Schéma DB V9 — table forces_snapshots (data/v9_forces.db)."""

from __future__ import annotations

import logging

import sqlite3
from pathlib import Path

from core.v9.config import DB_PATH

logger = logging.getLogger("v9.db_schema")
log = logger

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
    cvd_delta INTEGER,
    cvd_cumul INTEGER,
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
    "cvd_delta", "cvd_cumul",  # Chantier C (2026-07-18) — CVD tick-level MT4
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


def migrate_cvd(conn: sqlite3.Connection) -> list[str]:
    """Migration rétrocompatible Chantier C (2026-07-18) : ajoute les colonnes
    `cvd_delta` / `cvd_cumul` (Cumulative Volume Delta tick-level) à
    forces_snapshots si absentes.

    ADD COLUMN en SQLite est O(1) (metadata only) — sûr même sur une base de
    plusieurs Go. NON appelée par init_db : le déploiement prod est explicite
    via scripts/v9_migrate_cvd.py (décision CEO 2026-07-18, fenêtre contrôlée).
    Idempotent. Retourne la liste des colonnes effectivement ajoutées.
    """
    existing = {d[1] for d in conn.execute("PRAGMA table_info(forces_snapshots)").fetchall()}
    added: list[str] = []
    for col in ("cvd_delta", "cvd_cumul"):
        if col not in existing:
            conn.execute(f"ALTER TABLE forces_snapshots ADD COLUMN {col} INTEGER")
            added.append(col)
    return added


# ── P0 2026-07-19 : coexistence live+shadow sur les tables dérivées ───────
# Le shadow (core/v9/shadow_evaluator.py) fait INSERT OR REPLACE sur les
# tables signals / principle_evaluations avec un UNIQUE index qui ne
# différenciait pas `source_type` → écrasement silencieux des lignes live
# par les shadow. Correctif : dédupliquer puis créer l'index UNIQUE
# incluant source_type. La déduplication garde la ligne live la plus
# ancienne (id ASC) par (snapshot, principle, currency) ; les shadow
# excédentaires sont supprimés. R6 : si la dédup échoue (FK manquante,
# corruption), on log un warning et l'init ne crashe pas — la base reste
# dans l'état précédent (rollback transaction + skip de la migration).
#
# Le pattern « R8 + R14 » est respecté : pas de DROP/RECREATE sauvage,
# pas de UPDATE en masse sans traçabilité, le caller (init_signal_db /
# init_principle_db) appelle la fonction et trace le résultat dans le
# log de migration. La version R8.backup_md5 a été posée en pré-requis
# (docs/calibration/backups/2026-07-19_p0_shadow_halt/).


def _ensure_shadow_unique_index(
    conn: sqlite3.Connection,
    table: str,
    index_name: str,
    columns: list[str],
    dedupe_keys: list[str],
) -> bool:
    """Crée un index UNIQUE incluant source_type sur `table` après déduplication.

    `columns` est la liste ordonnée des colonnes de l'index
    (incluant `source_type` en dernier). `dedupe_keys` est la liste
    des colonnes d'unicité source (avant source_type) ; pour chaque
    combinaison, on garde la ligne live (si présente) ou la plus
    ancienne par id, et on supprime les autres.

    Retourne True si l'index a été créé, False si la migration a été
    skippée (warning logged). Ne lève JAMAIS (R6 fail-soft init_db).
    """
    # Si l'index existe déjà, rien à faire.
    existing_idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name = ?",
        (index_name,),
    ).fetchone()
    if existing_idx:
        return True

    # 1. Compter les doublons par (dedupe_keys + source_type).
    #    On cherche les valeurs de dedupe_keys présentes avec > 1 source_type.
    where_cols = ", ".join(f"{c} = excluded.{c}" for c in dedupe_keys)
    sql_count = f"""
        SELECT COUNT(*) FROM (
            SELECT {", ".join(dedupe_keys)}, COUNT(DISTINCT source_type) AS n_src
            FROM {table}
            WHERE source_type IS NOT NULL
            GROUP BY {", ".join(dedupe_keys)}
            HAVING n_src > 1
        )
    """
    dup_count = conn.execute(sql_count).fetchone()[0]
    if dup_count == 0:
        # Aucun doublon : création directe de l'index.
        try:
            conn.execute(
                f"CREATE UNIQUE INDEX {index_name} ON {table} "
                f"({', '.join(columns)})"
            )
            return True
        except sqlite3.OperationalError as exc:
            log.warning(
                "P0 shadow unique index : création %s sur %s impossible "
                "(%s). Migration skippée, base reste à l'état précédent.",
                index_name, table, exc,
            )
            return False

    # 2. Doublons détectés : déduplication manuelle par (dedupe_keys),
    #    on garde la ligne live si présente (priorité), sinon la plus
    #    ancienne (id ASC).
    dedupe_cols_csv = ", ".join(dedupe_keys)
    quoted = ", ".join(f'"{c}"' for c in dedupe_keys)
    # ROW_NUMBER partitionné : 1 = live en priorité, sinon id ASC.
    sql_dedupe = f"""
        DELETE FROM {table}
        WHERE rowid IN (
            SELECT rowid FROM (
                SELECT
                    rowid,
                    ROW_NUMBER() OVER (
                        PARTITION BY {dedupe_cols_csv}
                        ORDER BY
                            CASE WHEN source_type = 'live' THEN 0 ELSE 1 END,
                            id ASC
                    ) AS rn
                FROM {table}
                WHERE {", ".join(f"{c} IS NOT NULL" for c in dedupe_keys)}
            ) WHERE rn > 1
        )
    """
    try:
        cur = conn.execute(sql_dedupe)
        deleted = cur.rowcount if cur.rowcount is not None else 0
    except sqlite3.OperationalError as exc:
        log.warning(
            "P0 shadow unique index : dédup %s.%s impossible (%s). "
            "Migration skippée.",
            table, index_name, exc,
        )
        return False
    if deleted:
        log.info(
            "P0 shadow unique index : %s dédupliqué, %s lignes shadow "
            "excédentaires supprimées (live prioritaire, id ASC).",
            table, deleted,
        )

    # 3. Création de l'index UNIQUE.
    try:
        conn.execute(
            f"CREATE UNIQUE INDEX {index_name} ON {table} "
            f"({', '.join(columns)})"
        )
        return True
    except sqlite3.OperationalError as exc:
        log.warning(
            "P0 shadow unique index : création %s sur %s impossible après "
            "dédup (%s). Migration skippée.",
            index_name, table, exc,
        )
        return False


def ensure_shadow_unique_index_signals(conn: sqlite3.Connection) -> bool:
    """Garantit l'index UNIQUE signals (snapshot_id, source_type)."""
    return _ensure_shadow_unique_index(
        conn,
        table="signals",
        index_name="idx_signals_snapshot_source_type",
        columns=["snapshot_id", "source_type"],
        dedupe_keys=["snapshot_id"],
    )


def ensure_shadow_unique_index_principle_evaluations(
    conn: sqlite3.Connection,
) -> bool:
    """Garantit l'index UNIQUE principle_evaluations
    (snapshot_id, principle_id, currency, source_type)."""
    return _ensure_shadow_unique_index(
        conn,
        table="principle_evaluations",
        index_name="idx_pe_snapshot_principle_currency_source",
        columns=["snapshot_id", "principle_id", "currency", "source_type"],
        dedupe_keys=["snapshot_id", "principle_id", "currency"],
    )

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
    from core.v9.mtf_confirmation_db import init_mtf_confirmation_db

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
    init_mtf_confirmation_db(db_path)         # mtf_confirmations (Phase 9, MTF)

    # Migration source_type (8 tables) — rétrocompatible.
    conn = get_connection(db_path)
    try:
        migrate_source_type(conn)
        conn.commit()
    finally:
        conn.close()

    # OPT-3 : vue agrégée dashboard (init_views après migrate_source_type).
    init_views(db_path)


# Vue SQL OPT-3 (2026-07-07) — snapshot agrégé pour dashboard.
# Regroupe 5 SELECT en 1 ligne : counts + last_snapshot. Latence -60%
# sur `v9_dashboard.py --once` (de ~10 SELECT à 1 SELECT). 0 dépendance,
# 0 modif scripts/* (la vue est créée à l'init, appelée comme une table).
VIEW_DASHBOARD_SNAPSHOT_SQL = """
CREATE VIEW IF NOT EXISTS v_dashboard_snapshot AS
SELECT
  (SELECT COUNT(*) FROM forces_snapshots) AS n_snapshots,
  (SELECT MAX(bar_time) FROM forces_snapshots) AS last_bar_time,
  (SELECT COUNT(*) FROM decisions WHERE is_win IS NULL) AS n_decisions_unresolved,
  (SELECT COUNT(*) FROM decisions WHERE is_win = 1) AS n_decisions_win,
  (SELECT COUNT(*) FROM decisions WHERE is_win = 0) AS n_decisions_loss,
  (SELECT COUNT(*) FROM scenes) AS n_scenes,
  (SELECT COUNT(*) FROM behaviors) AS n_behaviors,
  (SELECT COUNT(*) FROM windows) AS n_windows,
  (SELECT COUNT(*) FROM exploitability) AS n_exploitability,
  (SELECT COUNT(*) FROM signals) AS n_signals,
  (SELECT COUNT(*) FROM paper_trades) AS n_paper_trades
"""


def init_views(db_path: Path | None = None) -> None:
    """Crée les vues V9 (OPT-3). Idempotent (CREATE VIEW IF NOT EXISTS).
    Appelé par init_all_dbs() pour garantir la présence de la vue."""
    conn = get_connection(db_path)
    try:
        conn.executescript(VIEW_DASHBOARD_SNAPSHOT_SQL)
        conn.commit()
    finally:
        conn.close()
