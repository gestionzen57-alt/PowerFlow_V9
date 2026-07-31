"""tests/test_v9_phase41.py — Phase 41 motion CEO 48h.

Tests pour correlation_matrix + portfolio_optimizer + live_html_dashboard.
"""
import pytest
import sqlite3


# === v9_correlation_matrix ===

def test_get_pips_by_symbol_db_missing():
    from scripts.v9_correlation_matrix import _get_pips_by_symbol
    from pathlib import Path as _P
    assert _get_pips_by_symbol(_P("/nonexistent/path.db")) == {}


def test_pearson_basic():
    from scripts.v9_correlation_matrix import _pearson
    xs = [1.0, 2.0, 3.0, 4.0]
    ys = [2.0, 4.0, 6.0, 8.0]
    r = _pearson(xs, ys)
    assert r is not None
    assert abs(r - 1.0) < 0.001  # perfectly correlated


def test_pearson_anticorrelated():
    from scripts.v9_correlation_matrix import _pearson
    xs = [1.0, 2.0, 3.0, 4.0]
    ys = [4.0, 3.0, 2.0, 1.0]
    r = _pearson(xs, ys)
    assert r is not None
    assert r < -0.9  # anti-correlated


def test_pearson_too_short():
    from scripts.v9_correlation_matrix import _pearson
    assert _pearson([1.0], [1.0]) is None


def test_compute_correlation_matrix_db_missing():
    from scripts.v9_correlation_matrix import compute_correlation_matrix
    from pathlib import Path as _P
    result = compute_correlation_matrix(_P("/nonexistent/path.db"))
    assert result["symbols"] == []


def test_compute_correlation_matrix_with_data(tmp_path):
    from scripts.v9_correlation_matrix import compute_correlation_matrix
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, symbol TEXT, pips_net REAL, closed_at TEXT
            )
        """)
        for s, p in [("GBPUSD", 25), ("GBPUSD", -8),
                      ("EURUSD", 15), ("EURUSD", -10),
                      ("USDJPY", 20), ("USDJPY", -5)]:
            conn.execute(
                "INSERT INTO v9_paper_trades VALUES (NULL, ?, ?, '2026-07-31')",
                (s, p),
            )
        conn.commit()
    result = compute_correlation_matrix(db)
    assert "GBPUSD" in result["symbols"]
    assert "EURUSD" in result["symbols"]


# === v9_portfolio_optimizer ===

def test_sharpe_like_basic():
    from scripts.v9_portfolio_optimizer import _sharpe_like
    pips = [25.0, -8.0, 30.0, -10.0, 20.0]
    s = _sharpe_like(pips)
    assert s != 0


def test_sharpe_like_too_short():
    from scripts.v9_portfolio_optimizer import _sharpe_like
    assert _sharpe_like([25.0]) == 0.0
    assert _sharpe_like([]) == 0.0


def test_portfolio_sharpe_empty():
    from scripts.v9_portfolio_optimizer import _portfolio_sharpe
    assert _portfolio_sharpe([], []) == 0.0


def test_portfolio_sharpe_basic():
    from scripts.v9_portfolio_optimizer import _portfolio_sharpe
    rm = [[1.0, 2.0, 3.0], [2.0, 4.0, 6.0]]
    w = [0.5, 0.5]
    s = _portfolio_sharpe(w, rm)
    assert s > 0


def test_optimize_weights_no_data():
    from scripts.v9_portfolio_optimizer import optimize_weights
    result = optimize_weights([], n_iterations=100)
    assert result["weights"] == []


def test_optimize_weights_with_data():
    from scripts.v9_portfolio_optimizer import optimize_weights
    pips = [[1.0, 2.0, 3.0, 4.0, 5.0], [2.0, 4.0, 6.0, 8.0, 10.0]]
    result = optimize_weights(pips, n_iterations=100, seed=42)
    assert len(result["weights"]) == 2
    assert result["sharpe"] >= 0


# === v9_live_html_dashboard ===

def test_safe_run():
    from scripts.v9_live_html_dashboard import _safe_run
    # echo doit retourner 'hello'
    out = _safe_run(["echo", "hello"], timeout=5)
    assert "hello" in out


def test_safe_run_timeout():
    from scripts.v9_live_html_dashboard import _safe_run
    # sleep 5 avec timeout 1 → doit retourner ""
    out = _safe_run(["sleep", "5"], timeout=1)
    assert out == ""


def test_git_head():
    from scripts.v9_live_html_dashboard import _git_head
    head = _git_head()
    assert isinstance(head, str)


def test_get_paper_summary_db_missing():
    from scripts.v9_live_html_dashboard import _get_paper_summary
    from pathlib import Path as _P
    s = _get_paper_summary(_P("/nonexistent/path.db"))
    assert s["n_open"] == 0
    assert s["n_closed"] == 0


def test_get_paper_summary_with_db(tmp_path):
    from scripts.v9_live_html_dashboard import _get_paper_summary
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, closed_at TEXT
            )
        """)
        for closed in [None, None, "2026-07-31", None, "2026-07-31"]:
            conn.execute(
                "INSERT INTO v9_paper_trades VALUES (NULL, ?)",
                (closed,),
            )
        conn.commit()
    s = _get_paper_summary(db)
    assert s["n_open"] == 3
    assert s["n_closed"] == 2


def test_generate_html(tmp_path, monkeypatch):
    from scripts.v9_live_html_dashboard import generate_html
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, closed_at TEXT
            )
        """)
        conn.commit()
    out = tmp_path / "dashboard.html"
    result = generate_html(db, out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "POWERFLOW V9" in content
    assert "auto-refresh" in content.lower() or "refresh" in content.lower()


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_live_html_dashboard import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER, closed_at TEXT
            )
        """)
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    import scripts.v9_live_html_dashboard as lhd
    monkeypatch.setattr(lhd, "HTML_PATH", d / "dashboard.html")
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "HTML DASHBOARD" in captured.out