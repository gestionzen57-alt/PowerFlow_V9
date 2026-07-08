"""Tests — core/v9/agent_bus.py (Agent Bus V9, bus d'événements SQLite).

Couvre : publish (création event + log), subscribe (création abonnement),
poll (consommation filtrée par abonnement, non-consommés uniquement),
get_pending_events (vue globale triée), get_agent_stats (agrégation par
agent), cleanup (purge events/agent_log par ancienneté).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.v9 import agent_bus


@pytest.fixture
def bus_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_agent_bus.db"
    agent_bus.init_agent_bus_db(db)
    return db


def test_publish_creates_event(bus_db: Path):
    event_id = agent_bus.publish(
        "NODE_BIRTH", "principle_engine", {"symbol": "GBPUSD"}, db_path=bus_db
    )
    assert event_id

    conn = agent_bus.get_connection(bus_db)
    try:
        row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[1] == "NODE_BIRTH"  # event_type
    assert row[2] == "principle_engine"  # source
    assert row[4] == "info"  # severity par défaut
    assert row[6] is None  # consumed_by


def test_subscribe_creates_subscription(bus_db: Path):
    sub_id = agent_bus.subscribe(
        "scoring_agent", "NODE_BIRTH", "on_node_birth", provider="free", db_path=bus_db
    )
    assert sub_id

    conn = agent_bus.get_connection(bus_db)
    try:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE id = ?", (sub_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[1] == "scoring_agent"  # agent_name
    assert row[2] == "NODE_BIRTH"  # event_type
    assert row[4] == "free"  # provider
    assert row[5] == 1  # enabled


def test_poll_returns_unconsumed(bus_db: Path):
    agent_bus.subscribe("scoring_agent", "NODE_BIRTH", "on_node_birth", db_path=bus_db)
    e1 = agent_bus.publish("NODE_BIRTH", "pipeline", {"i": 1}, db_path=bus_db)
    e2 = agent_bus.publish("NODE_BIRTH", "pipeline", {"i": 2}, db_path=bus_db)
    # Un event d'un autre type, non souscrit — ne doit jamais sortir.
    agent_bus.publish("OTHER_TYPE", "pipeline", {"i": 3}, db_path=bus_db)

    events = agent_bus.poll("scoring_agent", limit=5, db_path=bus_db)
    ids = {e["id"] for e in events}
    assert ids == {e1, e2}
    assert all(e["consumed_by"] == "scoring_agent" for e in events)

    # Deuxième poll : plus rien (déjà consommés).
    assert agent_bus.poll("scoring_agent", limit=5, db_path=bus_db) == []

    # Un agent sans abonnement ne reçoit jamais rien.
    assert agent_bus.poll("no_such_agent", limit=5, db_path=bus_db) == []


def test_get_pending_events_ordered(bus_db: Path):
    e1 = agent_bus.publish("A", "src", {}, db_path=bus_db)
    e2 = agent_bus.publish("B", "src", {}, db_path=bus_db)
    e3 = agent_bus.publish("C", "src", {}, db_path=bus_db)

    pending = agent_bus.get_pending_events(limit=20, db_path=bus_db)
    assert [e["id"] for e in pending] == [e1, e2, e3]
    # get_pending_events ne consomme rien.
    assert all(e["consumed_by"] is None for e in pending)
    pending_again = agent_bus.get_pending_events(limit=20, db_path=bus_db)
    assert len(pending_again) == 3


def test_get_agent_stats_returns_dict(bus_db: Path):
    agent_bus.subscribe("scoring_agent", "NODE_BIRTH", "on_node_birth", db_path=bus_db)
    agent_bus.publish("NODE_BIRTH", "pipeline", {}, db_path=bus_db)
    agent_bus.poll("scoring_agent", db_path=bus_db)

    stats = agent_bus.get_agent_stats(hours=24, db_path=bus_db)
    assert "pipeline" in stats
    assert "scoring_agent" in stats
    assert stats["pipeline"]["events_processed"] >= 1
    assert stats["scoring_agent"]["events_processed"] >= 1
    assert stats["scoring_agent"]["avg_duration_ms"] >= 0
    assert stats["scoring_agent"]["errors"] == 0


def test_cleanup_removes_old_events(bus_db: Path):
    old_iso = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    fresh_id = agent_bus.publish("FRESH", "src", {}, db_path=bus_db)

    conn = agent_bus.get_connection(bus_db)
    try:
        old_id = "old-event-id"
        conn.execute(
            "INSERT INTO events (id, event_type, source, payload, severity, "
            "created_at, consumed_by, consumed_at) VALUES (?,?,?,?,?,?,NULL,NULL)",
            (old_id, "OLD", "src", "{}", "info", old_iso),
        )
        old_log_iso = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        conn.execute(
            "INSERT INTO agent_log (id, agent_name, event_id, action, result, "
            "duration_ms, created_at) VALUES (?,?,?,?,?,?,?)",
            ("old-log-id", "src", None, "publish", "{}", 1, old_log_iso),
        )
        conn.commit()
    finally:
        conn.close()

    result = agent_bus.cleanup(days=7, db_path=bus_db)
    assert result["events_purged"] >= 1
    assert result["agent_log_purged"] >= 1

    conn = agent_bus.get_connection(bus_db)
    try:
        remaining_ids = {
            r[0] for r in conn.execute("SELECT id FROM events").fetchall()
        }
    finally:
        conn.close()
    assert old_id not in remaining_ids
    assert fresh_id in remaining_ids
