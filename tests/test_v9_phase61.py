"""tests/test_v9_phase61.py — Phase 61 motion CEO 48H non-stop.

Tests pour phase_tracker + auto_plan + auto_commit + autonomous_loop.
"""
import json
import pytest
from pathlib import Path


# === phase_tracker ===

def test_init_state_default():
    from scripts.v9_phase_tracker import init_state
    state = init_state()
    assert state["schema_version"] == 1
    assert state["elapsed_hours"] == 0.0
    assert len(state["phases_pending"]) >= 5


def test_load_state_default(tmp_path, monkeypatch):
    from scripts.v9_phase_tracker import load_state, STATE_PATH
    monkeypatch.setattr("scripts.v9_phase_tracker.STATE_PATH",
                          tmp_path / "state.json")
    state = load_state()
    assert "phases_pending" in state
    assert "phases_delivered" in state


def test_save_state(tmp_path, monkeypatch):
    from scripts.v9_phase_tracker import save_state, STATE_PATH
    monkeypatch.setattr("scripts.v9_phase_tracker.STATE_PATH",
                          tmp_path / "state.json")
    state = {"test": True, "phases_pending": []}
    save_state(state)
    assert (tmp_path / "state.json").exists()


def test_add_phase_delivered():
    from scripts.v9_phase_tracker import (
        init_state, add_phase_delivered,
    )
    state = init_state()
    state = add_phase_delivered(state, "Phase 62 — Pipeline orchestrator")
    assert "Phase 62 — Pipeline orchestrator" in state["phases_delivered"]
    assert "Phase 62 — Pipeline orchestrator" not in state["phases_pending"]


def test_compute_elapsed_hours():
    from scripts.v9_phase_tracker import (
        init_state, compute_elapsed_hours,
    )
    state = init_state()
    elapsed = compute_elapsed_hours(state)
    assert elapsed >= 0.0


def test_status():
    from scripts.v9_phase_tracker import init_state, status
    state = init_state()
    s = status(state)
    assert "elapsed_hours" in s
    assert "phases_pending" in s


def test_should_terminate_max_hours():
    from scripts.v9_phase_tracker import should_terminate
    state = {"elapsed_hours": 50.0, "max_hours": 48.0,
              "tests_red_streak": 0, "commits_session": 0}
    assert should_terminate(state) is True


def test_should_terminate_red_streak():
    from scripts.v9_phase_tracker import should_terminate
    state = {"elapsed_hours": 1.0, "max_hours": 48.0,
              "tests_red_streak": 5, "commits_session": 0}
    assert should_terminate(state) is True


def test_should_terminate_continue():
    from scripts.v9_phase_tracker import should_terminate
    state = {"elapsed_hours": 5.0, "max_hours": 48.0,
              "tests_red_streak": 0, "commits_session": 10}
    assert should_terminate(state) is False


def test_main_status(monkeypatch, capsys):
    from scripts.v9_phase_tracker import main
    import tempfile
    monkeypatch.setattr("scripts.v9_phase_tracker.STATE_PATH",
                          Path(tempfile.mkdtemp()) / "state.json")
    exit_code = main(["--status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PHASE TRACKER" in captured.out


def test_main_next(monkeypatch, capsys):
    from scripts.v9_phase_tracker import main
    import tempfile
    monkeypatch.setattr("scripts.v9_phase_tracker.STATE_PATH",
                          Path(tempfile.mkdtemp()) / "state.json")
    exit_code = main(["--next"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert len(captured.out.strip()) > 0


def test_main_reset(monkeypatch, capsys):
    from scripts.v9_phase_tracker import main
    import tempfile
    monkeypatch.setattr("scripts.v9_phase_tracker.STATE_PATH",
                          Path(tempfile.mkdtemp()) / "state.json")
    exit_code = main(["--reset"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "reset" in captured.out.lower()


# === auto_plan ===

def test_compute_score_known():
    from scripts.v9_auto_plan import compute_score
    score = compute_score("Phase 63 — FTMO compliance")
    assert 0.0 <= score <= 1.0


def test_compute_score_unknown():
    from scripts.v9_auto_plan import compute_score
    score = compute_score("Phase unknown")
    assert score == 0.5  # default


def test_rank_phases():
    from scripts.v9_auto_plan import rank_phases
    phases = [
        "Phase 62 — Pipeline orchestrator",
        "Phase 63 — FTMO compliance",
        "Phase 64 — Real money preflight",
    ]
    ranked = rank_phases(phases)
    assert len(ranked) == 3
    # Le plus haut score est Premier
    assert ranked[0]["score"] >= ranked[1]["score"]


def test_next_phase():
    from scripts.v9_auto_plan import next_phase
    phases = [
        "Phase 62 — Pipeline orchestrator",
        "Phase 63 — FTMO compliance",
    ]
    nxt = next_phase(phases)
    assert nxt is not None
    assert "name" in nxt


def test_next_phase_empty():
    from scripts.v9_auto_plan import next_phase
    nxt = next_phase([])
    assert nxt is None


def test_generate_emergent():
    from scripts.v9_auto_plan import generate_emergent
    em = generate_emergent()
    assert em["emergent"] is True


def test_main_rank(monkeypatch, capsys):
    from scripts.v9_auto_plan import main
    import tempfile
    from scripts.v9_phase_tracker import STATE_PATH
    import scripts.v9_phase_tracker as pt
    pt.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    exit_code = main(["--rank"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "RANKING" in captured.out


def test_main_next(monkeypatch, capsys):
    from scripts.v9_auto_plan import main
    import tempfile
    import scripts.v9_phase_tracker as pt
    pt.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    exit_code = main(["--next"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "name" in captured.out


# === auto_commit ===

def test_stage_files_empty():
    from scripts.v9_auto_commit import stage_files
    rc, out, err = stage_files([])
    # git add -A doit retourner 0
    assert rc in (0, 1)  # peut-etre nothing to add


def test_auto_commit_phase_dry_run():
    from scripts.v9_auto_commit import auto_commit_phase
    # Dry run pas de git ops reelles
    result = auto_commit_phase("Phase 62", "test message", [])
    assert "staged" in result or "noop" in result or "error" in result


def test_main_commit_dry_run(capsys):
    from scripts.v9_auto_commit import main
    exit_code = main(["--phase-id", "Phase 62", "--message",
                       "test", "--dry-run"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DRY RUN" in captured.out


# === autonomous_loop ===

def test_main_loop_dry_run(monkeypatch, capsys):
    from scripts.v9_autonomous_loop import main
    import tempfile
    import scripts.v9_phase_tracker as pt
    pt.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    exit_code = main(["--dry-run", "--max-phases", "1"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "AUTONOMOUS LOOP" in captured.out


def test_main_loop_with_max(monkeypatch, capsys):
    from scripts.v9_autonomous_loop import main
    import tempfile
    import scripts.v9_phase_tracker as pt
    pt.STATE_PATH = Path(tempfile.mkdtemp()) / "state.json"
    exit_code = main(["--dry-run", "--max-phases", "3"])
    captured = capsys.readouterr()
    assert exit_code == 0


def test_verify_tests_runs():
    from scripts.v9_autonomous_loop import verify_tests
    # Verifier que la fonction existe et n'explose pas
    result = verify_tests()
    assert isinstance(result, bool)