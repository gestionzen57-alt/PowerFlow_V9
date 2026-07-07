"""Tests agent_telemetry — Sprint V9 2026-07-07."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v9 import agent_telemetry


@pytest.fixture
def tmp_db(monkeypatch):
    """Crée une DB temporaire pour les tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    monkeypatch.setattr(agent_telemetry, "DB_PATH", db_path)
    agent_telemetry.init_telemetry_db()
    yield db_path
    db_path.unlink(missing_ok=True)


def test_init_creates_table_and_view(tmp_db):
    """init_telemetry_db doit créer la table ET la vue."""
    con = sqlite3.connect(str(tmp_db))
    tables = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_telemetry'"
    ).fetchall()
    views = con.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='v_agent_precision_report'"
    ).fetchall()
    con.close()
    assert len(tables) == 1
    assert len(views) == 1


def test_record_inserts_row(tmp_db):
    row_id = agent_telemetry.record(
        agent_name="force_reader",
        snapshot_id="snap_001",
        latency_ms=12.5,
        status="OK",
    )
    assert row_id > 0


def test_record_with_error(tmp_db):
    agent_telemetry.record(
        agent_name="scene_builder",
        status="ERROR",
        notes="test error",
    )
    report = agent_telemetry.report(window_days=1)
    assert len(report) >= 1


def test_report_empty_when_no_data(tmp_db):
    report = agent_telemetry.report(window_days=7)
    assert isinstance(report, list)


def test_record_drift_signal(tmp_db):
    """drift_signal doit être persisté (utilisé pour alerte)."""
    agent_telemetry.record(
        agent_name="decision_maker",
        drift_signal=0.85,
    )
    con = sqlite3.connect(str(tmp_db))
    row = con.execute(
        "SELECT drift_signal FROM agent_telemetry WHERE agent_name='decision_maker'"
    ).fetchone()
    con.close()
    assert row[0] == 0.85


def test_init_is_idempotent(tmp_db):
    """init_telemetry_db doit pouvoir être appelé plusieurs fois sans erreur."""
    agent_telemetry.init_telemetry_db()
    agent_telemetry.init_telemetry_db()
    # pas d'exception = OK


def test_record_3_hits_returns_aggregated_report(tmp_db):
    """3 hits sur un agent = 3 dans le rapport."""
    for i in range(3):
        agent_telemetry.record(agent_name="behavior_analyst", latency_ms=50.0 + i)
    report = agent_telemetry.report(window_days=1)
    ba = [r for r in report if r["agent_name"] == "behavior_analyst"]
    assert len(ba) == 1
    assert ba[0]["total_hits"] == 3
