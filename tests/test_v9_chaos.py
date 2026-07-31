"""tests/test_v9_chaos.py — Phase 36 motion CEO 48h.

Tests pour v9_chaos_test.
"""
import pytest
import os
import sqlite3
import tempfile
from pathlib import Path


def test_chaos_corrupt_db_no_file(tmp_path):
    """chaos_corrupt_db sur fichier inexistant → False."""
    from scripts.v9_chaos_test import chaos_corrupt_db
    assert chaos_corrupt_db(tmp_path / "absent.db") is False


def test_chaos_corrupt_db_small(tmp_path):
    """chaos_corrupt_db sur petit fichier (< 100 bytes) → no-op mais True."""
    from scripts.v9_chaos_test import chaos_corrupt_db
    small = tmp_path / "small.db"
    small.write_bytes(b"x" * 50)
    # Pas de corruption reelle car trop petit, mais True (graceful)
    assert chaos_corrupt_db(small) is True


def test_chaos_corrupt_db_large(tmp_path):
    """chaos_corrupt_db sur gros fichier → True."""
    from scripts.v9_chaos_test import chaos_corrupt_db
    large = tmp_path / "large.db"
    large.write_bytes(b"x" * 1000)
    assert chaos_corrupt_db(large) is True


def test_chaos_missing_file_absent(tmp_path):
    """chaos_missing_file sur fichier absent → False."""
    from scripts.v9_chaos_test import chaos_missing_file
    assert chaos_missing_file(tmp_path / "absent.txt") is False


def test_chaos_missing_file_present(tmp_path):
    """chaos_missing_file sur fichier present → True + rename."""
    from scripts.v9_chaos_test import chaos_missing_file
    f = tmp_path / "test.txt"
    f.write_text("content")
    assert chaos_missing_file(f) is True
    assert not f.exists()
    assert f.with_suffix(".txt.chaos_backup").exists()


def test_chaos_recover_file(tmp_path):
    """chaos_recover_file restaure depuis backup."""
    from scripts.v9_chaos_test import chaos_missing_file, chaos_recover_file
    f = tmp_path / "test.txt"
    f.write_text("content")
    chaos_missing_file(f)
    assert chaos_recover_file(f) is True
    assert f.exists()


def test_chaos_kill_switch_random_no_env(monkeypatch, tmp_path):
    """chaos_kill_switch_random sans env → error."""
    from scripts.v9_chaos_test import chaos_kill_switch_random
    import scripts.v9_chaos_test as ct
    monkeypatch.setattr(ct, "_ROOT", tmp_path)
    res = chaos_kill_switch_random()
    assert res["error"] == "env_missing"


def test_chaos_kill_switch_random_with_env(monkeypatch, tmp_path):
    """chaos_kill_switch_random toggle 5 vars aleatoires."""
    from scripts.v9_chaos_test import chaos_kill_switch_random
    import scripts.v9_chaos_test as ct
    monkeypatch.setattr(ct, "_ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    env = tmp_path / "config" / "v9_kill_switches.env"
    env.write_text(
        "V9_A=1\nV9_B=0\nV9_C=1\nV9_D=0\nV9_E=1\nV9_F=0\nV9_G=1\n"
    )
    res = chaos_kill_switch_random()
    assert res["n_toggled"] >= 1


def test_chaos_slow_query_no_db():
    """chaos_slow_query sans DB → False."""
    from scripts.v9_chaos_test import chaos_slow_query
    from pathlib import Path as _P
    assert chaos_slow_query(_P("/nonexistent/path.db")) is False


def test_chaos_slow_query_with_db(tmp_path):
    """chaos_slow_query avec DB valide → True."""
    from scripts.v9_chaos_test import chaos_slow_query
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
    assert chaos_slow_query(db) is True


def test_run_chaos_suite_small(monkeypatch):
    """run_chaos_suite execute N iterations."""
    from scripts.v9_chaos_test import run_chaos_suite
    import scripts.v9_chaos_test as ct
    with tempfile.TemporaryDirectory() as d:
        import os
        monkeypatch.setattr(ct, "REPORT_PATH", Path(d) / "report.json")
        result = run_chaos_suite(n_iterations=3)
    assert result["n_iterations"] == 3
    assert len(result["results"]) == 3


def test_main_runs(monkeypatch, capsys):
    """CLI main execute sans erreur."""
    from scripts.v9_chaos_test import main
    with tempfile.TemporaryDirectory() as d:
        import scripts.v9_chaos_test as ct
        monkeypatch.setattr(ct, "REPORT_PATH", Path(d) / "report.json")
        exit_code = main(["--iterations", "3"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CHAOS TEST SUITE" in captured.out