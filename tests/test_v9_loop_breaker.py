"""test_v9_loop_breaker.py — Tests pour core/v9/v9_loop_breaker.py (Fix B).

Vérifie :
T1. Kill switch (V9_LOOP_BREAKER_ENABLED) — défaut OFF (R28 motion CEO explicite)
T2. check_loop() retourne allow si OFF
T3. _min_hold_seconds / _max_open_per_symbol / _window_minutes env
T4. check_loop() lit paper_trades correctement (lecture seule DB)
T5. check_loop() bloque si cooldown actif (< MIN_HOLD_BARS)
T6. check_loop() bloque si max_open_per_symbol atteint
T7. check_loop() bloque si densité suspecte (>10 trades dans fenêtre)
T8. R6 : DB absente → allow (fallback safe)
T9. R6 : DB corrompue → allow
T10. get_stats() diagnostic
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from core.v9.v9_loop_breaker import (
    DEFAULT_MAX_OPEN_TRADES_PER_SYMBOL,
    DEFAULT_MIN_HOLD_BARS,
    DEFAULT_LOOP_BREAKER_WINDOW_MINUTES,
    LOOP_BREAKER_ENABLED_ENV,
    MAX_OPEN_TRADES_PER_SYMBOL_ENV,
    MIN_HOLD_BARS_ENV,
    LoopDecision,
    _max_open_per_symbol,
    _min_hold_seconds,
    _window_minutes,
    check_loop,
    get_stats,
    loop_breaker_enabled,
)


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """DB v9_forces-like avec paper_trades + decisions."""
    from datetime import datetime, timezone, timedelta
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript("""
            CREATE TABLE decisions (
                decision_id TEXT PRIMARY KEY, snapshot_id TEXT,
                timestamp TEXT, symbol TEXT, timeframe TEXT,
                regime_type TEXT, direction TEXT,
                is_win INTEGER
            );
            CREATE TABLE paper_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, opened_at TEXT, closed_at TEXT,
                pips_simulated REAL, is_win INTEGER
            );
        """)
        # Insère 5 décisions GBPUSD haussiere avec paper_trades ouverts
        # IMPORTANT : utilise l'heure ACTUELLE pour éviter les bugs timezone
        # dans les tests (datetime.now() doit retourner >= opened_at).
        now = datetime.now(timezone.utc)
        for i in range(5):
            snapshot_id = f"snap_{i}"
            opened_at = (now - timedelta(seconds=300 - i * 30)).isoformat()
            conn.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"d{i}", snapshot_id, opened_at,
                 "GBPUSD", "M15", "NEUTRE", "haussiere", 1),
            )
            conn.execute(
                "INSERT INTO paper_trades(snapshot_id, opened_at, closed_at) VALUES (?, ?, ?)",
                (snapshot_id, opened_at, None),  # OPEN
            )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture(autouse=True)
def cleanup_env(monkeypatch: pytest.MonkeyPatch):
    """Isole les tests des variables d'environnement."""
    for env in (LOOP_BREAKER_ENABLED_ENV, MIN_HOLD_BARS_ENV,
                MAX_OPEN_TRADES_PER_SYMBOL_ENV, "V9_LOOP_BREAKER_WINDOW_MINUTES"):
        if env in os.environ:
            monkeypatch.delenv(env)
    yield


# ============================================================== T1 kill switch

def test_loop_breaker_default_off(monkeypatch: pytest.MonkeyPatch):
    """OFF explicite → False. Depuis le câblage P0.4 (2026-07-19), le switch
    lit `config/v9_kill_switches.env` (où il vaut 1) via kill_switches.get() ;
    on force donc OFF par l'environnement (priorité env > fichier)."""
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "0")
    assert loop_breaker_enabled() is False


def test_loop_breaker_enabled_when_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "1")
    assert loop_breaker_enabled() is True


def test_loop_breaker_other_values(monkeypatch: pytest.MonkeyPatch):
    for val in ("0", "false", "", "yes"):
        monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, val)
        assert loop_breaker_enabled() is False


# ============================================================== T2 allow si OFF

def test_check_loop_returns_allow_when_disabled(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Si loop_breaker OFF → always allow (OFF forcé par l'env, cf. P0.4)."""
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "0")
    decision = check_loop("GBPUSD", "haussiere", db_path=tmp_db)
    assert decision.allowed is True
    assert decision.reason == "loop_breaker_disabled"
    assert decision.action == "allow"


# ============================================================== T3 env defaults

def test_min_hold_default():
    assert _min_hold_seconds() == DEFAULT_MIN_HOLD_BARS


def test_min_hold_custom(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_HOLD_BARS_ENV, "120")
    assert _min_hold_seconds() == 120


def test_min_hold_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MIN_HOLD_BARS_ENV, "not_a_number")
    assert _min_hold_seconds() == DEFAULT_MIN_HOLD_BARS


def test_max_open_default():
    assert _max_open_per_symbol() == DEFAULT_MAX_OPEN_TRADES_PER_SYMBOL


def test_max_open_custom(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(MAX_OPEN_TRADES_PER_SYMBOL_ENV, "5")
    assert _max_open_per_symbol() == 5


def test_window_default():
    assert _window_minutes() == DEFAULT_LOOP_BREAKER_WINDOW_MINUTES


def test_window_custom(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("V9_LOOP_BREAKER_WINDOW_MINUTES", "30")
    assert _window_minutes() == 30


# ============================================================== T4-T7 check_loop activé

def test_check_loop_allows_when_no_open_trades(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Aucun trade ouvert → allow."""
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "1")
    monkeypatch.setenv(MIN_HOLD_BARS_ENV, "60")
    monkeypatch.setenv(MAX_OPEN_TRADES_PER_SYMBOL_ENV, "3")
    # DB a 5 trades ouverts GBPUSD → bloqué par max_open (3 < 5)
    decision = check_loop("EURUSD", "haussiere", db_path=tmp_db)
    # EURUSD a 0 trades ouverts → n_open=0 < max_open=3 → allow
    assert decision.allowed is True


def test_check_loop_blocks_max_open_reached(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """5 trades GBPUSD ouverts + max_open=3 → block."""
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "1")
    monkeypatch.setenv(MIN_HOLD_BARS_ENV, "60")
    monkeypatch.setenv(MAX_OPEN_TRADES_PER_SYMBOL_ENV, "3")
    decision = check_loop("GBPUSD", "haussiere", db_path=tmp_db)
    assert decision.allowed is False
    assert "max_open_per_symbol_reached" in decision.reason
    assert decision.action == "block"


def test_check_loop_blocks_density(tmp_db: Path, monkeypatch: pytest.MonkeyPatch):
    """Si > 10 trades dans la fenêtre → block (densité suspecte)."""
    from datetime import datetime, timezone, timedelta
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "1")
    monkeypatch.setenv(MIN_HOLD_BARS_ENV, "1")  # 1s pour ne pas avoir cooldown
    monkeypatch.setenv(MAX_OPEN_TRADES_PER_SYMBOL_ENV, "100")  # pas de limite
    # 15 paper trades fermés dans les 10 dernières minutes
    conn = sqlite3.connect(str(tmp_db))
    try:
        now = datetime.now(timezone.utc)
        for i in range(15):
            snap_id = f"snap_dens_{i}"
            opened_at = (now - timedelta(seconds=300 - i * 10)).isoformat()
            conn.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"d_d_{i}", snap_id, opened_at,
                 "USDJPY", "M15", "NEUTRE", "haussiere", 1),
            )
            conn.execute(
                "INSERT INTO paper_trades(snapshot_id, opened_at, closed_at) VALUES (?, ?, ?)",
                (snap_id, opened_at, opened_at),
            )
        conn.commit()
    finally:
        conn.close()
    decision = check_loop("USDJPY", "haussiere", db_path=tmp_db)
    assert decision.allowed is False
    assert "suspicious_density" in decision.reason


def test_check_loop_decision_dataclass():
    """LoopDecision immuable + to_dict."""
    d = LoopDecision(
        allowed=False, reason="test", n_recent_trades=5,
        seconds_since_last_trade=10.0, action="block",
    )
    assert d.allowed is False
    dd = d.to_dict()
    assert dd["action"] == "block"
    assert dd["n_recent_trades"] == 5


# ============================================================== T8-T9 R6 DB errors

def test_check_loop_db_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """DB absente → allow (R6 fallback safe)."""
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "1")
    decision = check_loop("GBPUSD", "haussiere", db_path=tmp_path / "no.db")
    # DB absente → 0 trades récents, inf secondes → allow
    assert decision.allowed is True


def test_check_loop_db_corrupt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """DB corrompue → allow (R6)."""
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "1")
    db = tmp_path / "corrupt.db"
    db.write_text("not sqlite")
    decision = check_loop("GBPUSD", "haussiere", db_path=db)
    assert decision.allowed is True


def test_check_loop_db_no_paper_trades_table(monkeypatch: pytest.MonkeyPatch,
                                              tmp_path: Path):
    """DB sans table paper_trades → allow (R6)."""
    monkeypatch.setenv(LOOP_BREAKER_ENABLED_ENV, "1")
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE foo (x INT);")
        conn.commit()
    finally:
        conn.close()
    decision = check_loop("GBPUSD", "haussiere", db_path=db)
    assert decision.allowed is True


# ============================================================== T10 get_stats

def test_get_stats_returns_dict(tmp_db: Path):
    stats = get_stats(db_path=tmp_db)
    assert isinstance(stats, dict)
    assert "enabled" in stats
    assert "min_hold_seconds" in stats
    assert "max_open_per_symbol" in stats
    assert "window_minutes" in stats


def test_get_stats_db_missing(tmp_path: Path):
    stats = get_stats(db_path=tmp_path / "no.db")
    assert "db_status" in stats
    assert stats["db_status"] == "absent"


def test_get_stats_counts_open_trades(tmp_db: Path):
    stats = get_stats(db_path=tmp_db)
    assert stats.get("n_open_trades") == 5  # 5 paper trades ouverts
    assert stats.get("n_symbols_with_open") == 1  # 1 symbol (GBPUSD)
