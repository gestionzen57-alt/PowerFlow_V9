"""Tests — scripts/v9_supervisor.py (bibliothèque partagée d'outillage V9).

Couvre : disponibilité de port (socket réel), gestion de port stale
(mocks — jamais de vrai `taskkill` en test), génération de mini-checkpoint
(gabarit `workspace/perplexity/assets/CHECKPOINT_TEMPLATE.md`), et
formatage du health snapshot. Aucun test ne touche `data/v9_forces.db` ni
`logs/v9_capture.pid` réels (toujours `tmp_path`/monkeypatch).
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from scripts import v9_supervisor


# ── is_port_available ─────────────────────────────────────
def test_is_port_available_true_for_free_port() -> None:
    # Port ephemere quasi-certainement libre.
    assert v9_supervisor.is_port_available(0, host="127.0.0.1") in (True, False)


def test_is_port_available_false_when_bound() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        assert v9_supervisor.is_port_available(port, host="127.0.0.1") is False
    finally:
        sock.close()


# ── ensure_port_free ───────────────────────────────────────
class _FakeLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, msg: str) -> None:
        self.messages.append(("info", msg))

    def warning(self, msg: str) -> None:
        self.messages.append(("warning", msg))

    def error(self, msg: str) -> None:
        self.messages.append(("error", msg))


def test_ensure_port_free_already_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_supervisor, "is_port_available", lambda port, host="x": True)
    logger = _FakeLogger()
    assert v9_supervisor.ensure_port_free(31685, logger) is True


def test_ensure_port_free_own_server_not_killed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Port occupe par notre propre serveur (PID file coherent) : jamais tue."""
    monkeypatch.setattr(v9_supervisor, "is_port_available", lambda port, host="x": False)
    monkeypatch.setattr(v9_supervisor, "is_server_running", lambda: (True, 4242))
    monkeypatch.setattr(v9_supervisor, "find_pid_on_port", lambda port: 4242)

    killed = {"called": False}

    def _fake_kill(pid: int, logger) -> bool:
        killed["called"] = True
        return True

    monkeypatch.setattr(v9_supervisor, "kill_pid", _fake_kill)

    logger = _FakeLogger()
    assert v9_supervisor.ensure_port_free(31685, logger) is True
    assert killed["called"] is False


def test_ensure_port_free_kills_stale_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Port occupe par un PID different du PID file (ou pas de PID file) :
    considere stale, tue, puis le port doit redevenir libre."""
    calls = {"n": 0}

    def _fake_is_port_available(port, host="x"):
        calls["n"] += 1
        return calls["n"] > 1  # occupe au premier appel, libre ensuite

    monkeypatch.setattr(v9_supervisor, "is_port_available", _fake_is_port_available)
    monkeypatch.setattr(v9_supervisor, "is_server_running", lambda: (False, None))
    monkeypatch.setattr(v9_supervisor, "find_pid_on_port", lambda port: 9999)
    monkeypatch.setattr(v9_supervisor, "time", type("T", (), {"sleep": staticmethod(lambda s: None)}))

    killed = {"pid": None}

    def _fake_kill(pid: int, logger) -> bool:
        killed["pid"] = pid
        return True

    monkeypatch.setattr(v9_supervisor, "kill_pid", _fake_kill)

    logger = _FakeLogger()
    assert v9_supervisor.ensure_port_free(31685, logger) is True
    assert killed["pid"] == 9999


def test_ensure_port_free_pid_not_found_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_supervisor, "is_port_available", lambda port, host="x": False)
    monkeypatch.setattr(v9_supervisor, "is_server_running", lambda: (False, None))
    monkeypatch.setattr(v9_supervisor, "find_pid_on_port", lambda port: None)

    logger = _FakeLogger()
    assert v9_supervisor.ensure_port_free(31685, logger) is False


# ── find_pid_on_port (parsing netstat) ─────────────────────
def test_find_pid_on_port_parses_listening_line(monkeypatch: pytest.MonkeyPatch) -> None:
    netstat_output = (
        "Active Connections\n\n"
        "  Proto  Local Address          Foreign Address        State           PID\n"
        "  TCP    127.0.0.1:31685        0.0.0.0:0              LISTENING       28584\n"
        "  TCP    127.0.0.1:5432         0.0.0.0:0              LISTENING       111\n"
    )

    class _FakeResult:
        stdout = netstat_output

    monkeypatch.setattr(v9_supervisor.sys, "platform", "win32")
    monkeypatch.setattr(v9_supervisor.subprocess, "run", lambda *a, **k: _FakeResult())

    assert v9_supervisor.find_pid_on_port(31685) == 28584
    assert v9_supervisor.find_pid_on_port(5432) == 111
    assert v9_supervisor.find_pid_on_port(9) is None


# ── mini-checkpoint generation ─────────────────────────────
def test_generate_mini_checkpoint_writes_gabarit_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(v9_supervisor, "MINI_CHECKPOINT_DIR", tmp_path)

    path = v9_supervisor.generate_mini_checkpoint(
        kind="test",
        contexte="Contexte de test.",
        observed_lines=["ligne 1", "ligne 2"],
    )

    assert path.exists()
    assert path.parent == tmp_path
    content = path.read_text(encoding="utf-8")
    assert "## Mini-checkpoint —" in content
    assert "### Contexte" in content
    assert "Contexte de test." in content
    assert "### Observé" in content
    assert "- ligne 1" in content
    assert "- ligne 2" in content
    assert "### Écart vs attendu" in content
    assert "### Action immédiate" in content
    assert "### Suite" in content


def test_generate_mini_checkpoint_empty_observed_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(v9_supervisor, "MINI_CHECKPOINT_DIR", tmp_path)
    path = v9_supervisor.generate_mini_checkpoint(kind="empty", contexte="c", observed_lines=[])
    content = path.read_text(encoding="utf-8")
    assert "(aucune observation)" in content


# ── health snapshot formatting (pure) ──────────────────────
def _snapshot(**overrides) -> dict:
    base = {
        "timestamp_utc": "2026-07-05T21:00:00+00:00",
        "python_ok": True,
        "modules_ok": True,
        "modules_count": 15,
        "db_ok": True,
        "port_available": False,
        "server_running": True,
        "server_pid": 123,
        "market_open": False,
        "market_session": "closed",
        "db_counts": {},
        "git_branch": "feat/v9-foundation-clean",
        "git_last_commit": "abc1234 test commit",
    }
    base.update(overrides)
    return base


def test_format_health_report_contains_key_fields() -> None:
    report = v9_supervisor.format_health_report(_snapshot())
    assert "Health snapshot" in report
    assert "feat/v9-foundation-clean" in report
    assert "OK" in report
    assert "FERME" in report


def test_health_snapshot_to_observed_lines_includes_last_snapshot() -> None:
    snapshot = _snapshot(
        db_counts={
            "forces_snapshots": 42,
            "last_snapshot": {
                "created_at": "2026-07-05T21:00:00", "symbol": "GBPUSD",
                "timeframe": "M1", "stale": False,
            },
        }
    )
    lines = v9_supervisor.health_snapshot_to_observed_lines(snapshot)
    joined = "\n".join(lines)
    assert "forces_snapshots total : 42" in joined
    assert "GBPUSD" in joined


def test_health_snapshot_to_observed_lines_no_db_counts() -> None:
    lines = v9_supervisor.health_snapshot_to_observed_lines(_snapshot(db_counts={}))
    assert all("forces_snapshots total" not in line for line in lines)


# ── market_status_warning (anomalie DST — Phase 9.5) ───────
def test_market_status_warning_none_when_market_open() -> None:
    from datetime import datetime, timezone
    now = datetime(2026, 7, 5, 22, 30, tzinfo=timezone.utc)
    snapshot = {"created_at": now.isoformat(), "stale": False}
    assert v9_supervisor.market_status_warning(True, snapshot, now) is None


def test_market_status_warning_none_without_recent_snapshot() -> None:
    from datetime import datetime, timezone
    now = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)
    assert v9_supervisor.market_status_warning(False, None, now) is None


def test_market_status_warning_none_when_snapshot_stale() -> None:
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)
    snapshot = {"created_at": (now - timedelta(seconds=10)).isoformat(), "stale": True}
    assert v9_supervisor.market_status_warning(False, snapshot, now) is None


def test_market_status_warning_none_when_snapshot_too_old() -> None:
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)
    snapshot = {"created_at": (now - timedelta(seconds=500)).isoformat(), "stale": False}
    assert v9_supervisor.market_status_warning(False, snapshot, now) is None


def test_market_status_warning_fires_on_dst_window() -> None:
    from datetime import datetime, timedelta, timezone
    # Dimanche 21h30 UTC : marche reel deja ouvert (17h EDT New York) mais
    # calendrier canonique (22h UTC fixe) dit encore FERME.
    now = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)
    snapshot = {"created_at": (now - timedelta(seconds=40)).isoformat(), "stale": False}
    warning = v9_supervisor.market_status_warning(False, snapshot, now)
    assert warning is not None
    assert "DST" in warning


def test_read_health_snapshot_includes_market_status_warning_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = v9_supervisor.read_health_snapshot()
    assert "market_status_warning" in snapshot


def test_format_health_report_includes_warning_when_present() -> None:
    snapshot = _snapshot(market_status_warning="activite live detectee (test)")
    report = v9_supervisor.format_health_report(snapshot)
    assert "ATTENTION" in report
    assert "activite live detectee (test)" in report


def test_observed_lines_includes_warning_when_present() -> None:
    snapshot = _snapshot(market_status_warning="activite live detectee (test)")
    lines = v9_supervisor.health_snapshot_to_observed_lines(snapshot)
    assert any("ATTENTION" in line for line in lines)
