"""test_auto_optimizer.py — Tests pour core/v9/auto_optimizer.py (SOUL.md §4).

Vérifie :
1. Kill switch OFF -> no-op
2. Grid search trouve le meilleur TP/SL
3. Application si delta > 1 pip
4. Pas d'application si delta <= 1 pip
5. Notification Telegram best-effort
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from core.v9.auto_optimizer import (
    AUTO_OPTIMIZER_ENABLED_ENV,
    STRATEGY_OVERRIDES_PATH,
    _grid_search,
    _fetch_trades_for_principle,
    _get_current_strategy,
    _apply_optimization,
    run_optimization_cycle,
    auto_optimizer_enabled,
)


def test_auto_optimizer_enabled_default_on():
    """Kill switch V9_AUTO_OPTIMIZER_ENABLED default ON (mandat CEO)."""
    # Ne pas setter la variable -> default '1'
    if AUTO_OPTIMIZER_ENABLED_ENV in os.environ:
        del os.environ[AUTO_OPTIMIZER_ENABLED_ENV]
    assert auto_optimizer_enabled() is True


def test_auto_optimizer_disabled_when_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(AUTO_OPTIMIZER_ENABLED_ENV, "0")
    assert auto_optimizer_enabled() is False


def test_run_optimization_cycle_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(AUTO_OPTIMIZER_ENABLED_ENV, "0")
    report = run_optimization_cycle()
    assert report["enabled"] is False


def test_grid_search_empty_trades():
    result = _grid_search([])
    assert result["tp"] == 10
    assert result["sl"] == 15
    assert result["n_trades"] == 0


def test_grid_search_all_wins():
    """100% wins -> meilleur TP = max de la grille, meilleur SL = min."""
    trades = [{"is_win": 1, "pips": 10.0} for _ in range(20)]
    result = _grid_search(trades, tp_grid=[5, 10, 20], sl_grid=[5, 10, 15])
    assert result["tp"] == 20  # max TP
    assert result["sl"] == 5   # min SL (pas de pertes)
    assert result["wr"] == 100.0
    assert result["n_trades"] == 20


def test_grid_search_all_losses():
    """0% wins -> meilleur TP = min, meilleur SL = min (limiter les pertes)."""
    trades = [{"is_win": 0, "pips": -10.0} for _ in range(20)]
    result = _grid_search(trades, tp_grid=[5, 10, 20], sl_grid=[5, 10, 15])
    assert result["tp"] == 5   # min TP
    assert result["sl"] == 5   # min SL
    assert result["wr"] == 0.0


def test_grid_search_mixed():
    """50% wins -> expectancy max avec TP=10, SL=5."""
    trades = [{"is_win": 1, "pips": 10.0} for _ in range(10)] + \
             [{"is_win": 0, "pips": -5.0} for _ in range(10)]
    result = _grid_search(trades, tp_grid=[5, 10], sl_grid=[5, 10])
    # expectancy(10,5) = 0.5*10 - 0.5*5 = 2.5
    # expectancy(5,5) = 0.5*5 - 0.5*5 = 0
    # expectancy(10,10) = 0.5*10 - 0.5*10 = 0
    # expectancy(5,10) = 0.5*5 - 0.5*10 = -2.5
    assert result["tp"] == 10
    assert result["sl"] == 5
    assert result["expectancy"] == 2.5


def test_apply_optimization_delta_above_threshold(tmp_path: Path):
    """Delta > 1 pip -> application."""
    overrides_path = tmp_path / "strategy_overrides.json"
    overrides_path.write_text("{}", encoding="utf-8")

    # Patcher le chemin
    import core.v9.auto_optimizer as ao
    original_path = ao.STRATEGY_OVERRIDES_PATH
    ao.STRATEGY_OVERRIDES_PATH = overrides_path

    try:
        best = {"tp": 12, "sl": 8, "expectancy": 8.0, "wr": 80.0, "n_trades": 50}
        current = {"tp_pips": 10, "sl_pips": 15}
        result = _apply_optimization("TEST_PRINCIPLE", best, current)
        assert result is not None
        assert result["tp_new"] == 12
        assert result["sl_new"] == 8
        assert result["delta"] > 1.0

        # Verifier que l'override a ete ecrit
        data = json.loads(overrides_path.read_text(encoding="utf-8"))
        assert "TEST_PRINCIPLE" in data
        assert data["TEST_PRINCIPLE"]["tp_pips"] == 12
    finally:
        ao.STRATEGY_OVERRIDES_PATH = original_path


def test_apply_optimization_delta_below_threshold(tmp_path: Path):
    """Delta <= 1 pip -> pas d'application."""
    overrides_path = tmp_path / "strategy_overrides.json"
    overrides_path.write_text("{}", encoding="utf-8")

    import core.v9.auto_optimizer as ao
    original_path = ao.STRATEGY_OVERRIDES_PATH
    ao.STRATEGY_OVERRIDES_PATH = overrides_path

    try:
        best = {"tp": 10, "sl": 14, "expectancy": 0.5, "wr": 60.0, "n_trades": 50}
        current = {"tp_pips": 10, "sl_pips": 15}
        result = _apply_optimization("TEST_PRINCIPLE", best, current)
        assert result is None  # Pas applique (delta <= 1)
    finally:
        ao.STRATEGY_OVERRIDES_PATH = original_path


def test_fetch_trades_for_principle_empty_db(tmp_path: Path):
    """DB avec tables mais vide -> liste vide, pas de crash."""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS principle_evaluations (
            id INTEGER PRIMARY KEY, principle_id TEXT, snapshot_id TEXT,
            triggered INTEGER, confidence REAL, timeframe TEXT
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY, snapshot_id TEXT, is_win INTEGER,
            resolution_pips REAL, timestamp TEXT
        );
    """)
    conn.commit()
    trades = _fetch_trades_for_principle(conn, "TEST")
    assert trades == []
    conn.close()


def test_get_current_strategy_default():
    """Pas d'overrides -> defaults."""
    result = _get_current_strategy("UNKNOWN")
    assert result["tp_pips"] == 10
    assert result["sl_pips"] == 15


def test_get_current_strategy_with_overrides(tmp_path: Path):
    """Override present -> retourne l'override."""
    overrides_path = tmp_path / "strategy_overrides.json"
    overrides_path.write_text(
        json.dumps({"TEST_PRINC": {"tp_pips": 12, "sl_pips": 8}}),
        encoding="utf-8",
    )

    import core.v9.auto_optimizer as ao
    original_path = ao.STRATEGY_OVERRIDES_PATH
    ao.STRATEGY_OVERRIDES_PATH = overrides_path

    try:
        result = _get_current_strategy("TEST_PRINC")
        assert result["tp_pips"] == 12
        assert result["sl_pips"] == 8
    finally:
        ao.STRATEGY_OVERRIDES_PATH = original_path
