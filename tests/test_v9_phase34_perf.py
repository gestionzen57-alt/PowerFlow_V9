"""tests/test_v9_phase34_perf.py — Phase 34 motion CEO 48h.

Tests pour v9_perf_profiler.
"""
import pytest
import sqlite3
import tempfile
from pathlib import Path


def test_time_function():
    """time_function retourne tuple (elapsed, result)."""
    from scripts.v9_perf_profiler import time_function
    elapsed, result = time_function(lambda: sum(range(100)), )
    assert elapsed >= 0
    assert result == sum(range(100))


def test_benchmark_query_db_missing():
    """benchmark_query sur DB absente → error."""
    from scripts.v9_perf_profiler import benchmark_query
    res = benchmark_query("/nonexistent/path.db", "SELECT 1", "test")
    assert res["error"] == "db_missing"


def test_benchmark_query_with_db():
    """benchmark_query calcule temps median."""
    from scripts.v9_perf_profiler import benchmark_query
    db = Path(tempfile.mkdtemp()) / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        for i in range(100):
            conn.execute("INSERT INTO t VALUES (?)", (i,))
        conn.commit()
    res = benchmark_query(db, "SELECT * FROM t", "test", n_runs=5)
    assert "median_ms" in res
    assert res["median_ms"] >= 0


def test_benchmark_query_invalid_sql():
    """benchmark_query sur SQL invalide → error."""
    from scripts.v9_perf_profiler import benchmark_query
    db = Path(tempfile.mkdtemp()) / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
    res = benchmark_query(db, "SELECT * FROM nonexistent", "test")
    assert "error" in res


def test_profile_module_invalid():
    """profile_module sur module invalide → error."""
    from scripts.v9_perf_profiler import profile_module
    res = profile_module("nonexistent.module", "fn")
    assert "error" in res


def test_profile_module_valid():
    """profile_module sur module valide retourne stats."""
    from scripts.v9_perf_profiler import profile_module
    import tempfile
    from pathlib import Path
    # Creer un fichier temporaire et appeler fix_missing_docstring(script)
    tmp_script = Path(tempfile.mkdtemp()) / "v9_x.py"
    tmp_script.write_text("x = 1\n")
    res = profile_module("scripts.v9_self_improving_loop",
                          "fix_missing_docstring", tmp_script)
    assert "stats" in res


def test_run_benchmarks_db_missing():
    """run_benchmarks sur DB absente → liste avec errors."""
    from scripts.v9_perf_profiler import run_benchmarks
    results = run_benchmarks("/nonexistent/path.db")
    assert all("error" in r for r in results)


def test_main_runs(monkeypatch, capsys):
    """CLI main execute sans erreur."""
    from scripts.v9_perf_profiler import main
    import scripts.v9_perf_profiler as pp
    import tempfile
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("CREATE TABLE v9_paper_trades (id INTEGER, pips_net REAL)")
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    monkeypatch.setattr(pp, "REPORT_PATH", d / "perf.json")
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PERFORMANCE PROFILER" in captured.out