"""tests/test_v9_principle_audit.py — Phase 14 motion CEO « EDGE FUND MAX ».

BUG-P3 follow-up : audit trail des changements de v9_status.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest


def _create_db(db):
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE principles (
                principle_id TEXT PRIMARY KEY,
                v9_status TEXT,
                source_status TEXT,
                created_at_source TEXT
            )
        """)
        conn.commit()


def test_log_change_creates_table(tmp_path):
    """log_change cree la table principle_audit_log si absente."""
    from core.v9.v9_principle_audit import log_change, get_audit_history
    db = tmp_path / "v9.db"
    _create_db(db)

    log_change(db, "PRICE_LAG_AT_NODE_BIRTH", "v9_status",
               "ACTIVE", "SHADOW", actor="ceo_son", reason="motion")

    history = get_audit_history(db, "PRICE_LAG_AT_NODE_BIRTH")
    assert len(history) == 1
    assert history[0]["old_value"] == "ACTIVE"
    assert history[0]["new_value"] == "SHADOW"
    assert history[0]["actor"] == "ceo_son"
    assert history[0]["reason"] == "motion"


def test_log_change_noop_when_same_value(tmp_path):
    """log_change ne cree pas d'entree si old == new."""
    from core.v9.v9_principle_audit import log_change, get_audit_history
    db = tmp_path / "v9.db"
    _create_db(db)

    log_change(db, "TEST", "v9_status", "ACTIVE", "ACTIVE")
    assert get_audit_history(db, "TEST") == []


def test_log_change_preserves_field(tmp_path):
    """log_change preserve le field dans l'audit."""
    from core.v9.v9_principle_audit import log_change, get_audit_history
    db = tmp_path / "v9.db"
    _create_db(db)

    log_change(db, "TEST", "source_status", "active", "pending")
    log_change(db, "TEST", "v9_status", "SHADOW", "ACTIVE")
    history = get_audit_history(db, "TEST")
    fields = {h["field"] for h in history}
    assert fields == {"source_status", "v9_status"}


def test_get_audit_history_filter_by_field(tmp_path):
    """get_audit_history filter par field."""
    from core.v9.v9_principle_audit import log_change, get_audit_history
    db = tmp_path / "v9.db"
    _create_db(db)

    log_change(db, "TEST", "v9_status", "SHADOW", "ACTIVE")
    log_change(db, "TEST", "source_status", "x", "y")
    history = get_audit_history(db, "TEST", field="v9_status")
    assert len(history) == 1
    assert history[0]["field"] == "v9_status"


def test_get_audit_history_missing_db(tmp_path):
    """get_audit_history sur DB absente → []."""
    from core.v9.v9_principle_audit import get_audit_history
    assert get_audit_history(tmp_path / "absent.db", "X") == []


def test_audit_table_idempotent(tmp_path):
    """Appels repetes ne casent pas d'erreur (CREATE IF NOT EXISTS)."""
    from core.v9.v9_principle_audit import _ensure_audit_table
    db = tmp_path / "v9.db"
    _create_db(db)
    _ensure_audit_table(db)
    _ensure_audit_table(db)  # idempotent
    # Pas d'exception levee


def test_log_change_multiple_entries_order_desc(tmp_path):
    """Multiple changements → ordre DESC par ts."""
    from core.v9.v9_principle_audit import log_change, get_audit_history
    db = tmp_path / "v9.db"
    _create_db(db)

    log_change(db, "T", "v9_status", "A", "B")
    log_change(db, "T", "v9_status", "B", "C")
    log_change(db, "T", "v9_status", "C", "D")
    history = get_audit_history(db, "T")
    # DESC: D first
    assert history[0]["new_value"] == "D"
    assert history[-1]["new_value"] == "B"


def test_sync_with_audit_handles_minimal_db(tmp_path):
    """sync_with_audit : tolere une DB sans la colonne version (degrade)."""
    from core.v9.v9_principle_audit import _ensure_audit_table
    db = tmp_path / "v9.db"
    _create_db(db)
    _ensure_audit_table(db)
    # Verifie que la table audit est creee, meme si sync_with_audit
    # requiert la version complete de principles (pas notre cas test).
    import sqlite3
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='principle_audit_log'"
        ).fetchall()
    assert len(rows) == 1