"""tests/test_v9_phase62.py — Phase 62 motion CEO 48H.

Tests pour pipeline_orchestrator.
"""
import pytest
from pathlib import Path


def test_load_state_default(tmp_path, monkeypatch):
    from scripts.v9_pipeline_orchestrator import (
        load_state, STATE_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.STATE_PATH",
        tmp_path / "state.json",
    )
    state = load_state()
    assert "workers" in state


def test_save_state(tmp_path, monkeypatch):
    from scripts.v9_pipeline_orchestrator import (
        save_state, STATE_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.STATE_PATH",
        tmp_path / "state.json",
    )
    save_state({"test": 1})
    assert (tmp_path / "state.json").exists()


def test_dlq_push(tmp_path, monkeypatch):
    from scripts.v9_pipeline_orchestrator import (
        dlq_push, dlq_count, DLQ_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.DLQ_PATH",
        tmp_path / "dlq.jsonl",
    )
    dlq_push("task1", "error1")
    assert dlq_count() == 1


def test_dlq_count_empty(tmp_path, monkeypatch):
    from scripts.v9_pipeline_orchestrator import (
        dlq_count, DLQ_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.DLQ_PATH",
        tmp_path / "nonexistent.jsonl",
    )
    assert dlq_count() == 0


def test_restart_worker(tmp_path, monkeypatch):
    from scripts.v9_pipeline_orchestrator import (
        restart_worker, load_state, STATE_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.STATE_PATH",
        tmp_path / "state.json",
    )
    state = load_state()
    w = restart_worker("worker1", state)
    assert w["status"] == "restarting"


def test_heartbeat(tmp_path, monkeypatch):
    from scripts.v9_pipeline_orchestrator import (
        heartbeat, load_state, STATE_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.STATE_PATH",
        tmp_path / "state.json",
    )
    state = load_state()
    w = heartbeat("worker1", state)
    assert w["status"] == "alive"


def test_check_health_empty(tmp_path, monkeypatch):
    from scripts.v9_pipeline_orchestrator import (
        check_health, STATE_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.STATE_PATH",
        tmp_path / "state.json",
    )
    health = check_health({})
    assert health["n_workers"] == 0


def test_check_health_all_alive(tmp_path, monkeypatch):
    from scripts.v9_pipeline_orchestrator import (
        check_health, heartbeat, STATE_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.STATE_PATH",
        tmp_path / "state.json",
    )
    state = {"workers": {}}
    heartbeat("w1", state)
    heartbeat("w2", state)
    health = check_health(state)
    assert health["n_alive"] == 2


def test_orchestrate():
    from scripts.v9_pipeline_orchestrator import orchestrate
    result = orchestrate(["w1", "w2"])
    assert "workers" in result


def test_main_status(monkeypatch, capsys):
    from scripts.v9_pipeline_orchestrator import main
    import tempfile
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.STATE_PATH",
        Path(tempfile.mkdtemp()) / "state.json",
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.DLQ_PATH",
        Path(tempfile.mkdtemp()) / "dlq.jsonl",
    )
    exit_code = main(["--status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PIPELINE ORCHESTRATOR" in captured.out


def test_main_with_workers(monkeypatch, capsys):
    from scripts.v9_pipeline_orchestrator import main
    import tempfile
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.STATE_PATH",
        Path(tempfile.mkdtemp()) / "state.json",
    )
    monkeypatch.setattr(
        "scripts.v9_pipeline_orchestrator.DLQ_PATH",
        Path(tempfile.mkdtemp()) / "dlq.jsonl",
    )
    exit_code = main(["--workers", "w1", "w2"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ORCHESTRATED" in captured.out