"""tests/test_v9_phase24.py — Phase 24 motion CEO autopilote.

Tests pour walk_forward_monte_carlo + expectancy_comparison + hurst_exponent.
"""
import pytest
import math


# === v9_walk_forward_monte_carlo ===

def test_get_paper_trades_chrono_db_missing(tmp_path):
    """get_paper_trades_chrono sur DB absente → []."""
    from scripts.v9_walk_forward_monte_carlo import get_paper_trades_chrono
    assert get_paper_trades_chrono(tmp_path / "absent.db") == []


def test_get_paper_trades_chrono_with_db(tmp_path):
    """get_paper_trades_chrono retourne liste ordonnee."""
    import sqlite3
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, opened_at TEXT, closed_at TEXT,
                pips_net REAL, direction TEXT
            )
        """)
        for i in range(10):
            conn.execute("""
                INSERT INTO v9_paper_trades
                VALUES (NULL, 'GBPUSD', ?, ?, 23.5, 'haussiere')
            """, (f"2026-07-{31 - i:02d}T11:00:00",
                  f"2026-07-{31 - i:02d}T11:30:00"))
        conn.commit()
    from scripts.v9_walk_forward_monte_carlo import get_paper_trades_chrono
    trades = get_paper_trades_chrono(db)
    assert len(trades) == 10
    assert all(t["symbol"] == "GBPUSD" for t in trades)


def test_walk_forward_insufficient_trades():
    """walk_forward_simulation avec <20 trades → error."""
    from scripts.v9_walk_forward_monte_carlo import walk_forward_simulation
    trades = [{"pips_net": 10.0}] * 5
    res = walk_forward_simulation(trades)
    assert "error" in res


def test_walk_forward_basic():
    """walk_forward_simulation split 70/30 et calcule IS/OOS."""
    from scripts.v9_walk_forward_monte_carlo import walk_forward_simulation
    trades = [{"pips_net": 23.5}] * 70 + [{"pips_net": -9.5}] * 30
    res = walk_forward_simulation(trades, train_ratio=0.7, seed=42)
    assert res["n_in_sample"] == 70
    assert res["n_out_sample"] == 30
    assert res["is_wr"] == 100.0
    assert res["oos_wr"] == 0.0
    assert res["is_expectancy"] == 23.5
    assert res["oos_expectancy"] == -9.5
    assert res["passed"] is False


def test_walk_forward_passed():
    """walk_forward OOS positive."""
    from scripts.v9_walk_forward_monte_carlo import walk_forward_simulation
    trades = [{"pips_net": 23.5}] * 80 + [{"pips_net": 10.0}] * 20
    res = walk_forward_simulation(trades, train_ratio=0.7, seed=42)
    assert res["passed"] is True


def test_walk_forward_monte_carlo_insufficient():
    """wfmc avec <20 trades → error."""
    from scripts.v9_walk_forward_monte_carlo import walk_forward_monte_carlo
    res = walk_forward_monte_carlo([{"pips_net": 10.0}] * 5)
    assert "error" in res


def test_walk_forward_monte_carlo_distribution():
    """wfmc genere distribution OOS expectancy."""
    from scripts.v9_walk_forward_monte_carlo import walk_forward_monte_carlo
    # 100 trades majoritairement positifs
    trades = [{"pips_net": 23.5}] * 80 + [{"pips_net": -9.5}] * 20
    res = walk_forward_monte_carlo(trades, n_sims=50, seed=42)
    assert res["n_simulations"] == 50
    assert res["p_oos_positive"] > 50  # majorite OOS > 0


def test_walk_forward_monte_carlo_robust_edge():
    """wfmc detecte edge robuste si 100% WR."""
    from scripts.v9_walk_forward_monte_carlo import walk_forward_monte_carlo
    trades = [{"pips_net": 23.5}] * 100
    res = walk_forward_monte_carlo(trades, n_sims=20, seed=42)
    assert res["p_oos_positive"] == 100.0
    assert res["oos_exp_p5"] > 0


def test_main_runs(monkeypatch, capsys):
    """CLI main execute sans erreur."""
    from scripts.v9_walk_forward_monte_carlo import main
    # Mock DB_PATH avec DB temporaire contenant 30 trades
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, opened_at TEXT, closed_at TEXT,
                pips_net REAL, direction TEXT
            )
        """)
        for i in range(30):
            conn.execute("""
                INSERT INTO v9_paper_trades
                VALUES (NULL, 'GBPUSD', '2026-07-31T11:00:00',
                  '2026-07-31T11:30:00', 23.5, 'haussiere')
            """)
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--n-sims", "50"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "WALK-FORWARD MONTE CARLO" in captured.out