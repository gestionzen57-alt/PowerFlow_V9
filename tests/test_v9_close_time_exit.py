"""tests/test_v9_close_time_exit.py — Phase 3 L3 force_close_aged_trades."""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "1")
    yield
    monkeypatch.delenv("V9_TIME_EXIT_ENABLED", raising=False)


@pytest.fixture
def tmp_db(tmp_path):
    """DB minimale avec table paper_trades pour tests L3."""
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "CREATE TABLE paper_trades ("
            "trade_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "opened_at TEXT, closed_at TEXT, "
            "is_win INTEGER, pips_simulated REAL)"
        )
        conn.commit()
    yield db


def _insert_open_trade(db, age_min):
    """Insère un trade ouvert depuis `age_min` minutes."""
    opened = (datetime.utcnow() - timedelta(minutes=age_min)).isoformat()
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT INTO paper_trades (opened_at, closed_at, is_win, pips_simulated) "
            "VALUES (?, NULL, 0, 0)",
            (opened,),
        )
        conn.commit()


def test_time_exit_enabled_default():
    """Kill switch V9_TIME_EXIT_ENABLED defaut ON."""
    from scripts.v9_close_time_exit import time_exit_enabled
    assert time_exit_enabled() is True


def test_force_close_aged_trades_closes_5min(tmp_db):
    """Trade ouvert >5min doit etre ferme (forced=1)."""
    from scripts.v9_close_time_exit import force_close_aged_trades
    _insert_open_trade(tmp_db, age_min=10)
    res = force_close_aged_trades(db_path=tmp_db)
    assert res["forced"] == 1
    assert res["skipped"] == 0
    assert res["artifact"] == 1
    # Verif DB
    with sqlite3.connect(str(tmp_db)) as conn:
        rows = conn.execute(
            "SELECT closed_at, is_win, pips_simulated FROM paper_trades"
        ).fetchall()
    assert rows[0][0] is not None  # closed_at pose
    assert rows[0][1] == 0  # is_win=0 (artefact)
    assert rows[0][2] == 0.0  # pips=0


def test_force_close_skips_young_trades(tmp_db):
    """Trade ouvert <5min doit etre laisse ouvert (skipped=1)."""
    from scripts.v9_close_time_exit import force_close_aged_trades
    _insert_open_trade(tmp_db, age_min=2)
    res = force_close_aged_trades(db_path=tmp_db)
    assert res["forced"] == 0
    assert res["skipped"] == 1


def test_force_close_multiple_mixed_ages(tmp_db):
    """Mix 3 aged + 2 young → forced=3 skipped=2."""
    from scripts.v9_close_time_exit import force_close_aged_trades
    for age in (1, 2, 6, 10, 15):
        _insert_open_trade(tmp_db, age_min=age)
    res = force_close_aged_trades(db_path=tmp_db)
    assert res["forced"] == 3
    assert res["skipped"] == 2


def test_force_close_no_trades_returns_zero(tmp_db):
    """DB vide → 0 forced, 0 skipped."""
    from scripts.v9_close_time_exit import force_close_aged_trades
    res = force_close_aged_trades(db_path=tmp_db)
    assert res["forced"] == 0
    assert res["skipped"] == 0


def test_force_close_missing_db_returns_zero(tmp_path):
    """DB absente → no-op, retourne zeros."""
    from scripts.v9_close_time_exit import force_close_aged_trades
    res = force_close_aged_trades(db_path=tmp_path / "absent.db")
    assert res["forced"] == 0


def test_kill_switch_off_returns_zero(tmp_db, monkeypatch):
    """V9_TIME_EXIT_ENABLED=0 → no-op."""
    from scripts.v9_close_time_exit import (
        force_close_aged_trades, time_exit_enabled,
    )
    monkeypatch.setenv("V9_TIME_EXIT_ENABLED", "0")
    assert time_exit_enabled() is False
    _insert_open_trade(tmp_db, age_min=60)
    res = force_close_aged_trades(db_path=tmp_db)
    assert res == {"forced": 0, "skipped": 0, "artifact": 0}