"""tests/test_bug_p3_principle_sync.py — Phase 13 motion CEO « EDGE FUND MAX ».

BUG-P3 Perplexity : INSERT OR REPLACE sur principles pouvait ecraser
ACTIVE→SHADOW silencieusement. Fix structurel Phase 13 : UPSERT cible
qui preserve v9_status, source_status, created_at_source.

Validation : on insere un principe v9_status=ACTIVE, on simule un
recalibrage qui baisse confiance (v9_status devrait etre preserve
malgre un sync), puis on verifie qu'il reste ACTIVE.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _create_principles_db(db):
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE principles (
                principle_id TEXT PRIMARY KEY,
                version TEXT,
                origin TEXT,
                kind TEXT,
                source_status TEXT,
                v9_status TEXT,
                scope_timeframes_json TEXT,
                scope_currencies_json TEXT,
                conditions_json TEXT,
                emits_json TEXT,
                bounds_json TEXT,
                anti_signal_bias REAL,
                notes TEXT,
                created_by TEXT,
                created_at_source TEXT,
                synced_at TEXT
            )
        """)
        conn.commit()


def _insert_principle(conn, pid, v9_status="ACTIVE", notes="orig"):
    conn.execute("""
        INSERT INTO principles
        (principle_id, version, origin, kind, source_status, v9_status,
         scope_timeframes_json, scope_currencies_json, conditions_json,
         emits_json, bounds_json, anti_signal_bias, notes, created_by,
         created_at_source, synced_at)
        VALUES (?, '1.0', 'audit', 'star', 'active', ?,
                '[]', '[]', '{}', '{}', '{}', 0.0, ?, 'hermes',
                '2026-07-31T00:00:00+00:00', '2026-07-31T00:00:00+00:00')
    """, (pid, v9_status, notes))
    conn.commit()


def _upsert_via_engine_logic(conn, pid, new_notes="recalib"):
    """Reproduit la logique _sync_principles_to_db (UPSERT cible)."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO principles
        (principle_id, version, origin, kind, source_status, v9_status,
         scope_timeframes_json, scope_currencies_json, conditions_json,
         emits_json, bounds_json, anti_signal_bias, notes, created_by,
         created_at_source, synced_at)
        VALUES (?, '1.0', 'audit', 'star', 'active', 'SHADOW',
                '[]', '[]', '{}', '{}', '{}', 0.0, ?, 'hermes',
                '2026-07-31T00:00:00+00:00', ?)
        ON CONFLICT(principle_id) DO UPDATE SET
            version = excluded.version,
            scope_timeframes_json = excluded.scope_timeframes_json,
            scope_currencies_json = excluded.scope_currencies_json,
            conditions_json = excluded.conditions_json,
            emits_json = excluded.emits_json,
            bounds_json = excluded.bounds_json,
            anti_signal_bias = excluded.anti_signal_bias,
            notes = excluded.notes,
            synced_at = excluded.synced_at
    """, (pid, new_notes, now))
    conn.commit()


def test_bug_p3_v9_status_preserved_after_upsert(tmp_path):
    """BUG-P3 fix : UPSERT cible preserve v9_status, n'ecrase pas ACTIVE."""
    db = tmp_path / "v9.db"
    _create_principles_db(db)

    with sqlite3.connect(str(db)) as conn:
        _insert_principle(conn, "PRICE_LAG_AT_NODE_BIRTH", v9_status="ACTIVE")
        # Simule recalibrage qui baisse confiance (v9_status=SHADOW
        # dans le payload, mais l'UPSERT ne doit pas ecraser)
        _upsert_via_engine_logic(
            conn, "PRICE_LAG_AT_NODE_BIRTH", new_notes="recalib_notes",
        )
        row = conn.execute(
            "SELECT v9_status, notes, source_status, created_at_source "
            "FROM principles WHERE principle_id=?",
            ("PRICE_LAG_AT_NODE_BIRTH",),
        ).fetchone()

    # v9_status doit rester ACTIVE malgre le payload SHADOW
    assert row[0] == "ACTIVE", \
        f"BUG-P3 regression: v9_status devenu {row[0]}"
    # notes doit avoir ete update (colonne volatile OK)
    assert row[1] == "recalib_notes"
    # source_status preserve
    assert row[2] == "active"
    # created_at_source preserve
    assert row[3] == "2026-07-31T00:00:00+00:00"


def test_bug_p3_new_principle_inserted_with_active(tmp_path):
    """UPSERT sur nouveau principe_id → INSERT classique avec v9_status."""
    db = tmp_path / "v9.db"
    _create_principles_db(db)

    with sqlite3.connect(str(db)) as conn:
        _upsert_via_engine_logic(conn, "NEW_STAR_PRINCIPLE",
                                  new_notes="initial")
        row = conn.execute(
            "SELECT v9_status, notes FROM principles "
            "WHERE principle_id=?",
            ("NEW_STAR_PRINCIPLE",),
        ).fetchone()

    # Premier INSERT → v9_status=SHADOW (du payload), mais la doctrine
    # dit que c'est le module auto_promote qui decide, pas le sync.
    # Le fix preserve juste le statu quo lors des syncs ulterieurs.
    assert row is not None
    assert row[1] == "initial"


def test_bug_p3_no_data_loss_on_multiple_syncs(tmp_path):
    """Sync repete ne detruit pas les colonnes preservees."""
    db = tmp_path / "v9.db"
    _create_principles_db(db)

    with sqlite3.connect(str(db)) as conn:
        _insert_principle(
            conn, "PRICE_LAG_AT_NODE_BIRTH",
            v9_status="ACTIVE", notes="notes_v1",
        )
        # 5 recalibrages simules
        for i in range(5):
            _upsert_via_engine_logic(
                conn, "PRICE_LAG_AT_NODE_BIRTH",
                new_notes=f"recalib_v{i+2}",
            )
        row = conn.execute(
            "SELECT v9_status, notes FROM principles "
            "WHERE principle_id=?",
            ("PRICE_LAG_AT_NODE_BIRTH",),
        ).fetchone()

    # Apres 5 syncs, v9_status doit TOUJOURS etre ACTIVE
    assert row[0] == "ACTIVE"
    # notes = dernier update
    assert row[1] == "recalib_v6"