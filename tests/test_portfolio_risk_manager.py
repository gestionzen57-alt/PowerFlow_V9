"""test_portfolio_risk_manager.py — Tests pour core/v9/portfolio_risk_manager.py.

Vérifie que le risk management portfolio fonctionne :
- Exposition nette par devise
- Corrélation entre paires
- Portfolio heat
- Circuit breaker
- Max drawdown 24h
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.v9.portfolio_risk_manager import (
    PortfolioRiskManager,
    MAX_NET_EXPOSURE_PER_CURRENCY,
    MAX_CONSECUTIVE_LOSSES,
    CORRELATION_MATRIX,
)


def _make_prm(tmp_path: Path) -> PortfolioRiskManager:
    """Crée un PRM avec une DB vide (pas de circuit breaker ni drawdown)."""
    db = tmp_path / "prm_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            trade_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT,
            opened_at TEXT, closed_at TEXT, is_win INTEGER, pips_simulated REAL
        );
    """)
    conn.commit()
    conn.close()
    return PortfolioRiskManager(db_path=db)


def test_empty_portfolio_accepts_trade(tmp_path: Path):
    """Portfolio vide → accepte le trade."""
    prm = _make_prm(tmp_path)
    go, reason, sizing = prm.evaluate_portfolio([], {"symbol": "GBPUSD", "direction": "haussiere"})
    assert go is True
    assert reason is None
    assert sizing == 1.0


def test_net_exposure_blocks_excess(tmp_path: Path):
    """Trop de trades short USD → bloqué."""
    prm = _make_prm(tmp_path)
    open_trades = [
        {"symbol": "GBPUSD", "direction": "baissiere", "risk_amount": 100},
        {"symbol": "EURUSD", "direction": "baissiere", "risk_amount": 100},
        {"symbol": "USDJPY", "direction": "baissiere", "risk_amount": 100},
    ]
    new_trade = {"symbol": "USDCHF", "direction": "baissiere", "risk_amount": 100}
    go, reason, sizing = prm.evaluate_portfolio(open_trades, new_trade)
    assert go is False
    assert "net_exposure" in reason


def test_net_exposure_allows_balanced(tmp_path: Path):
    """2 short + 1 long = exposition nette 1 → accepté."""
    prm = _make_prm(tmp_path)
    open_trades = [
        {"symbol": "GBPUSD", "direction": "baissiere", "risk_amount": 100},
        {"symbol": "EURUSD", "direction": "baissiere", "risk_amount": 100},
        {"symbol": "USDJPY", "direction": "haussiere", "risk_amount": 100},
    ]
    new_trade = {"symbol": "USDCHF", "direction": "haussiere", "risk_amount": 100}
    go, reason, sizing = prm.evaluate_portfolio(open_trades, new_trade)
    assert go is True


def test_correlation_reduces_sizing(tmp_path: Path):
    """Trade corrélé avec un trade ouvert → sizing réduit."""
    prm = _make_prm(tmp_path)
    open_trades = [
        {"symbol": "GBPUSD", "direction": "haussiere", "risk_amount": 100},
    ]
    new_trade = {"symbol": "EURUSD", "direction": "haussiere", "risk_amount": 100}
    go, reason, sizing = prm.evaluate_portfolio(open_trades, new_trade)
    assert go is True
    assert sizing < 1.0


def test_correlation_opposite_direction_no_reduction(tmp_path: Path):
    """Trade corrélé mais direction opposée (hedge) → pas de réduction."""
    prm = _make_prm(tmp_path)
    open_trades = [
        {"symbol": "GBPUSD", "direction": "haussiere", "risk_amount": 100},
    ]
    new_trade = {"symbol": "EURUSD", "direction": "baissiere", "risk_amount": 100}
    go, reason, sizing = prm.evaluate_portfolio(open_trades, new_trade)
    assert go is True
    assert sizing == 1.0


def test_portfolio_heat_blocks_excess(tmp_path: Path):
    """Risque total > 6% du capital → bloqué."""
    prm = _make_prm(tmp_path)
    open_trades = [
        {"symbol": "GBPUSD", "direction": "haussiere", "risk_amount": 300},
        {"symbol": "EURUSD", "direction": "haussiere", "risk_amount": 300},
    ]
    new_trade = {
        "symbol": "USDJPY", "direction": "haussiere",
        "risk_amount": 200, "capital": 10000,
    }
    go, reason, sizing = prm.evaluate_portfolio(open_trades, new_trade)
    assert go is False
    assert "portfolio_heat" in reason


def test_circuit_breaker(tmp_path: Path):
    """5 pertes consécutives → circuit breaker."""
    db = tmp_path / "cb_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            trade_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT,
            opened_at TEXT, closed_at TEXT, is_win INTEGER, pips_simulated REAL
        );
    """)
    now = datetime.now(timezone.utc).isoformat()
    # 5 pertes consécutives récentes
    for i in range(5):
        conn.execute(
            "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, 0, -15.0)",
            (f"t{i}", f"s{i}", "haussiere", now, now, ),
        )
    conn.commit()
    conn.close()

    prm = PortfolioRiskManager(db_path=db)
    result = prm._check_circuit_breaker()
    assert result is not None
    assert "circuit_breaker" in result


def test_no_circuit_breaker_with_wins(tmp_path: Path):
    """Pas de circuit breaker si des wins récentes."""
    db = tmp_path / "cb_ok.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            trade_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT,
            opened_at TEXT, closed_at TEXT, is_win INTEGER, pips_simulated REAL
        );
    """)
    now = datetime.now(timezone.utc).isoformat()
    # 3 pertes puis 2 wins
    for i in range(3):
        conn.execute(
            "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, 0, -15.0)",
            (f"t{i}", f"s{i}", "haussiere", now, now),
        )
    for i in range(3, 5):
        conn.execute(
            "INSERT INTO paper_trades VALUES (?, ?, ?, ?, ?, 1, 8.0)",
            (f"t{i}", f"s{i}", "haussiere", now, now),
        )
    conn.commit()
    conn.close()

    prm = PortfolioRiskManager(db_path=db)
    result = prm._check_circuit_breaker()
    assert result is None  # pas de circuit breaker


def test_get_portfolio_stats(tmp_path: Path):
    """get_portfolio_stats retourne les bonnes métriques."""
    db = tmp_path / "stats_test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            trade_id TEXT PRIMARY KEY, snapshot_id TEXT, direction TEXT,
            opened_at TEXT, closed_at TEXT, is_win INTEGER, pips_simulated REAL
        );
    """)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO paper_trades VALUES ('t1', 's1', 'haussiere', ?, ?, 1, 8.0)", (now, now))
    conn.execute("INSERT INTO paper_trades VALUES ('t2', 's2', 'baissiere', ?, ?, 0, -15.0)", (now, now))
    conn.execute("INSERT INTO paper_trades VALUES ('t3', 's3', 'haussiere', ?, NULL, NULL, NULL)", (now,))
    conn.commit()
    conn.close()

    prm = PortfolioRiskManager(db_path=db)
    stats = prm.get_portfolio_stats()
    assert stats["open_trades"] == 1
    assert stats["total_closed"] == 2
    assert stats["wins"] == 1


def test_never_crashes_on_empty_db(tmp_path: Path):
    """DB vide → pas de crash, retourne go=True."""
    db = tmp_path / "empty.db"
    db.touch()
    prm = PortfolioRiskManager(db_path=db)
    go, reason, sizing = prm.evaluate_portfolio([], {"symbol": "GBPUSD", "direction": "haussiere"})
    assert go is True