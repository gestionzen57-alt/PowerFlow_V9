"""Tests — scripts/v9_ops.py (point d'entrée unique opérateur V9).

Couvre le routage des sous-commandes vers les scripts délégués. Tout
`subprocess.run` est mocké — aucun vrai sous-script n'est jamais lancé.
Pas de test fonctionnel DB/intégration (hors scope, cf. chantier C-5b).
Périmètre gel : 0 modification de v9_ops.py (DECISIONS_LOG.md 2026-07-07
"Audit dette résiduelle").
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from scripts import v9_ops


def _fake_run(returncode: int = 0):
    calls: list[list[str]] = []

    def _run(cmd, cwd=None):
        calls.append(cmd)
        return MagicMock(returncode=returncode)

    return _run, calls


def test_routes_check_calls_deploy_check(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run, calls = _fake_run()
    monkeypatch.setattr(v9_ops.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["v9_ops.py", "check"])

    assert v9_ops.main() == 0
    assert calls == [[sys.executable, str(v9_ops.SCRIPTS_DIR / "deploy_v9.py"), "--check"]]


def test_routes_start_calls_deploy_start(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run, calls = _fake_run()
    monkeypatch.setattr(v9_ops.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["v9_ops.py", "start"])

    assert v9_ops.main() == 0
    assert calls == [[sys.executable, str(v9_ops.SCRIPTS_DIR / "deploy_v9.py"), "--start"]]


def test_routes_health_calls_supervisor_health(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run, calls = _fake_run()
    monkeypatch.setattr(v9_ops.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["v9_ops.py", "health"])

    assert v9_ops.main() == 0
    assert calls == [[sys.executable, str(v9_ops.SCRIPTS_DIR / "v9_supervisor.py"), "--health"]]


def test_routes_dashboard_calls_dashboard_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run, calls = _fake_run()
    monkeypatch.setattr(v9_ops.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["v9_ops.py", "dashboard"])

    assert v9_ops.main() == 0
    assert calls == [[sys.executable, str(v9_ops.SCRIPTS_DIR / "v9_dashboard.py"), "--once"]]


def test_unknown_subcommand_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["v9_ops.py", "nope-inconnue"])

    assert v9_ops.main() != 0


def test_run_forwards_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v9_ops.subprocess, "run", lambda *a, **k: MagicMock(returncode=42))

    assert v9_ops._run("deploy_v9.py", ["--check"]) == 42


def test_no_subcommand_shows_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["v9_ops.py"])

    assert v9_ops.main() == 0
    assert "v9_ops.py" in capsys.readouterr().out


def test_subcommand_with_extra_args(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run, calls = _fake_run()
    monkeypatch.setattr(v9_ops.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["v9_ops.py", "replay", "--list", "v9-replay-001"])

    assert v9_ops.main() == 0
    assert calls == [
        [
            sys.executable,
            str(v9_ops.SCRIPTS_DIR / "v9_replay.py"),
            "--list",
            "v9-replay-001",
        ]
    ]
