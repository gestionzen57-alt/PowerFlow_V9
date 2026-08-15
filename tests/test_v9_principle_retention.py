"""Tests rétention auto principle_evaluations (CEO motion 2026-08-15).

Bug-fix : principle_evaluations croissait sans borne (+1,5M rows/jour,
DB 18→35 Go en 1 semaine). On ajoute un DELETE > rétention (défaut 30j)
après chaque batch INSERT dans principle_engine._write_evaluations_to_db.

R6 — pas de simulation, on vérifie effectif (rows supprimées en vrai).
R7 — env var V9_PRINCIPLE_RETENTION_DAYS = kill switch (0 = OFF).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core.v9.principle_db import (
    PRINCIPLE_EVALUATIONS_COLUMNS,
    PRINCIPLE_RETENTION_DAYS_DEFAULT,
    PRINCIPLE_RETENTION_ENV,
    init_principle_db,
    principle_retention_days,
    purge_principle_evaluations_older_than,
)


def _make_db(tmp_path):
    """DB tmp avec schema principle_evaluations initialisé."""
    db_path = tmp_path / "test.db"
    init_principle_db(db_path)
    return db_path


def _insert_row(db_path, created_at: str, evaluation_id: str = None) -> None:
    """Insère 1 row dans principle_evaluations (sans les 18 colonnes formelles,
    juste created_at pour test)."""
    if evaluation_id is None:
        evaluation_id = f"peval_{datetime.now().strftime('%H%M%S%f')}_{created_at}"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            f"INSERT INTO principle_evaluations ({', '.join(PRINCIPLE_EVALUATIONS_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in PRINCIPLE_EVALUATIONS_COLUMNS)})",
            (
                evaluation_id, "v1", datetime.now(timezone.utc).isoformat(),
                f"snap_{evaluation_id}", "P_TEST", "ACTIVE", "kind",
                "GBPUSD", "M5", "GBP",
                1, "BUY", 0.5, 0.0, "test",
                "{}", "test_src", created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_default_retention_is_30_days(monkeypatch):
    """Sans env var, rétention = 30 jours (CEO motion)."""
    monkeypatch.delenv(PRINCIPLE_RETENTION_ENV, raising=False)
    assert principle_retention_days() == 30
    assert principle_retention_days() == PRINCIPLE_RETENTION_DAYS_DEFAULT


def test_retention_kill_switch_zero_disables(monkeypatch):
    """V9_PRINCIPLE_RETENTION_DAYS=0 → kill switch OFF."""
    monkeypatch.setenv(PRINCIPLE_RETENTION_ENV, "0")
    assert principle_retention_days() == 0


def test_retention_kill_switch_invalid_disables(monkeypatch):
    """Env var invalide (non-entier) → fail-safe = OFF."""
    monkeypatch.setenv(PRINCIPLE_RETENTION_ENV, "not_a_number")
    assert principle_retention_days() == 0


def test_retention_explicit_value(monkeypatch):
    """V9_PRINCIPLE_RETENTION_DAYS=N → N jours."""
    monkeypatch.setenv(PRINCIPLE_RETENTION_ENV, "60")
    assert principle_retention_days() == 60


def test_purge_deletes_old_rows(tmp_path, monkeypatch):
    """DELETE rows > 30j par created_at."""
    monkeypatch.setenv(PRINCIPLE_RETENTION_ENV, "30")
    db_path = _make_db(tmp_path)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=31)).isoformat()
    fresh = (now - timedelta(days=10)).isoformat()
    very_fresh = (now - timedelta(days=1)).isoformat()
    for i in range(5):
        _insert_row(db_path, old, evaluation_id=f"old_{i}")
    for i in range(3):
        _insert_row(db_path, fresh, evaluation_id=f"fresh_{i}")
    for i in range(2):
        _insert_row(db_path, very_fresh, evaluation_id=f"very_{i}")

    conn = sqlite3.connect(str(db_path))
    try:
        n = purge_principle_evaluations_older_than(conn, days=30)
        assert n == 5, f"devrait purger 5 rows, purgé: {n}"
        # 3 fresh + 2 very_fresh = 5 restantes
        remaining = conn.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0]
        assert remaining == 5
    finally:
        conn.close()


def test_purge_idempotent_when_nothing_to_purge(tmp_path, monkeypatch):
    """Si 0 row à purger → rowcount=0, no-op silencieux."""
    monkeypatch.setenv(PRINCIPLE_RETENTION_ENV, "30")
    db_path = _make_db(tmp_path)
    # Rien inséré
    conn = sqlite3.connect(str(db_path))
    try:
        n = purge_principle_evaluations_older_than(conn, days=30)
        assert n == 0
    finally:
        conn.close()


def test_purge_disabled_when_kill_switch_zero(tmp_path, monkeypatch):
    """V9_PRINCIPLE_RETENTION_DAYS=0 → aucun DELETE (kill switch)."""
    monkeypatch.setenv(PRINCIPLE_RETENTION_ENV, "0")
    db_path = _make_db(tmp_path)
    very_old = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    for i in range(10):
        _insert_row(db_path, very_old, evaluation_id=f"old_{i}")
    conn = sqlite3.connect(str(db_path))
    try:
        # days=None → lit env var → 0 → no-op
        n = purge_principle_evaluations_older_than(conn)
        assert n == 0
        # Vérifier que rien n'a été purgé
        remaining = conn.execute("SELECT COUNT(*) FROM principle_evaluations").fetchone()[0]
        assert remaining == 10
    finally:
        conn.close()


def test_purge_chunks_large_table(tmp_path, monkeypatch):
    """DELETE par chunks de 500k pour ne pas bloquer le lock writer."""
    monkeypatch.setenv(PRINCIPLE_RETENTION_ENV, "30")
    db_path = _make_db(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    # Insérer 1200 rows anciennes (chunk par défaut 500_000, donc 1 seul chunk)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = [
            (
                f"peval_old_{i}", "v1", "2025-01-01T00:00:00+00:00",
                f"snap_{i}", "P_TEST", "ACTIVE", "kind",
                "GBPUSD", "M5", "GBP",
                1, "BUY", 0.5, 0.0, "test",
                "{}", "test_src", old,
            )
            for i in range(1200)
        ]
        conn.executemany(
            f"INSERT INTO principle_evaluations ({', '.join(PRINCIPLE_EVALUATIONS_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in PRINCIPLE_EVALUATIONS_COLUMNS)})",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    conn = sqlite3.connect(str(db_path))
    try:
        n = purge_principle_evaluations_older_than(conn, days=30, chunk=500)
        assert n == 1200
    finally:
        conn.close()
