"""Tests pytest — core/v9/v9_monte_carlo.py.

Couvre : constructeur (validation), simulate/stress_test avec DB
temporaire, scénarios vides, percentile, R6 défensif.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9.v9_monte_carlo import (
    MonteCarloResult,
    MonteCarloSimulator,
    STRESS_SCENARIOS,
    main,
)

# ── Schéma minimal reproduisant paper_trades + forces_snapshots ─────


SCHEMA_SQL = """
CREATE TABLE forces_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    symbol TEXT,
    timeframe TEXT,
    bar_time INTEGER
);
CREATE TABLE paper_trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT,
    direction TEXT,
    confiance REAL,
    principes_source TEXT,
    opened_at TEXT,
    closed_at TEXT,
    pips_simulated REAL,
    is_win INTEGER,
    risk_go_context TEXT
);
"""


def _populate_db(
    path: Path,
    symbol: str,
    pips_values: list[float],
    n_snapshots: int = 1,
) -> None:
    """Insère n trades (1 par snapshot_id unique)."""
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA_SQL)
    for i, pips in enumerate(pips_values):
        snap = f"v9-{symbol}-M15-{i:09d}"
        conn.execute(
            "INSERT INTO forces_snapshots (snapshot_id, symbol, timeframe, bar_time) "
            "VALUES (?, ?, 'M15', ?)",
            (snap, symbol, i),
        )
        conn.execute(
            "INSERT INTO paper_trades "
            "(snapshot_id, direction, confiance, principes_source, opened_at, "
            " closed_at, pips_simulated, is_win, risk_go_context) "
            "VALUES (?, 'LONG', 0.8, '[\"P1\"]', '2026-01-01', '2026-01-01', ?, ?, '{}')",
            (snap, pips, 1 if pips > 0 else 0),
        )
    conn.commit()
    conn.close()


# ── Tests ──────────────────────────────────────────────────────────


def test_constructor_validation():
    with pytest.raises(ValueError):
        MonteCarloSimulator(n_simulations=0)
    with pytest.raises(ValueError):
        MonteCarloSimulator(lookback_trades=0)
    sim = MonteCarloSimulator(n_simulations=10, lookback_trades=100)
    assert sim.n_simulations == 10
    assert sim.lookback_trades == 100


def test_simulate_basic_distribution(tmp_path: Path):
    """Distribution mixte (gains/pertes) — vérifie le calcul."""
    db = tmp_path / "test.db"
    # 60 trades : 50 wins à +5 pips, 10 losses à -10 pips (WR 83%)
    pips = [5.0] * 50 + [-10.0] * 10
    _populate_db(db, "GBPUSD", pips)

    sim = MonteCarloSimulator(n_simulations=200, lookback_trades=1000, seed=42, db_path=db)
    r = sim.simulate(symbol="GBPUSD", n_trades=100)

    assert isinstance(r, MonteCarloResult)
    assert r.n_simulations == 200
    assert r.sample_size_source == 60
    # Esperance par trade = (50*5 - 10*10) / 60 = (250-100)/60 ≈ 2.5 pips/trade
    # Sur 100 trades ~ 250 pips en moyenne
    assert 200 < r.mean_pips < 300
    assert r.percentile_5 < r.percentile_50 < r.percentile_95
    assert r.proba_positive == 100.0  # distribution fortement positive


def test_simulate_empty_distribution(tmp_path: Path):
    """Aucune data — retourne un résultat vide sans lever."""
    db = tmp_path / "empty.db"
    _populate_db(db, "EURUSD", [])  # 0 trades

    sim = MonteCarloSimulator(n_simulations=10, db_path=db)
    r = sim.simulate(symbol="EURUSD", n_trades=10)
    assert r.n_simulations == 0
    assert r.mean_pips == 0.0
    assert r.scenario == "empty"


def test_simulate_unknown_symbol(tmp_path: Path):
    """Symbole inexistant → résultat vide (R6)."""
    db = tmp_path / "test.db"
    _populate_db(db, "GBPUSD", [5.0, -3.0, 8.0])

    sim = MonteCarloSimulator(n_simulations=5, db_path=db)
    r = sim.simulate(symbol="UNKNOWN", n_trades=10)
    assert r.n_simulations == 0


def test_stress_test_scenarios(tmp_path: Path):
    """Les scénarios amplifient les pertes (mean plus bas, DD plus haut)."""
    db = tmp_path / "test.db"
    pips = [5.0] * 40 + [-10.0] * 10  # WR 80%
    _populate_db(db, "GBPUSD", pips)

    sim = MonteCarloSimulator(n_simulations=200, seed=7, db_path=db)

    r_normal = sim.stress_test(scenario="normal", symbol="GBPUSD", n_trades=100)
    r_black = sim.stress_test(scenario="black_swan", symbol="GBPUSD", n_trades=100)
    r_crisis = sim.stress_test(scenario="crisis", symbol="GBPUSD", n_trades=100)

    assert r_normal.scenario == "normal"
    assert r_black.scenario == "black_swan"
    assert r_crisis.scenario == "crisis"
    # black_swan et crisis doivent dégrader le mean_pips vs normal
    assert r_normal.mean_pips > r_black.mean_pips > r_crisis.mean_pips
    # DD doit augmenter
    assert r_normal.max_drawdown_p95 <= r_black.max_drawdown_p95
    assert r_black.max_drawdown_p95 <= r_crisis.max_drawdown_p95


def test_stress_test_unknown_scenario_fallback(tmp_path: Path):
    """Scénario inconnu → fallback normal (R6)."""
    db = tmp_path / "test.db"
    _populate_db(db, "GBPUSD", [5.0, -3.0, 8.0])

    sim = MonteCarloSimulator(n_simulations=5, db_path=db)
    r = sim.stress_test(scenario="meteor_impact", symbol="GBPUSD", n_trades=10)
    assert r.scenario == "normal"


def test_percentile_helper():
    """Percentile basique (méthode linéaire)."""
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert MonteCarloSimulator._percentile(vals, 50) == 3.0
    assert MonteCarloSimulator._percentile(vals, 0) == 1.0
    assert MonteCarloSimulator._percentile(vals, 100) == 5.0
    assert MonteCarloSimulator._percentile([], 50) == 0.0


def test_scenarios_dict():
    """Les scénarios définis couvrent les clés du brief."""
    assert "normal" in STRESS_SCENARIOS
    assert "black_swan" in STRESS_SCENARIOS
    assert "crisis" in STRESS_SCENARIOS
    assert STRESS_SCENARIOS["black_swan"]["vol_mult"] >= 1.0
    assert STRESS_SCENARIOS["crisis"]["vol_mult"] > STRESS_SCENARIOS["black_swan"]["vol_mult"]


def test_result_to_dict():
    """MonteCarloResult sérialise en dict JSON-compatible."""
    r = MonteCarloResult(
        n_simulations=10,
        n_trades_per_sim=100,
        scenario="normal",
        mean_pips=10.0,
        std_pips=2.0,
        var_pips=4.0,
        percentile_5=6.0,
        percentile_50=10.0,
        percentile_95=14.0,
        max_drawdown_mean=5.0,
        max_drawdown_p95=10.0,
        sharpe_mean=1.5,
        sharpe_p5=1.0,
        proba_positive=80.0,
    )
    d = r.to_dict()
    assert d["n_simulations"] == 10
    assert d["scenario"] == "normal"
    assert "generated_at" in d


def test_reproducibility_with_seed(tmp_path: Path):
    """Deux simulateurs avec le même seed produisent les mêmes résultats."""
    db = tmp_path / "test.db"
    _populate_db(db, "GBPUSD", [3.0, -5.0, 7.0, -2.0] * 25)

    r1 = MonteCarloSimulator(n_simulations=50, seed=123, db_path=db).simulate(
        symbol="GBPUSD", n_trades=50
    )
    r2 = MonteCarloSimulator(n_simulations=50, seed=123, db_path=db).simulate(
        symbol="GBPUSD", n_trades=50
    )
    assert r1.mean_pips == r2.mean_pips
    assert r1.std_pips == r2.std_pips


def test_main_cli_runs(tmp_path: Path, monkeypatch, capsys):
    """Le CLI --simulations 10 tourne sans erreur (mode custom sans filtre)."""
    import json

    # Test sur main() directement avec sys.argv stubé — pas de DB custom :
    # on s'attend à un résultat vide (sample_size=0) mais sans crash.
    monkeypatch.setattr("sys.argv", [
        "v9_monte_carlo.py",
        "--symbol", "ZZZ_NO_SUCH_SYMBOL",
        "--n", "20",
        "--simulations", "5",
        "--seed", "1",
    ])
    rc = main()
    out = capsys.readouterr().out
    assert rc == 0
    # Au moins un résultat sérialisé en JSON
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1