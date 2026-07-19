"""test_v9_live_watchdog.py — Tests pour core/v9/v9_live_watchdog.py (Axe 6).

Vérifie (post-correctifs pré-réouverture 2026-07-19) :
T1.  Kill switch V9_LIVE_WATCHDOG_ENABLED — OFF explicite → statut "disabled"
T2.  Seuils env (_env_float / _env_int) surchargeables
T3.  check_health() statut "ok" quand WR haut & P&L sain
T4.  check_health() "warn" si WR < 80 %
T5.  check_health() "critical" + P0 si WR < 60 %
T6.  P0 ne désactive JAMAIS V9_GBPUSD_LONG_ONLY (audit 07-19)
T7.  P0 recommande V9_PAPER_TRADE_HALT=1 (vrai arrêt)
T8.  check_health() "warn" si P&L net 24h < -200 pips (WR sain)
T9.  WR segmenté GBPUSD long-only : le WR global ne compte pas
T10. check_health() "no_data" si aucun trade
T11. "no_data" si aucun trade GBPUSD long (que des shorts / autres paires)
T12. db absente → "db_error" + alerte p0 (télémétrie muette = danger)
T13. schema incompatible → "db_error"
T14. db verrouillée / connexion en échec → "db_error"
T15. connexion SQLite ouverte en read-only strict (mode=ro, uri=True)
T16. get_stats() diagnostic
T17. to_dict() expose les nouveaux noms de champs
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

import core.v9.v9_live_watchdog as wd
from core.v9.v9_live_watchdog import (
    DEFAULT_DD_24H_PIPS,
    DEFAULT_WR_WARN,
    DEFAULT_WR_CRIT,
    LIVE_WATCHDOG_ENABLED_ENV,
    DD_24H_PIPS_ENV,
    WR_WINDOW_ENV,
    WR_WARN_ENV,
    WR_CRIT_ENV,
    ACTION_HALT,
    WatchdogDecision,
    check_health,
    get_stats,
    live_watchdog_enabled,
    _env_float,
    _env_int,
)


def _make_db(
    tmp_path: Path,
    trades: list[tuple[float, int, float]],
    symbol: str = "GBPUSD",
    direction: str = "haussiere",
) -> Path:
    """Crée une DB paper_trades + decisions (jointure snapshot_id).

    trades = list of (pips, is_win, hours_ago). Tous les trades partagent
    le même (symbol, direction) par défaut = GBPUSD/haussiere (segment surveillé).
    """
    return _make_db_multi(tmp_path, [(symbol, direction, trades)])


def _make_db_multi(
    tmp_path: Path,
    groups: list[tuple[str, str, list[tuple[float, int, float]]]],
) -> Path:
    """Crée une DB mixte. groups = list of (symbol, direction, trades)."""
    db = tmp_path / "fake.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "CREATE TABLE decisions (snapshot_id TEXT, symbol TEXT, direction TEXT)"
        )
        conn.execute(
            """CREATE TABLE paper_trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, direction TEXT, opened_at TEXT, closed_at TEXT,
                pips_simulated REAL, is_win INTEGER)"""
        )
        now = datetime.now(timezone.utc)
        idx = 0
        for symbol, direction, trades in groups:
            for pips, is_win, hours_ago in trades:
                sid = f"s{idx}"
                idx += 1
                closed = (now - timedelta(hours=hours_ago)).isoformat()
                conn.execute(
                    "INSERT INTO decisions (snapshot_id, symbol, direction) VALUES (?, ?, ?)",
                    (sid, symbol, direction),
                )
                conn.execute(
                    "INSERT INTO paper_trades "
                    "(snapshot_id, direction, opened_at, closed_at, pips_simulated, is_win) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (sid, direction, closed, closed, pips, is_win),
                )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture(autouse=True)
def _clean_env():
    """Isole les env vars du watchdog entre tests."""
    keys = (LIVE_WATCHDOG_ENABLED_ENV, DD_24H_PIPS_ENV,
            WR_WINDOW_ENV, WR_WARN_ENV, WR_CRIT_ENV)
    saved = {k: os.environ.get(k) for k in keys}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ── T1 : kill switch OFF explicite ─────────────────────────────────

def test_disabled_by_default(tmp_path):
    # Le fichier .env a V9_LIVE_WATCHDOG_ENABLED=1 → on force OFF par l'env
    # (priorité env > fichier dans kill_switches.get()).
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "0"
    assert live_watchdog_enabled() is False
    d = check_health(_make_db(tmp_path, [(-5, 0, 1)] * 20))
    assert d.status == "disabled"
    assert d.recommended_actions == ()


# ── T2 : seuils env ────────────────────────────────────────────────

def test_env_overrides():
    os.environ[DD_24H_PIPS_ENV] = "-500"
    assert _env_float(DD_24H_PIPS_ENV, DEFAULT_DD_24H_PIPS) == -500.0
    os.environ[WR_WINDOW_ENV] = "30"
    assert _env_int(WR_WINDOW_ENV, 50) == 30


def test_env_invalid_falls_back():
    os.environ[DD_24H_PIPS_ENV] = "not_a_number"
    assert _env_float(DD_24H_PIPS_ENV, DEFAULT_DD_24H_PIPS) == DEFAULT_DD_24H_PIPS


# ── T3 : ok ────────────────────────────────────────────────────────

def test_health_ok(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # 20 trades GBPUSD long, WR 95 %, pips positifs → ok
    trades = [(8.0, 1, 1)] * 19 + [(-15.0, 0, 1)]
    d = check_health(_make_db(tmp_path, trades))
    assert d.status == "ok"
    assert d.alert_level == "none"
    assert d.recommended_actions == ()
    assert d.wr_long_only_gbpusd == 0.95


# ── T4 : warn WR < 80 % ────────────────────────────────────────────

def test_health_warn_wr(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # WR 70 % (14 win / 6 loss), pips nets positifs (ne déclenche pas le P&L)
    trades = [(8.0, 1, 1)] * 14 + [(-2.0, 0, 1)] * 6
    d = check_health(_make_db(tmp_path, trades))
    assert d.status == "warn"
    assert d.alert_level == "warn"
    assert "V9_TRADER_MINI_ENABLED=0" in d.recommended_actions
    assert "V9_GBPUSD_LONG_ONLY=0" not in d.recommended_actions


# ── T5 : critical WR < 60 % ────────────────────────────────────────

def test_health_critical_wr(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # WR 30 % (6 win / 14 loss), pips nets positifs
    trades = [(8.0, 1, 1)] * 6 + [(-1.0, 0, 1)] * 14
    d = check_health(_make_db(tmp_path, trades))
    assert d.status == "critical"
    assert d.alert_level == "p0"


# ── T6 : P0 ne désactive JAMAIS long-only ──────────────────────────

def test_health_p0_does_not_disable_long_only(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    trades = [(8.0, 1, 1)] * 6 + [(-1.0, 0, 1)] * 14
    d = check_health(_make_db(tmp_path, trades))
    assert d.status == "critical"
    assert "V9_GBPUSD_LONG_ONLY=0" not in d.recommended_actions


# ── T7 : P0 recommande le HALT total ───────────────────────────────

def test_health_p0_recommends_paper_trade_halt(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    trades = [(8.0, 1, 1)] * 6 + [(-1.0, 0, 1)] * 14
    d = check_health(_make_db(tmp_path, trades))
    assert ACTION_HALT in d.recommended_actions
    assert "V9_PAPER_TRADE_HALT=1" in d.recommended_actions


# ── T8 : warn P&L net 24h ──────────────────────────────────────────

def test_health_warn_drawdown(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # WR sain (90 %) mais P&L 24h très négatif (grosses pertes concentrées)
    trades = [(1.0, 1, 1)] * 18 + [(-150.0, 0, 1)] * 2
    d = check_health(_make_db(tmp_path, trades))
    assert d.net_pnl_24h_pips < DEFAULT_DD_24H_PIPS
    assert d.status == "warn"
    assert "V9_TRADER_MINI_ENABLED=0" in d.recommended_actions


# ── T9 : segmentation GBPUSD long-only ─────────────────────────────

def test_health_segmented_long_only(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # Segment surveillé (GBPUSD haussiere) = 12 wins → WR 100 %.
    # Bruit ignoré : shorts GBPUSD + EURUSD, tous perdants.
    db = _make_db_multi(tmp_path, [
        ("GBPUSD", "haussiere", [(8.0, 1, 1)] * 12),
        ("GBPUSD", "baissiere", [(-5.0, 0, 1)] * 10),
        ("EURUSD", "haussiere", [(-5.0, 0, 1)] * 8),
    ])
    d = check_health(db)
    # WR global (12/30 = 40 %) serait critique, mais seul le segment compte.
    assert d.status == "ok"
    assert d.wr_long_only_gbpusd == 1.0
    assert d.n_recent == 12


# ── T10 : no_data (aucun trade) ────────────────────────────────────

def test_no_data(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    d = check_health(_make_db(tmp_path, []))
    assert d.status == "no_data"
    assert d.n_recent == 0


# ── T11 : no_data si aucun GBPUSD long ─────────────────────────────

def test_no_long_only_trades_returns_no_data(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    # 50 shorts uniquement → segment haussiere vide → no_data, pas d'alerte
    db = _make_db(tmp_path, [(-5.0, 0, 1)] * 50, direction="baissiere")
    d = check_health(db)
    assert d.status == "no_data"
    assert d.n_recent == 0
    assert d.alert_level == "none"


# ── T12 : db absente → db_error + p0 ───────────────────────────────

def test_db_absent_returns_error(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    d = check_health(tmp_path / "nonexistent.db")
    assert d.status == "db_error"
    assert d.alert_level == "p0"
    assert ACTION_HALT in d.recommended_actions


# ── T13 : schema incompatible → db_error ───────────────────────────

def test_db_missing_schema(tmp_path):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    db = tmp_path / "empty.db"
    sqlite3.connect(str(db)).close()  # DB vide, aucune table
    d = check_health(db)
    assert d.status == "db_error"
    assert d.alert_level == "p0"


# ── T14 : connexion en échec (verrou) → db_error ───────────────────

def test_db_locked_returns_error(tmp_path, monkeypatch):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    db = _make_db(tmp_path, [(5.0, 1, 1)] * 12)

    def _boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(wd.sqlite3, "connect", _boom)
    d = check_health(db)
    assert d.status == "db_error"
    assert d.alert_level == "p0"


# ── T15 : connexion read-only stricte ──────────────────────────────

def test_readonly_connection_uri(tmp_path, monkeypatch):
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    db = _make_db(tmp_path, [(5.0, 1, 1)] * 12)
    real_connect = sqlite3.connect
    captured: dict = {}

    def _spy(*args, **kwargs):
        captured.setdefault("calls", []).append((args, kwargs))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(wd.sqlite3, "connect", _spy)
    check_health(db)
    assert captured.get("calls"), "sqlite3.connect never called"
    args, kwargs = captured["calls"][0]
    assert "mode=ro" in args[0]
    assert kwargs.get("uri") is True


# ── T16 : get_stats ────────────────────────────────────────────────

def test_get_stats():
    os.environ[LIVE_WATCHDOG_ENABLED_ENV] = "1"
    s = get_stats()
    assert s["enabled"] is True
    assert s["dd_24h_limit_pips"] == DEFAULT_DD_24H_PIPS
    assert s["wr_warn"] == DEFAULT_WR_WARN
    assert s["wr_crit"] == DEFAULT_WR_CRIT
    assert s["segment"] == "GBPUSD/haussiere"


# ── T17 : to_dict nouveaux champs ──────────────────────────────────

def test_decision_to_dict():
    d = WatchdogDecision(
        status="ok", net_pnl_24h_pips=10.0, wr_long_only_gbpusd=0.9, n_recent=20,
    )
    js = d.to_dict()
    assert js["status"] == "ok"
    assert js["net_pnl_24h_pips"] == 10.0
    assert js["wr_long_only_gbpusd"] == 0.9
    assert js["recommended_actions"] == []
