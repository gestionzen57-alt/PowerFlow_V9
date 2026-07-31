"""tests/test_v9_edge_fund_max.py — Phase 21 motion CEO « EDGE FUND MAX ».

Tests pour mega_edge_optimizer, win_streak, paper_performance.
"""
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# === v9_mega_edge_optimizer ===

def test_compute_hour_wr():
    """compute_hour_wr agrege correctement par heure."""
    from scripts.v9_mega_edge_optimizer import compute_hour_wr
    trades = [
        {"hour_utc": "11", "pips_net": 25.0},
        {"hour_utc": "11", "pips_net": 25.0},
        {"hour_utc": "11", "pips_net": -8.0},
        {"hour_utc": "12", "pips_net": 25.0},
        {"hour_utc": "13", "pips_net": -8.0},
    ]
    result = compute_hour_wr(trades)
    assert result["11"]["n"] == 3
    assert result["11"]["wins"] == 2
    assert result["11"]["wr_pct"] == pytest.approx(66.67, abs=0.1)
    assert result["13"]["n"] == 1
    assert result["13"]["wr_pct"] == 0.0


def test_compute_symbol_blacklist():
    """compute_symbol_blacklist detecte symbols avec WR<50%."""
    from scripts.v9_mega_edge_optimizer import compute_symbol_blacklist
    trades = [
        {"symbol": "GBPUSD", "pips_net": 25.0},
        {"symbol": "GBPUSD", "pips_net": 25.0},
        {"symbol": "GBPUSD", "pips_net": 25.0},
        {"symbol": "GBPUSD", "pips_net": 25.0},
        {"symbol": "GBPUSD", "pips_net": 25.0},
        {"symbol": "EURUSD", "pips_net": -8.0},
        {"symbol": "EURUSD", "pips_net": -8.0},
        {"symbol": "EURUSD", "pips_net": -8.0},
        {"symbol": "EURUSD", "pips_net": -8.0},
        {"symbol": "EURUSD", "pips_net": -8.0},
    ]
    blacklist = compute_symbol_blacklist(trades)
    assert "EURUSD" in blacklist
    assert "GBPUSD" not in blacklist


def test_compute_symbol_blacklist_below_min_n():
    """compute_symbol_blacklist ignore les symbols avec n<min_n."""
    from scripts.v9_mega_edge_optimizer import compute_symbol_blacklist
    trades = [{"symbol": "USDJPY", "pips_net": -8.0}] * 3  # n=3, default min_n=5
    blacklist = compute_symbol_blacklist(trades, min_n=5)
    assert "USDJPY" not in blacklist


def test_compute_day_blacklist():
    """compute_day_blacklist detecte jours avec WR<50%."""
    from scripts.v9_mega_edge_optimizer import compute_day_blacklist
    # 2026-07-28 = Mardi (L14 inverted)
    base = "2026-07-28"
    trades = []
    for i in range(5):
        trades.append({
            "opened_at": f"{base}T11:{i:02d}:00",
            "pips_net": -8.0,
        })
    blacklist = compute_day_blacklist(trades)
    assert "Tuesday" in blacklist


def test_optimize_runtime_db_missing(tmp_path):
    """optimize_runtime sur DB absente → WAIT_MORE_DATA."""
    from scripts.v9_mega_edge_optimizer import optimize_runtime
    res = optimize_runtime(tmp_path / "absent.db")
    assert res["recommendation"] == "WAIT_MORE_DATA"


def test_optimize_runtime_insufficient_data(tmp_path):
    """optimize_runtime avec n<20 → WAIT_MORE_DATA."""
    from scripts.v9_mega_edge_optimizer import optimize_runtime
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, opened_at TEXT, closed_at TEXT,
                pips_brut REAL, pips_net REAL
            )
        """)
        for i in range(5):
            conn.execute("""
                INSERT INTO v9_paper_trades
                (symbol, opened_at, closed_at, pips_brut, pips_net)
                VALUES (?, ?, ?, 25.0, 23.5)
            """, ("GBPUSD", f"2026-07-31T11:{i:02d}:00",
                  f"2026-07-31T11:{i:02d}:30"))
        conn.commit()
    res = optimize_runtime(db)
    assert res["recommendation"] == "WAIT_MORE_DATA"


def test_optimize_runtime_sufficient(tmp_path):
    """optimize_runtime avec 25 trades GBPUSD 11h → APPLY_OVERRIDES."""
    from scripts.v9_mega_edge_optimizer import optimize_runtime
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT, symbol TEXT, direction TEXT,
                opened_at TEXT, closed_at TEXT, entry_price REAL,
                tp_pips REAL, sl_pips REAL, lot REAL,
                close_reason TEXT, close_price REAL,
                pips_brut REAL, pips_net REAL,
                spread_pips REAL, leviers TEXT, confidence REAL
            )
        """)
        for i in range(25):
            conn.execute("""
                INSERT INTO v9_paper_trades
                (symbol, opened_at, closed_at, pips_brut, pips_net, spread_pips)
                VALUES (?, ?, ?, 25.0, 23.5, 1.5)
            """, ("GBPUSD", f"2026-07-31T11:{i:02d}:00",
                  f"2026-07-31T11:{i:02d}:30"))
        conn.commit()
    res = optimize_runtime(db)
    assert res["recommendation"] == "APPLY_OVERRIDES"
    assert "11" in res["optimal_hours_utc"]


def test_apply_runtime_overrides(tmp_path, monkeypatch):
    """apply_runtime_overrides ecrit le fichier."""
    from scripts.v9_mega_edge_optimizer import apply_runtime_overrides
    overrides_file = tmp_path / "overrides.json"
    monkeypatch.setattr(
        "scripts.v9_mega_edge_optimizer.RUNTIME_OVERRIDES_FILE",
        overrides_file,
    )
    opt = {
        "ts": "2026-07-31T12:00:00",
        "recommendation": "APPLY_OVERRIDES",
        "optimal_hours_utc": ["11", "13"],
        "symbol_blacklist_runtime": ["EURUSD"],
        "day_blacklist_runtime": ["Tuesday"],
        "wr_by_hour": {"11": {"n": 25, "wins": 24, "wr_pct": 96.0}},
    }
    ok = apply_runtime_overrides(opt)
    assert ok is True
    assert overrides_file.exists()


def test_apply_runtime_overrides_skips_if_not_apply():
    """apply_runtime_overrides ne fait rien si recommendation != APPLY."""
    from scripts.v9_mega_edge_optimizer import apply_runtime_overrides
    ok = apply_runtime_overrides({"recommendation": "WAIT_MORE_DATA"})
    assert ok is False


# === v9_win_streak ===

def test_compute_streaks_empty():
    """compute_streaks sur liste vide → 0 partout."""
    from scripts.v9_win_streak import compute_streaks
    res = compute_streaks([])
    assert res["n_total"] == 0
    assert res["current_streak"] == 0
    assert res["current_type"] == "none"


def test_compute_streaks_all_wins():
    """compute_streaks sur tous wins → current=win, max=full."""
    from scripts.v9_win_streak import compute_streaks
    trades = [{"pips_net": 10.0}] * 5
    res = compute_streaks(trades)
    assert res["current_streak"] == 5
    assert res["current_type"] == "win"
    assert res["max_win_streak"] == 5
    assert res["max_loss_streak"] == 0


def test_compute_streaks_loss_streak():
    """compute_streaks sur 4 losses consecutives → loss_streak=4."""
    from scripts.v9_win_streak import compute_streaks
    trades = [{"pips_net": -5.0}] * 4
    res = compute_streaks(trades)
    assert res["current_streak"] == 4
    assert res["current_type"] == "loss"
    assert res["max_loss_streak"] == 4


def test_compute_streaks_mixed():
    """compute_streaks mixed win/loss streaks."""
    from scripts.v9_win_streak import compute_streaks
    trades = [
        {"pips_net": 10.0},
        {"pips_net": 10.0},
        {"pips_net": -5.0},
        {"pips_net": -5.0},
        {"pips_net": -5.0},
        {"pips_net": 10.0},
        {"pips_net": 10.0},
    ]
    res = compute_streaks(trades)
    assert res["current_streak"] == 2
    assert res["current_type"] == "win"
    assert res["max_win_streak"] == 2
    assert res["max_loss_streak"] == 3


def test_get_recommendation_ok():
    """get_recommendation : pas d'alerte sur streak safe."""
    from scripts.v9_win_streak import get_recommendation
    rec, alerts = get_recommendation({
        "current_streak": 1, "current_type": "win",
        "max_win_streak": 3, "max_loss_streak": 1, "n_total": 10,
    })
    assert rec == "OK"
    assert alerts == []


def test_get_recommendation_loss_streak_alert():
    """get_recommendation : alerte sur 3+ losses."""
    from scripts.v9_win_streak import get_recommendation
    rec, alerts = get_recommendation({
        "current_streak": 3, "current_type": "loss",
        "max_win_streak": 2, "max_loss_streak": 3, "n_total": 10,
    })
    assert rec == "ALERT"
    assert any("Loss streak" in a for a in alerts)


def test_get_recommendation_kill_switch():
    """get_recommendation : KILL_SWITCH_PROPOSED sur 5+ losses."""
    from scripts.v9_win_streak import get_recommendation
    rec, alerts = get_recommendation({
        "current_streak": 5, "current_type": "loss",
        "max_win_streak": 2, "max_loss_streak": 5, "n_total": 10,
    })
    assert rec == "KILL_SWITCH_PROPOSED"


def test_get_recent_trades_db_missing(tmp_path):
    """get_recent_trades sur DB absente → []."""
    from scripts.v9_win_streak import get_recent_trades
    assert get_recent_trades(tmp_path / "absent.db") == []


def test_get_recent_trades_with_db(tmp_path):
    """get_recent_trades retourne les trades fermes en ordre ASC."""
    from scripts.v9_win_streak import get_recent_trades
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, opened_at TEXT, closed_at TEXT,
                pips_net REAL
            )
        """)
        for i in range(5):
            conn.execute("""
                INSERT INTO v9_paper_trades
                (symbol, opened_at, closed_at, pips_net)
                VALUES ('GBPUSD', ?, ?, 25.0)
            """, (f"2026-07-31T11:{i:02d}:00",
                  f"2026-07-31T11:{i:02d}:30"))
        conn.commit()
    trades = get_recent_trades(db, n=10)
    assert len(trades) == 5
    assert trades[0]["opened_at"] < trades[-1]["opened_at"]


def test_save_state(tmp_path, monkeypatch):
    """save_state cree le fichier state."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr("scripts.v9_win_streak.STREAK_STATE_FILE", state_file)
    from scripts.v9_win_streak import save_state
    save_state({"current_streak": 5, "current_type": "win"})
    assert state_file.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["streaks"]["current_streak"] == 5


# === v9_paper_performance ===

def test_compute_performance_empty():
    """compute_performance sur liste vide → no_trades."""
    from scripts.v9_paper_performance import compute_performance
    res = compute_performance([])
    assert res["error"] == "no_trades"


def test_compute_performance_basic():
    """compute_performance calcule les metriques correctement."""
    from scripts.v9_paper_performance import compute_performance
    trades = [
        {"pips_net": 25.0, "pips_brut": 25.0},
        {"pips_net": 25.0, "pips_brut": 25.0},
        {"pips_net": -8.0, "pips_brut": -8.0},
    ]
    res = compute_performance(trades)
    assert res["n_total"] == 3
    assert res["n_wins"] == 2
    assert res["n_losses"] == 1
    assert res["win_rate_pct"] == pytest.approx(66.67, abs=0.1)
    assert res["total_pips_net"] == pytest.approx(42.0, abs=0.1)
    assert res["expectancy_net"] == pytest.approx(14.0, abs=0.1)
    assert res["profit_factor"] == pytest.approx(6.25, abs=0.1)


def test_compute_performance_all_losses():
    """compute_performance sur tous losses → max_dd egal total net."""
    from scripts.v9_paper_performance import compute_performance
    trades = [
        {"pips_net": -10.0, "pips_brut": -10.0},
        {"pips_net": -8.0, "pips_brut": -8.0},
    ]
    res = compute_performance(trades)
    assert res["n_wins"] == 0
    assert res["n_losses"] == 2
    assert res["profit_factor"] == 0.0  # no wins
    assert res["max_dd_pips"] == 18.0


def test_compute_performance_sharpe():
    """compute_performance calcule Sharpe-like avec n>=2."""
    from scripts.v9_paper_performance import compute_performance
    trades = [
        {"pips_net": 25.0, "pips_brut": 25.0},
        {"pips_net": -8.0, "pips_brut": -8.0},
        {"pips_net": 25.0, "pips_brut": 25.0},
    ]
    res = compute_performance(trades)
    # mean=14, std calculee manuellement
    mean = 14.0
    var = ((25-14)**2 + (-8-14)**2 + (25-14)**2) / 2  # n-1
    expected_std = math.sqrt(var)
    expected_sharpe = mean / expected_std
    assert res["sharpe_like"] == pytest.approx(expected_sharpe, abs=0.05)


def test_compute_performance_single_trade():
    """compute_performance avec 1 seul trade → sharpe=0."""
    from scripts.v9_paper_performance import compute_performance
    res = compute_performance([{"pips_net": 25.0, "pips_brut": 25.0}])
    assert res["sharpe_like"] == 0.0


def test_compute_performance_recovery_factor_inf():
    """compute_performance avec max_dd=0 → recovery_factor=inf."""
    from scripts.v9_paper_performance import compute_performance
    res = compute_performance([{"pips_net": 25.0, "pips_brut": 25.0}])
    assert res["recovery_factor"] == "inf"


def test_compute_performance_profit_factor_inf():
    """compute_performance sans losses → profit_factor=inf."""
    from scripts.v9_paper_performance import compute_performance
    res = compute_performance([
        {"pips_net": 25.0, "pips_brut": 25.0},
        {"pips_net": 25.0, "pips_brut": 25.0},
    ])
    assert res["profit_factor"] == "inf"


def test_get_paper_trades_db_missing(tmp_path):
    """get_paper_trades sur DB absente → []."""
    from scripts.v9_paper_performance import get_paper_trades
    assert get_paper_trades(tmp_path / "absent.db") == []


def test_get_paper_trades_with_filter(tmp_path):
    """get_paper_trades filtre les N derniers jours."""
    from scripts.v9_paper_performance import get_paper_trades
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, direction TEXT, opened_at TEXT,
                closed_at TEXT, pips_brut REAL, pips_net REAL,
                spread_pips REAL
            )
        """)
        for i in range(5):
            conn.execute("""
                INSERT INTO v9_paper_trades
                (symbol, direction, opened_at, closed_at, pips_brut, pips_net, spread_pips)
                VALUES ('GBPUSD', 'haussiere', ?, ?, 25.0, 23.5, 1.5)
            """, (f"2026-07-31T11:{i:02d}:00",
                  f"2026-07-31T11:{i:02d}:30"))
        conn.commit()
    trades = get_paper_trades(db, days=30)
    assert len(trades) == 5