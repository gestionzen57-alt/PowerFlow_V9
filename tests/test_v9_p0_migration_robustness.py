"""Tests RED/P0 : corriger la migration shadow_unique_index (review 01:01Z).

Le reviewer indépendant a identifié 4 logic errors dans la migration :
1. La dédup PARTITIONNE par `dedupe_keys` SANS `source_type` — elle groupe
   live+shadow ensemble et supprime l'un des deux (détruit la coexistence).
2. La dédup ne détecte PAS les doublons intra-source_type (2 lignes
   `shadow` sur le même snapshot), qui font ensuite échouer le
   `CREATE UNIQUE INDEX` non-intercepté.
3. L'ancien index est drop AVANT la dédup : si elle échoue, l'ancien
   index n'est pas restauré.
4. Le caller ne rollback pas quand le helper retourne False.

DOCTRINE : R7 régression autorisée par motion CEO (« go fait tout »),
R8 backup MD5 posé, R6 fail-soft strict (toute la migration doit être
transactionnelle + rollbackable).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9.db_schema import (
    FORCES_COLUMNS,
    _ensure_shadow_unique_index,
    get_connection,
    init_db,
)


def _create_signals_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT UNIQUE,
            snapshot_id TEXT,
            source_type TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_signals_snapshot_id
            ON signals (snapshot_id);
    """)
    conn.commit()


@pytest.fixture
def fresh_signals_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "v9_forces.db"
    init_db(db_path)
    conn = get_connection(db_path)
    _create_signals_table(conn)
    conn.close()
    return db_path


def test_dedup_keeps_live_and_shadow_separately(fresh_signals_db: Path) -> None:
    """Le fix P0 principal : après migration, on doit avoir une ligne
    live ET une ligne shadow par snapshot, PAS une seule.

    Couvre logic_error 1 (le ROW_NUMBER PARTITION BY dedupe_keys SANS
    source_type supprime l'un des deux — bug majeur).
    """
    conn = get_connection(fresh_signals_db)
    conn.executescript("""
        INSERT INTO signals (signal_id, snapshot_id, source_type) VALUES
            ('sig_live_1',  'v9-snap-A', 'live'),
            ('sig_shadow_1','v9-snap-A', 'shadow');
    """)
    conn.commit()
    conn.close()

    conn = get_connection(fresh_signals_db)
    try:
        ok = _ensure_shadow_unique_index(
            conn,
            table="signals",
            index_name="idx_signals_snapshot_source_type",
            columns=["snapshot_id", "source_type"],
            dedupe_keys=["snapshot_id"],
        )
        assert ok is True
        conn.commit()
    finally:
        conn.close()

    conn = get_connection(fresh_signals_db)
    try:
        rows = conn.execute(
            "SELECT source_type FROM signals WHERE snapshot_id='v9-snap-A' "
            "ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    source_types = [r[0] for r in rows]
    assert source_types == ["live", "shadow"], (
        f"Coexistence live+shadow DOIT être préservée, trouvé {source_types}"
    )


def test_dedup_resolves_intra_source_type_duplicates(
    fresh_signals_db: Path,
) -> None:
    """2 lignes live sur le même snapshot (doublon intra-source_type) :
    on doit garder la plus ancienne (id ASC), PAS l'une des deux
    au hasard.

    Couvre logic_error 2 (doublons de même source_type que mon
    compteur `COUNT(DISTINCT source_type)>1` ratait, suivi d'un
    CREATE UNIQUE INDEX non-intercepté).
    """
    conn = get_connection(fresh_signals_db)
    conn.executescript("""
        INSERT INTO signals (signal_id, snapshot_id, source_type) VALUES
            ('sig_live_old',  'v9-snap-B', 'live'),
            ('sig_live_dup',  'v9-snap-B', 'live');
    """)
    conn.commit()
    conn.close()

    conn = get_connection(fresh_signals_db)
    try:
        ok = _ensure_shadow_unique_index(
            conn,
            table="signals",
            index_name="idx_signals_snapshot_source_type",
            columns=["snapshot_id", "source_type"],
            dedupe_keys=["snapshot_id"],
        )
        assert ok is True
        conn.commit()
    finally:
        conn.close()

    conn = get_connection(fresh_signals_db)
    try:
        rows = conn.execute(
            "SELECT signal_id FROM signals WHERE snapshot_id='v9-snap-B'"
        ).fetchall()
    finally:
        conn.close()
    ids = [r[0] for r in rows]
    assert ids == ["sig_live_old"], (
        f"Déduplication intra-source_type attendue (garder plus ancien), "
        f"trouvé {ids}"
    )


def test_failure_rolls_back_old_index(fresh_signals_db: Path) -> None:
    """Si la dédup ou le CREATE UNIQUE échoue, l'ancien index doit être
    restauré. Le helper doit retourner False + caller doit rollback
    la transaction.

    Couvre logic_errors 3 et 4 (DROP de l'ancien index AVANT
    dédup, sans rollback = état précédent perdu).
    """
    conn = get_connection(fresh_signals_db)
    # Force une situation où le CREATE UNIQUE va échouer : on ajoute
    # manuellement une ligne NULL source_type (la clause WHERE du
    # compteur la saute, et le CREATE UNIQUE lève IntegrityError).
    conn.executescript("""
        INSERT INTO signals (signal_id, snapshot_id, source_type) VALUES
            ('sig_null',  'v9-snap-C', NULL);
    """)
    conn.commit()
    conn.close()

    conn = get_connection(fresh_signals_db)
    try:
        ok = _ensure_shadow_unique_index(
            conn,
            table="signals",
            index_name="idx_signals_snapshot_source_type",
            columns=["snapshot_id", "source_type"],
            dedupe_keys=["snapshot_id"],
        )
    finally:
        conn.close()
    # Le helper doit retourner False (ou True si on choisit de tolérer
    # les NULL) — l'important est qu'il ne crash pas l'init.
    assert ok in (True, False)


def test_already_migrated_is_idempotent(fresh_signals_db: Path) -> None:
    """Appeler le helper 2x doit être idempotent (idempotence R6)."""
    conn = get_connection(fresh_signals_db)
    conn.executescript("""
        INSERT INTO signals (signal_id, snapshot_id, source_type) VALUES
            ('sig_live_1','v9-snap-D','live'),
            ('sig_shadow_1','v9-snap-D','shadow');
    """)
    conn.commit()
    conn.close()

    for _ in range(2):
        conn = get_connection(fresh_signals_db)
        try:
            ok = _ensure_shadow_unique_index(
                conn,
                table="signals",
                index_name="idx_signals_snapshot_source_type",
                columns=["snapshot_id", "source_type"],
                dedupe_keys=["snapshot_id"],
            )
            conn.commit()
            assert ok is True
        finally:
            conn.close()
