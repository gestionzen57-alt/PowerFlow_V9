"""Tests — scripts/v9_bootstrap.py (procédure --boot).

Toutes les dépendances externes (health snapshot, port, démarrage serveur,
génération de mini-checkpoint) sont mockées : aucun test ne démarre un
vrai `core.v9.capture_server`, ni ne touche `logs/v9_capture.pid` réel.
"""

from __future__ import annotations

import pytest

from scripts import v9_bootstrap


def _snapshot(**overrides) -> dict:
    base = {
        "timestamp_utc": "2026-07-05T21:00:00+00:00",
        "python_ok": True,
        "modules_ok": True,
        "modules_count": 15,
        "db_ok": True,
        "port_available": True,
        "server_running": False,
        "server_pid": None,
        "market_open": False,
        "market_session": "closed",
        "db_counts": {},
        "git_branch": "feat/v9-foundation-clean",
        "git_last_commit": "abc1234 test",
    }
    base.update(overrides)
    return base


def _patch_common(monkeypatch: pytest.MonkeyPatch, **snapshot_overrides):
    snapshot = _snapshot(**snapshot_overrides)
    monkeypatch.setattr(v9_bootstrap, "read_health_snapshot", lambda: snapshot)
    monkeypatch.setattr(v9_bootstrap, "health_snapshot_to_observed_lines", lambda snap: ["obs"])
    monkeypatch.setattr(v9_bootstrap.time, "sleep", lambda s: None)
    return snapshot


def test_run_boot_fails_fast_on_blocking_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch, python_ok=False)

    called = {"ensure_port_free": False}
    monkeypatch.setattr(
        v9_bootstrap, "ensure_port_free",
        lambda port, logger: called.__setitem__("ensure_port_free", True) or True,
    )

    assert v9_bootstrap.run_boot() == 1
    assert called["ensure_port_free"] is False


def test_run_boot_dry_run_does_not_touch_server(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)

    def _boom(*a, **k):
        raise AssertionError("dry-run ne doit pas demarrer/arreter de process")

    monkeypatch.setattr(v9_bootstrap, "ensure_port_free", _boom)
    monkeypatch.setattr(v9_bootstrap, "start_capture_server_background", _boom)

    assert v9_bootstrap.run_boot(dry_run=True) == 0


def test_run_boot_port_not_freeable_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(v9_bootstrap, "ensure_port_free", lambda port, logger: False)

    assert v9_bootstrap.run_boot() == 1


def test_run_boot_starts_server_when_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(v9_bootstrap, "ensure_port_free", lambda port, logger: True)

    states = iter([(False, None), (True, 555)])
    monkeypatch.setattr(v9_bootstrap, "is_server_running", lambda: next(states))

    started = {"called": False}
    monkeypatch.setattr(
        v9_bootstrap, "start_capture_server_background",
        lambda logger: started.__setitem__("called", True),
    )

    checkpoint_calls = []
    monkeypatch.setattr(
        v9_bootstrap, "generate_mini_checkpoint",
        lambda **kwargs: checkpoint_calls.append(kwargs) or __import__("pathlib").Path("dummy.md"),
    )

    assert v9_bootstrap.run_boot() == 0
    assert started["called"] is True
    assert len(checkpoint_calls) == 1
    assert checkpoint_calls[0]["kind"] == "boot"


def test_run_boot_server_already_running_skips_start(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch, server_running=True, server_pid=99)
    monkeypatch.setattr(v9_bootstrap, "ensure_port_free", lambda port, logger: True)
    monkeypatch.setattr(v9_bootstrap, "is_server_running", lambda: (True, 99))

    def _boom(*a, **k):
        raise AssertionError("ne doit pas redemarrer un serveur deja actif")

    monkeypatch.setattr(v9_bootstrap, "start_capture_server_background", _boom)
    monkeypatch.setattr(
        v9_bootstrap, "generate_mini_checkpoint",
        lambda **kwargs: __import__("pathlib").Path("dummy.md"),
    )

    assert v9_bootstrap.run_boot() == 0


def test_run_boot_server_fails_to_start_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(v9_bootstrap, "ensure_port_free", lambda port, logger: True)

    states = iter([(False, None), (False, None)])
    monkeypatch.setattr(v9_bootstrap, "is_server_running", lambda: next(states))
    monkeypatch.setattr(v9_bootstrap, "start_capture_server_background", lambda logger: None)

    assert v9_bootstrap.run_boot() == 1


def test_run_boot_write_checkpoint_false_skips_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch, server_running=True, server_pid=1)
    monkeypatch.setattr(v9_bootstrap, "ensure_port_free", lambda port, logger: True)
    monkeypatch.setattr(v9_bootstrap, "is_server_running", lambda: (True, 1))

    def _boom(**kwargs):
        raise AssertionError("write_checkpoint=False ne doit pas generer de mini-checkpoint")

    monkeypatch.setattr(v9_bootstrap, "generate_mini_checkpoint", _boom)

    assert v9_bootstrap.run_boot(write_checkpoint=False) == 0


def test_run_boot_skip_start_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(v9_bootstrap, "ensure_port_free", lambda port, logger: True)
    monkeypatch.setattr(v9_bootstrap, "is_server_running", lambda: (False, None))

    def _boom(*a, **k):
        raise AssertionError("--skip-start ne doit jamais demarrer le serveur")

    monkeypatch.setattr(v9_bootstrap, "start_capture_server_background", _boom)
    monkeypatch.setattr(
        v9_bootstrap, "generate_mini_checkpoint",
        lambda **kwargs: __import__("pathlib").Path("dummy.md"),
    )

    assert v9_bootstrap.run_boot(skip_start=True) == 0
