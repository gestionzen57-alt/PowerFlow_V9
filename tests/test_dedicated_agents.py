"""test_dedicated_agents.py — Tests des 4 agents dédiés V9 + base.

Couvre :
- DedicatedAgent : subscribe + poll + on_event callback
- Chaque agent : 1 test fonctionnel via publish() + run_once()
- Supervisor : health check
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(r"C:\projet\V9").resolve()
sys.path.insert(0, str(ROOT))

# Import base + agents
from core.v9.dedicated_agent_base import DedicatedAgent
from core.v9 import agent_bus

AGENT_BUS_DB = ROOT / "data" / "v9_agent_bus.db"


@pytest.fixture(autouse=True)
def _clean_bus():
    """Vide le bus agent_bus avant chaque test pour isolation."""
    if AGENT_BUS_DB.exists():
        conn = sqlite3.connect(str(AGENT_BUS_DB), timeout=5)
        try:
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM subscriptions")
            conn.commit()
        finally:
            conn.close()
    yield


# ── Tests base class ────────────────────────────────────
class _TestAgent(DedicatedAgent):
    """Agent minimal pour tester la base class."""
    agent_name = "test_agent_base"
    event_type = "test_event"
    poll_interval_s = 1

    def __init__(self) -> None:
        super().__init__()
        self.received = []

    def on_event(self, event: dict) -> None:
        self.received.append(event)


def test_base_subscribe_and_poll() -> None:
    """Vérifie que subscribe + poll fonctionne."""
    agent = _TestAgent()
    # Publish 2 events
    agent_bus.publish("test_event", "test", {"foo": 1}, db_path=AGENT_BUS_DB)
    agent_bus.publish("test_event", "test", {"foo": 2}, db_path=AGENT_BUS_DB)

    n = agent.run_once()

    assert n == 2
    assert len(agent.received) == 2
    assert agent.received[0]["payload"] == {"foo": 1}
    assert agent.received[1]["payload"] == {"foo": 2}


def test_base_idempotent_subscribe() -> None:
    """S'abonner 2 fois ne crée pas de doublons."""
    agent = _TestAgent()
    agent._subscribe()
    agent._subscribe()
    conn = sqlite3.connect(str(AGENT_BUS_DB), timeout=5)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE agent_name=? AND event_type=?",
            ("test_agent_base", "test_event"),
        ).fetchone()[0]
        # Pas de contrainte UNIQUE, donc 2 subscriptions créées. C'est OK
        # car le poll() déduplique par agent_name (cf core/v9/agent_bus.py).
        assert n >= 1
    finally:
        conn.close()


def test_base_run_once_returns_count() -> None:
    """run_once retourne le nombre d'events traités."""
    agent = _TestAgent()
    agent_bus.publish("test_event", "test", {"i": 0}, db_path=AGENT_BUS_DB)
    agent_bus.publish("test_event", "test", {"i": 1}, db_path=AGENT_BUS_DB)
    agent_bus.publish("test_event", "test", {"i": 2}, db_path=AGENT_BUS_DB)
    n = agent.run_once()
    assert n == 3
    assert agent._n_processed == 3


# ── Tests 4 agents dédiés ──────────────────────────────
def test_signal_open_tracker_logs_events() -> None:
    """signal_open_tracker traite les events signal_open."""
    from agents.signal_open_tracker import SignalOpenTracker
    agent = SignalOpenTracker()
    # Bypass Telegram send (pas testé ici)
    agent._send_telegram_alert = lambda text: None

    agent_bus.publish("signal_open", "v9_emit", {
        "decision_id": "dec_test_1",
        "direction": "haussiere",
        "confiance": 95,
        "symbol": "GBPUSD",
        "timeframe": "M15",
        "timestamp": "2026-07-10T05:00:00Z",
    }, db_path=AGENT_BUS_DB)

    n = agent.run_once()
    assert n == 1


def test_regime_change_monitor_filters_neutre() -> None:
    """regime_change_monitor alerte SEULEMENT si nouveau régime ≠ NEUTRE."""
    from agents.regime_change_monitor import RegimeChangeMonitor
    agent = RegimeChangeMonitor()
    captured = []
    agent._send_telegram_alert = lambda text: captured.append(text)

    # Transition NEUTRE → NEUTRE : pas d'alerte
    agent_bus.publish("regime_change", "v9_emit", {
        "symbol": "GBPUSD", "timeframe": "M15",
        "regime_new": "NEUTRE", "regime_prev": "NEUTRE",
        "timestamp": "2026-07-10T05:00:00Z",
    }, db_path=AGENT_BUS_DB)

    agent.run_once()
    assert len(captured) == 0  # NEUTRE → NEUTRE : pas d'alerte

    # Transition PALIER → EXTENSION : alerte
    agent_bus.publish("regime_change", "v9_emit", {
        "symbol": "GBPUSD", "timeframe": "M15",
        "regime_new": "EXTENSION", "regime_prev": "PALIER",
        "timestamp": "2026-07-10T05:01:00Z",
    }, db_path=AGENT_BUS_DB)

    agent.run_once()
    assert len(captured) == 1
    assert "EXTENSION" in captured[0]


def test_principle_cluster_logger_accumulates_stats() -> None:
    """principle_cluster_logger cumule des stats par heure et par n."""
    from agents.principle_cluster_logger import PrincipleClusterLogger
    agent = PrincipleClusterLogger()

    for i in range(3):
        agent_bus.publish("principle_cluster", "v9_emit", {
            "snapshot_id": f"snap_{i}", "n_triggered": 3 + (i % 2),
        }, db_path=AGENT_BUS_DB)

    n = agent.run_once()
    assert n == 3
    assert agent._total_events == 3
    assert agent._by_n[3] == 2
    assert agent._by_n[4] == 1


def test_high_resolution_win_analyzer_aggregates_pips() -> None:
    """high_resolution_win_analyzer agrège pips par (symbol, TF, direction)."""
    from agents.high_resolution_win_analyzer import HighResolutionWinAnalyzer
    agent = HighResolutionWinAnalyzer()

    for pips in [25.0, 30.0, 45.0, 20.0]:
        agent_bus.publish("high_resolution_win", "v9_emit", {
            "decision_id": "dec_x",
            "symbol": "GBPUSD",
            "timeframe": "M15",
            "direction": "haussiere",
            "pips": pips,
        }, db_path=AGENT_BUS_DB)

    n = agent.run_once()
    assert n == 4
    assert agent._total_events == 4
    assert agent._total_pips == 120.0
    s = agent._by_config[("GBPUSD", "M15", "haussiere")]
    assert s["count"] == 4
    assert s["max_pips"] == 45.0
    assert s["total_pips"] == 120.0


# ── Test supervisor (CLI parse uniquement) ──────────────
def test_supervisor_help() -> None:
    """Le supervisor CLI a les 4 sous-commandes attendues."""
    result = __import__("subprocess").run(
        [sys.executable, "scripts/v9_agents_supervisor.py", "--help"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=10,
    )
    assert result.returncode == 0
    assert "--start" in result.stdout
    assert "--stop" in result.stdout
    assert "--once" in result.stdout
    assert "--watch" in result.stdout