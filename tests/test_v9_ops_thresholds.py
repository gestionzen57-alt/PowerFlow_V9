"""Tests — sous-commande `thresholds` de scripts/v9_ops.py.

Couvre le handler cmd_thresholds() : délègue à
core.v9.adaptive_thresholds.propose_thresholds_diff() et affiche un JSON
valide (current vs proposed + rationale). propose_thresholds_diff() est
mockée — aucun accès DB live.
"""

from __future__ import annotations

import json
import sys

import pytest

from scripts import v9_ops


def _fake_diff() -> dict:
    return {
        "current": {"REPLAY_MIN_CAS": 3},
        "proposed": {"REPLAY_MIN_CAS": 1},
        "sample_size": {"REPLAY_MIN_CAS": "n_decisions_resolved=0"},
        "ready_to_apply": False,
        "rationale": {"REPLAY_MIN_CAS": "0 décisions résolues -> seuil conservé."},
    }


def test_cmd_thresholds_returns_0_and_prints_valid_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "core.v9.adaptive_thresholds.propose_thresholds_diff", lambda: _fake_diff()
    )

    assert v9_ops.cmd_thresholds([]) == 0

    out = capsys.readouterr().out
    first_line = out.splitlines()[0]
    # Le bloc JSON commence par '{' — on reparse le JSON pretty-printed.
    json_block = out.split("\n--- Seuils adaptatifs")[0]
    parsed = json.loads(json_block)
    assert parsed == _fake_diff()
    assert first_line == "{"


def test_thresholds_help_lists_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert v9_ops.cmd_thresholds(["--help"]) == 0
    assert "thresholds" in capsys.readouterr().out


def test_main_routes_thresholds_to_handler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "core.v9.adaptive_thresholds.propose_thresholds_diff", lambda: _fake_diff()
    )
    monkeypatch.setattr(sys, "argv", ["v9_ops.py", "thresholds"])

    assert v9_ops.main() == 0
    assert "ready_to_apply" in capsys.readouterr().out
