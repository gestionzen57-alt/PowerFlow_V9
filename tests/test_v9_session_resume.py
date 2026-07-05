"""Tests — scripts/v9_session_resume.py (procédure --resume).

`ROOT_DIR` et `REQUIRED_READING_ORDER` sont monkeypatchés vers un
`tmp_path` isolé pour chaque test de détection de fichiers/rupture de
continuité — aucun test ne dépend de l'état réel du dépôt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import v9_session_resume


# ── check_required_files ───────────────────────────────────
def test_check_required_files_all_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(v9_session_resume, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(v9_session_resume, "REQUIRED_READING_ORDER", ["a.md", "b.md"])

    present, missing = v9_session_resume.check_required_files()
    assert present == ["a.md", "b.md"]
    assert missing == []


def test_check_required_files_detects_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(v9_session_resume, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(v9_session_resume, "REQUIRED_READING_ORDER", ["a.md", "b.md"])

    present, missing = v9_session_resume.check_required_files()
    assert present == ["a.md"]
    assert missing == ["b.md"]


# ── find_referenced_checkpoints / check_checkpoint_references ──
def test_find_referenced_checkpoints_extracts_paths(tmp_path: Path) -> None:
    state_md = tmp_path / "STATE.md"
    state_md.write_text(
        "Voir docs/checkpoints/CHECKPOINT_A.md et docs/checkpoints/CHECKPOINT_B.md.\n"
        "Reference dupliquee : docs/checkpoints/CHECKPOINT_A.md.",
        encoding="utf-8",
    )
    refs = v9_session_resume.find_referenced_checkpoints(state_md)
    assert refs == ["docs/checkpoints/CHECKPOINT_A.md", "docs/checkpoints/CHECKPOINT_B.md"]


def test_find_referenced_checkpoints_missing_file_returns_empty(tmp_path: Path) -> None:
    assert v9_session_resume.find_referenced_checkpoints(tmp_path / "absent.md") == []


def test_check_checkpoint_references_flags_missing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(v9_session_resume, "ROOT_DIR", tmp_path)
    (tmp_path / "docs" / "checkpoints").mkdir(parents=True)
    (tmp_path / "docs" / "checkpoints" / "CHECKPOINT_A.md").write_text("x", encoding="utf-8")

    state_md = tmp_path / "STATE.md"
    state_md.write_text(
        "docs/checkpoints/CHECKPOINT_A.md et docs/checkpoints/CHECKPOINT_MISSING.md",
        encoding="utf-8",
    )

    existing, missing = v9_session_resume.check_checkpoint_references(state_md)
    assert existing == ["docs/checkpoints/CHECKPOINT_A.md"]
    assert missing == ["docs/checkpoints/CHECKPOINT_MISSING.md"]


# ── run_resume orchestration (mocked) ──────────────────────
def _snapshot() -> dict:
    return {
        "timestamp_utc": "2026-07-05T21:00:00+00:00", "python_ok": True, "modules_ok": True,
        "modules_count": 15, "db_ok": True, "port_available": True, "server_running": True,
        "server_pid": 1, "market_open": False, "market_session": "closed", "db_counts": {},
        "git_branch": "feat/v9-foundation-clean", "git_last_commit": "abc1234 test",
    }


def _patch_common(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, required_files: list[str]):
    for rel in required_files:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(v9_session_resume, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(v9_session_resume, "REQUIRED_READING_ORDER", required_files)
    monkeypatch.setattr(v9_session_resume, "git_branch", lambda: "feat/v9-foundation-clean")
    monkeypatch.setattr(v9_session_resume, "git_last_commit", lambda: "abc1234 test")
    monkeypatch.setattr(v9_session_resume, "git_log_recent", lambda n=10: ["abc1234 test"])
    monkeypatch.setattr(v9_session_resume, "git_status_dirty", lambda: [])
    monkeypatch.setattr(v9_session_resume, "read_health_snapshot", lambda: _snapshot())
    monkeypatch.setattr(v9_session_resume, "health_snapshot_to_observed_lines", lambda snap: ["obs"])
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "STATE.md").write_text("Aucune reference a un checkpoint.", encoding="utf-8")


def test_run_resume_continuity_intact_exit_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(tmp_path, monkeypatch, ["board.md"])
    assert v9_session_resume.run_resume(write_checkpoint=False) == 0


def test_run_resume_missing_file_returns_exit_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(tmp_path, monkeypatch, ["board.md", "missing.md"])
    (tmp_path / "missing.md").unlink()
    assert v9_session_resume.run_resume(write_checkpoint=False) == 2


def test_run_resume_missing_checkpoint_reference_returns_exit_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_common(tmp_path, monkeypatch, ["board.md"])
    (tmp_path / "docs" / "STATE.md").write_text(
        "docs/checkpoints/CHECKPOINT_NOPE.md", encoding="utf-8"
    )
    assert v9_session_resume.run_resume(write_checkpoint=False) == 2


def test_run_resume_writes_checkpoint_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_common(tmp_path, monkeypatch, ["board.md"])
    calls = []
    monkeypatch.setattr(
        v9_session_resume, "generate_mini_checkpoint",
        lambda **kwargs: calls.append(kwargs) or tmp_path / "dummy.md",
    )
    assert v9_session_resume.run_resume(write_checkpoint=True) == 0
    assert len(calls) == 1
    assert calls[0]["kind"] == "resume"
