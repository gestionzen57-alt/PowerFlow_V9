"""Tests — sous-commandes `propose` / `approve` / `reject` de scripts/v9_ops.py.

Couvre les handlers cmd_propose() / cmd_approve() / cmd_reject() : délèguent à
core.v9.learning_loop (propose_from_outcomes, list_proposals, approve_proposal,
reject_proposal). Toutes mockées — aucun accès DB live.
"""

from __future__ import annotations

import pytest

from scripts import v9_ops


def _fake_pending() -> list[dict]:
    return [
        {
            "id": "abc123",
            "target": "signal:BUY:weight_offset",
            "rationale": "WR=62% sur n=25 décisions résolues.",
            "observed_wr": 0.62,
            "observed_n": 25,
            "score": 42.5,
            "status": "PENDING",
        }
    ]


def test_cmd_propose_prints_pending_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "core.v9.learning_loop.propose_from_outcomes", lambda window_days: []
    )
    monkeypatch.setattr(
        "core.v9.learning_loop.list_proposals", lambda status: _fake_pending()
    )

    assert v9_ops.cmd_propose([]) == 0

    out = capsys.readouterr().out
    assert "abc123" in out
    assert "signal:BUY:weight_offset" in out


def test_cmd_approve_found_and_not_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "core.v9.learning_loop.approve_proposal", lambda proposal_id: proposal_id == "abc123"
    )

    assert v9_ops.cmd_approve(["abc123"]) == 0
    assert "APPROVED id=abc123" in capsys.readouterr().out

    assert v9_ops.cmd_approve(["missing"]) == 1
    assert "NOT FOUND" in capsys.readouterr().out


def test_cmd_reject_found_and_not_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "core.v9.learning_loop.reject_proposal",
        lambda proposal_id, reason="": proposal_id == "abc123",
    )

    assert v9_ops.cmd_reject(["abc123", "faux positif"]) == 0
    assert "REJECTED id=abc123" in capsys.readouterr().out

    assert v9_ops.cmd_reject(["missing"]) == 1
    assert "NOT FOUND" in capsys.readouterr().out
