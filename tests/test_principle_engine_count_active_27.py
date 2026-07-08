"""Test unitaire — 27 principes ACTIVE, 0 SHADOW après doctrine realign (Phase C1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.v9.config import PRINCIPLE_ACTIVE_IDS
from core.v9.db_schema import get_connection, init_db
from core.v9.principle_engine import PrincipleEngine, load_principles_from_yaml


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "v9_test.db"
    init_db(path)
    return path


def test_all_27_principles_report_v9_status_active():
    principles = load_principles_from_yaml()
    assert len(principles) == 27
    for p in principles:
        assert p.v9_status == "ACTIVE", f"{p.principle_id} devrait être ACTIVE post doctrine-realign"


def test_principles_table_synced_with_27_active(db_path: Path):
    PrincipleEngine(db_path=db_path)
    conn = get_connection(db_path)
    try:
        n_active = conn.execute(
            "SELECT COUNT(*) FROM principles WHERE v9_status = 'ACTIVE'"
        ).fetchone()[0]
        n_shadow = conn.execute(
            "SELECT COUNT(*) FROM principles WHERE v9_status = 'SHADOW'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n_active == 27
    assert n_shadow == 0


def test_active_ids_length_matches_config():
    assert len(PRINCIPLE_ACTIVE_IDS) == 27
