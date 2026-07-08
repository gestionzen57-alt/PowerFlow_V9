"""Tests — core/v9/meta_agent.py + scripts/v9_meta_agent.py.

Couvre :
- scan_patterns — retourne une liste, détecte pattern_frequent sur seuil dépassé
- propose_action — retourne un dict conforme (action_type/target/rationale/confidence)
- learn_cycle — publie les propositions (confiance > 0.5) sur le bus (agent_bus)
- get_proposals — retourne une liste triée par confiance décroissante
- CLI --scan — exit code 0
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9 import agent_bus, meta_agent  # noqa: E402
from scripts import v9_meta_agent as cli  # noqa: E402


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "meta_agent_test_bus.db"


def _seed_bus_events(db_path: Path, event_type: str, count: int, payload: dict | None = None) -> None:
    for i in range(count):
        agent_bus.publish(
            event_type=event_type,
            source="test_producer",
            payload=payload or {"foo": "bar"},
            db_path=db_path,
        )


# ── scan_patterns ────────────────────────────────────────────────────
def test_scan_patterns_returns_list(db_path: Path) -> None:
    result = meta_agent.scan_patterns(hours=24, db_path=db_path)
    assert isinstance(result, list)

    _seed_bus_events(db_path, "SIGNAL_HAUSSIER", meta_agent.FREQUENT_THRESHOLD + 1)
    result = meta_agent.scan_patterns(hours=24, db_path=db_path)
    assert isinstance(result, list)
    assert any(p["pattern_type"] == "pattern_frequent" for p in result)


# ── propose_action ───────────────────────────────────────────────────
def test_propose_action_returns_dict() -> None:
    pattern = {
        "pattern_type": "pattern_frequent",
        "event_type": "UNKNOWN_EVENT_XYZ",
        "frequency": 75,
        "window_hours": 24,
    }
    action = meta_agent.propose_action(pattern)
    assert isinstance(action, dict)
    for key in ("action_type", "target", "rationale", "confidence"):
        assert key in action
    assert action["action_type"] == "new_yaml_shadow"
    assert 0.0 <= action["confidence"] <= 1.0


# ── learn_cycle ──────────────────────────────────────────────────────
def test_learn_cycle_publishes_proposals(db_path: Path) -> None:
    _seed_bus_events(db_path, "UNKNOWN_EVENT_XYZ", meta_agent.FREQUENT_THRESHOLD + 5)

    proposals = meta_agent.learn_cycle(hours=24, db_path=db_path)
    assert isinstance(proposals, list)
    assert len(proposals) > 0
    assert all(p["confidence"] > meta_agent.PROPOSAL_CONFIDENCE_MIN for p in proposals)

    conn = agent_bus.get_connection(db_path)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM events WHERE event_type = 'proposal'"
    ).fetchone()
    conn.close()
    assert row[0] == len(proposals)


# ── get_proposals ────────────────────────────────────────────────────
def test_get_proposals_returns_list(db_path: Path) -> None:
    result = meta_agent.get_proposals(limit=5, db_path=db_path)
    assert isinstance(result, list)

    _seed_bus_events(db_path, "UNKNOWN_EVENT_ABC", meta_agent.FREQUENT_THRESHOLD + 5)
    meta_agent.learn_cycle(hours=24, db_path=db_path)

    result = meta_agent.get_proposals(limit=5, db_path=db_path)
    assert isinstance(result, list)
    assert len(result) <= 5
    confidences = [p["confidence"] for p in result]
    assert confidences == sorted(confidences, reverse=True)


# ── CLI ──────────────────────────────────────────────────────────────
def test_meta_agent_cli_scan_exits_zero(db_path: Path) -> None:
    exit_code = cli.main(["--scan", "--db", str(db_path)])
    assert exit_code == 0
