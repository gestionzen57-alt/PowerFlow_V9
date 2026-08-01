"""tests/test_v9_phase46.py — Phase 46 motion CEO 48h.

Tests pour v9_meta_learning.
"""
import pytest


def test_evaluate_hyperparams_empty():
    from scripts.v9_meta_learning import evaluate_hyperparams
    res = evaluate_hyperparams([])
    assert res["score"] == 0.0


def test_evaluate_hyperparams_basic():
    from scripts.v9_meta_learning import evaluate_hyperparams
    pips = [25.0] * 9 + [-8.0]  # 90% WR
    res = evaluate_hyperparams(pips, tp_atr_mult=2.5, sl_atr_mult=0.8)
    assert res["wr"] == 0.9
    assert res["n_trades"] == 10


def test_evaluate_hyperparams_bad_rr():
    from scripts.v9_meta_learning import evaluate_hyperparams
    pips = [25.0, -8.0, 30.0]
    res = evaluate_hyperparams(pips, tp_atr_mult=1.0, sl_atr_mult=2.0)
    # Bad RR → score * 0.5
    assert res["score"] < 0.5


def test_grid_search_empty():
    from scripts.v9_meta_learning import grid_search
    res = grid_search([], {})
    assert res["n_evals"] == 0
    assert res["best_score"] == -1.0


def test_grid_search_basic():
    from scripts.v9_meta_learning import grid_search
    pips = [25.0] * 9 + [-8.0]
    param_grid = {
        "tp_atr_mult": [2.0, 3.0],
        "sl_atr_mult": [0.8],
        "filter_threshold": [0.5],
        "position_factor": [1.0],
    }
    res = grid_search(pips, param_grid)
    # 2 * 1 * 1 * 1 = 2 evaluations
    assert res["n_evals"] == 2
    assert "tp_atr_mult" in res["best_params"]


def test_bayesian_optimization_empty():
    from scripts.v9_meta_learning import bayesian_optimization
    res = bayesian_optimization([], n_iterations=10)
    assert res["best_score"] == 0.0


def test_bayesian_optimization_basic():
    from scripts.v9_meta_learning import bayesian_optimization
    pips = [25.0] * 8 + [-8.0] * 2  # 80% WR
    res = bayesian_optimization(pips, n_iterations=20, seed=42)
    assert res["n_evals"] == 20
    assert res["best_score"] > 0


def test_bayesian_optimization_improves():
    from scripts.v9_meta_learning import bayesian_optimization
    pips = [25.0] * 9 + [-8.0]
    res = bayesian_optimization(pips, n_iterations=50, seed=42)
    # Should find good hyperparams (RR > 2 + high WR)
    assert res["best_score"] > 0.3


def test_main_runs_no_data(monkeypatch, capsys):
    """CLI avec DB vide → no data."""
    from scripts.v9_meta_learning import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()  # file exists but empty
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--method", "bayesian", "--n-iter", "5"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Aucun trade ferme" in captured.out


def test_main_runs_with_data(monkeypatch, capsys):
    """CLI avec donnees."""
    from scripts.v9_meta_learning import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, closed_at TEXT, pips_net REAL
            )
        """)
        for p in [25.0] * 8 + [-8.0] * 2:
            conn.execute(
                "INSERT INTO v9_paper_trades VALUES (NULL, '2026-07-31', ?)",
                (p,),
            )
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    import scripts.v9_meta_learning as ml
    monkeypatch.setattr(ml, "REPORT_PATH", d / "report.json")
    exit_code = main(["--method", "bayesian", "--n-iter", "10"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Best score" in captured.out