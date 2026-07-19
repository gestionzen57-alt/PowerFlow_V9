"""test_v9_live_watchdog.py — Tests pour core/v9/v9_live_watchdog.py (Axe 6).

Vérifie :
T1. Kill switch V9_LIVE_WATCHDOG_ENABLED — défaut OFF → statut "disabled"
T2. Seuils env (_env_float / _env_int) surchargeables
T3. check_health() statut "ok" quand WR haut & DD sain
T4. check_health() "warn" si WR < 80 %
T5. check_health() "critical" + P0 si WR < 60 %
T6. check_health() "warn" si DD 24h < -200 pips (WR sain)
T7. check_health() "no_data" si aucun trade
T8. MIN_TRADES_FOR_WR : pas de verdict WR sous le seuil
T9. R6 : DB absente → ok/no_data (jamais crash)
T10. get_stats() diagnostic
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from core.v9.v9_live_watchdog import (
    DEFAULT_DD_24H_PIPS,
    DEFAULT_WR_WARN,
    DEFAULT_WR_CRIT,
    LIVE_WATCHDOG_ENABLED_ENV,
    DD_24H_PIPS_ENV,
    WR_CRIT_ENV,
    WatchdogDecision,
    check_health,
    get_stats,
    live_watchdog_enabled,
    _env_float,
    _env_int,
)


def _make_db(tmp_path: Path, trades: list[tuple[float, int, float]]) -> Path:
    """Crée une DB paper_trades. trades = list of (pips, is_win, hours_ago)."""
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """CREATE TABLE paper_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, opened_at TEXT, closed_at TEXT,
                pips_simulated REAL, is_win INTEGER)"""
        )
        now = datetime.now(timezone.utc)
        for pips, is_win, hours_ago in trades:
            closed = (now - timedelta(hours=hours_ago)).isoformat()
            conn.execute(
                "INSERT INTO paper_trades (snapshot_id, opened_at, closed_at, pips_simulated, is_win) "
                "VALUES (?, ?, ?, ?, ?)",
                ("s", closed, closed, pips, is_win),
            )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture(autouse=True)
def _clean_env():
    """Isole les env vars du watchdog entre tests."""
    saved = {k: os.environ.get(k) for k in
             (LIVE_WATCHDOG_ENABLED_ENV, DD_24H_PIPS_ENV, WR_CRIT_ENV)}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ── T1 : kill switch défaut OFF ────────────────────────────────────

def test_disabled_by_default(tmp_path):
    os.environ.pop(LIVE_WATCHDOG_ENABLED_ENV, None)
    assert live_watchdog_enabled() is False
    d = check_health(_make_db(tmp_path, [(-5, 0, 1)] * 20))
    assert d.status == "disabled"
    assert d.recommended_actions == ()


# ── T2 : seuils env ────────────────────────────────────────────────

def test_env_overrides():
    os.environ[DD_24H_PIPS_ENV] = "-500"
    assert _env_float(DD_24H_PIPS_ENV, DEFAULT_DD_24H_PIPS) == -500.0
    os.environ["V9_WATCHDOG_WR_WINDOW"] = "30"
    assert _env_int("V9_WATCHDOG_WR_WINDOW", 50) == 30
    os.environ.pop("V9_WATCHDOG_WR_WINDOW", None)


def test_env_invalid_falls_back():
    os.environ[DD_24H_PIPS_ENV] = "not_a_number"
    assert _env_float(DD_24H_PIPS_ENV, DEFAULT_DD_24H_PIPS) == DEFAULT_DD_24H_PIPS


# ── T3 : ok ────────────────────────────────────────────────────────

def test_health_ok(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # 20 trades, WR 95 %, pips positifs → ok
    trades = [(8.0, 1, 1)] * 19 + [(-15.0, 0, 1)]
    d = check_health(_make_db(tmp_path, trades))
    assert d.status == "ok"
    assert d.alert_level == "none"
    assert d.recommended_actions == ()
    assert d.wr_recent == 0.95


# ── T4 : warn WR < 80 % ────────────────────────────────────────────

def test_health_warn_wr(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # WR 70 % (14 win / 6 loss), pips nets positifs pour ne PAS déclencher DD
    trades = [(8.0, 1, 1)] * 14 + [(-2.0, 0, 1)] * 6
    d = check_health(_make_db(tmp_path, trades))
    assert d.status == "warn"
    assert d.alert_level == "warn"
    assert "V9_TRADER_MINI_ENABLED=0" in d.recommended_actions
    assert "V9_GBPUSD_LONG_ONLY=0" not in d.recommended_actions


# ── T5 : critical WR < 60 % ────────────────────────────────────────

def test_health_critical_wr(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # WR 30 % (6 win / 14 loss)
    trades = [(8.0, 1, 1)] * 6 + [(-1.0, 0, 1)] * 14
    d = check_health(_make_db(tmp_path, trades))
    assert d.status == "critical"
    assert d.alert_level == "p0"
    assert "V9_GBPUSD_LONG_ONLY=0" in d.recommended_actions
    assert "V9_TRADER_MINI_ENABLED=0" in d.recommended_actions


# ── T6 : warn DD 24h ───────────────────────────────────────────────

def test_health_warn_drawdown(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # WR sain (90 %) mais DD 24h très négatif (grosses pertes concentrées)
    trades = [(1.0, 1, 1)] * 18 + [(-150.0, 0, 1)] * 2
    d = check_health(_make_db(tmp_path, trades))
    assert d.dd_24h_pips < DEFAULT_DD_24H_PIPS
    assert d.status == "warn"
    assert "V9_TRADER_MINI_ENABLED=0" in d.recommended_actions


# ── T7 : no_data ───────────────────────────────────────────────────

def test_no_data(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    d = check_health(_make_db(tmp_path, []))
    assert d.status == "no_data"
    assert d.n_recent == 0


# ── T8 : MIN_TRADES_FOR_WR ─────────────────────────────────────────

def test_wr_ignored_below_min_trades(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # 5 trades WR 0 % mais < MIN_TRADES_FOR_WR (10) → pas de verdict WR,
    # pips faibles pour ne pas déclencher DD non plus → ok
    trades = [(-1.0, 0, 1)] * 5
    d = check_health(_make_db(tmp_path, trades))
    assert d.status == "ok"
    assert d.n_recent == 5


# ── T9 : R6 DB absente ─────────────────────────────────────────────

def test_db_absent_safe(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    d = check_health(tmp_path / "nonexistent.db")
    assert d.status == "no_data"
    assert d.recommended_actions == ()


# ── T10 : get_stats ────────────────────────────────────────────────

def test_get_stats():
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    s = get_stats()
    assert s["enabled"] is True
    assert s["dd_24h_limit_pips"] == DEFAULT_DD_24H_PIPS
    assert s["wr_warn"] == DEFAULT_WR_WARN
    assert s["wr_crit"] == DEFAULT_WR_CRIT


def test_decision_to_dict():
    d = WatchdogDecision(status="ok", dd_24h_pips=10.0, wr_recent=0.9, n_recent=20)
    js = d.to_dict()
    assert js["status"] == "ok"
    assert js["recommended_actions"] == []
