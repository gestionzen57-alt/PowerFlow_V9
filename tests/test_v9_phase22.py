"""tests/test_v9_phase22.py — Phase 22 motion CEO « EDGE FUND MAX ».

Tests pour trade journal, daily summary, edge momentum.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# === v9_trade_journal ===

def test_get_trades_for_day_db_missing(tmp_path):
    """get_trades_for_day sur DB absente → []."""
    from scripts.v9_trade_journal import get_trades_for_day
    assert get_trades_for_day(tmp_path / "absent.db", "2026-07-31") == []


def test_get_trades_for_day_with_data(tmp_path):
    """get_trades_for_day retourne trades fermes du jour."""
    from scripts.v9_trade_journal import get_trades_for_day
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, opened_at TEXT, closed_at TEXT,
                pips_brut REAL, pips_net REAL, close_reason TEXT,
                spread_pips REAL
            )
        """)
        for i in range(5):
            conn.execute("""
                INSERT INTO v9_paper_trades
                (symbol, opened_at, closed_at, pips_brut, pips_net,
                 close_reason, spread_pips)
                VALUES ('GBPUSD', ?, ?, 25.0, 23.5, 'TP_hit', 1.5)
            """, (f"2026-07-31T11:{i:02d}:00",
                  f"2026-07-31T11:{i:02d}:30"))
        conn.commit()
    trades = get_trades_for_day(db, "2026-07-31")
    assert len(trades) == 5
    assert all(t["symbol"] == "GBPUSD" for t in trades)


def test_aggregate_day_empty():
    """aggregate_day avec liste vide → 0 partout."""
    from scripts.v9_trade_journal import aggregate_day
    res = aggregate_day([], "2026-07-31")
    assert res["n_total"] == 0
    assert res["wr_pct"] == 0.0
    assert res["pips_net"] == 0.0


def test_aggregate_day_with_trades():
    """aggregate_day calcule WR et pips correctement."""
    from scripts.v9_trade_journal import aggregate_day
    trades = [
        {"pips_net": 25.0, "pips_brut": 25.0},
        {"pips_net": 25.0, "pips_brut": 25.0},
        {"pips_net": -8.0, "pips_brut": -8.0},
    ]
    res = aggregate_day(trades, "2026-07-31")
    assert res["n_total"] == 3
    assert res["n_wins"] == 2
    assert res["n_losses"] == 1
    assert res["wr_pct"] == pytest.approx(66.67, abs=0.1)
    assert res["pips_net"] == pytest.approx(42.0, abs=0.1)
    assert res["max_pips"] == 25.0
    assert res["min_pips"] == -8.0


def test_save_journal(tmp_path, monkeypatch):
    """save_journal ecrit le fichier JSON."""
    from scripts.v9_trade_journal import save_journal
    journal_dir = tmp_path / "trade_journal"
    monkeypatch.setattr("scripts.v9_trade_journal.JOURNAL_DIR", journal_dir)
    aggregated = {
        "day": "2026-07-31",
        "n_total": 3, "n_wins": 2, "n_losses": 1,
        "wr_pct": 66.67, "pips_net": 42.0,
    }
    path = save_journal(aggregated)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["day"] == "2026-07-31"


# === v9_daily_summary ===

def test_build_summary_contains_sections(monkeypatch):
    """build_summary contient les sections obligatoires."""
    from scripts.v9_daily_summary import build_summary
    monkeypatch.setattr(
        "scripts.v9_daily_summary._load_latest_journal", lambda day: None,
    )
    monkeypatch.setattr(
        "scripts.v9_daily_summary._get_streaks",
        lambda: {"streaks": {"current_streak": 0, "current_type": "none",
                              "max_win_streak": 0, "max_loss_streak": 0,
                              "n_total": 0},
                  "recommendation": "OK"},
    )
    monkeypatch.setattr(
        "scripts.v9_daily_summary._get_performance",
        lambda days=7: {"error": "no_data"},
    )
    summary = build_summary("2026-07-31")
    assert "V9 Daily Summary" in summary
    assert "Trades du jour" in summary
    assert "Win Streak" in summary
    assert "Performance" in summary
    assert "Edge Baseline" in summary


def test_save_summary(tmp_path, monkeypatch):
    """save_summary cree .md et .txt."""
    from scripts.v9_daily_summary import save_summary
    summary_dir = tmp_path / "daily_summary"
    monkeypatch.setattr("scripts.v9_daily_summary.SUMMARY_DIR", summary_dir)
    md, txt = save_summary("2026-07-31", "# Test summary")
    assert md.exists()
    assert txt.exists()


def test_load_latest_journal_missing(tmp_path, monkeypatch):
    """_load_latest_journal retourne None si journal absent."""
    import scripts.v9_daily_summary as ds
    # Patch JOURNAL_DIR dans v9_trade_journal (reference partagee)
    monkeypatch.setattr(
        "scripts.v9_trade_journal.JOURNAL_DIR",
        tmp_path / "absent",
    )
    assert ds._load_latest_journal("2026-07-31") is None


# === v9_edge_momentum ===

def test_get_weekly_stats_db_missing(tmp_path):
    """get_weekly_stats sur DB absente → error."""
    from scripts.v9_edge_momentum import get_weekly_stats
    res = get_weekly_stats(tmp_path / "absent.db")
    assert res["error"] == "db_missing"


def test_get_weekly_stats_no_data(tmp_path):
    """get_weekly_stats sans data → n_total=0."""
    from scripts.v9_edge_momentum import get_weekly_stats
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, opened_at TEXT, closed_at TEXT,
                pips_brut REAL, pips_net REAL
            )
        """)
        conn.commit()
    res = get_weekly_stats(db, days_ago=0)
    assert res["n_total"] == 0


def test_get_weekly_stats_with_data(tmp_path):
    """get_weekly_stats calcule correctement."""
    from scripts.v9_edge_momentum import get_weekly_stats
    db = tmp_path / "v9.db"
    now = datetime.now(timezone.utc)
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, opened_at TEXT, closed_at TEXT,
                pips_brut REAL, pips_net REAL
            )
        """)
        for i in range(5):
            ts = (now - timedelta(days=i)).isoformat()
            conn.execute("""
                INSERT INTO v9_paper_trades
                (symbol, opened_at, closed_at, pips_brut, pips_net)
                VALUES ('GBPUSD', ?, ?, 25.0, 23.5)
            """, (ts, ts))
        conn.commit()
    res = get_weekly_stats(db, days_ago=0)
    assert res["n_total"] >= 3  # au moins les 5 derniers jours


def test_compute_momentum_insufficient_data(tmp_path):
    """compute_momentum avec 0 semaines valides → INSUFFICIENT_DATA."""
    from scripts.v9_edge_momentum import compute_momentum
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, opened_at TEXT, closed_at TEXT,
                pips_brut REAL, pips_net REAL
            )
        """)
        conn.commit()
    res = compute_momentum(db, n_weeks=4)
    assert res["recommendation"] == "INSUFFICIENT_DATA"


def test_compute_momentum_improving(monkeypatch):
    """compute_momentum detecte EDGE_GROWING si WR croît."""
    from scripts.v9_edge_momentum import compute_momentum
    # Mock get_weekly_stats pour retourner WR croissant
    stats_sequence = [
        {"n_total": 10, "wr_pct": 50.0, "expectancy_net": 1.0, "total_pips_net": 10.0, "period": "week0"},
        {"n_total": 10, "wr_pct": 70.0, "expectancy_net": 2.0, "total_pips_net": 20.0, "period": "week1"},
        {"n_total": 10, "wr_pct": 90.0, "expectancy_net": 3.0, "total_pips_net": 30.0, "period": "week2"},
        {"n_total": 10, "wr_pct": 95.0, "expectancy_net": 5.0, "total_pips_net": 50.0, "period": "week3"},
    ]
    monkeypatch.setattr("scripts.v9_edge_momentum.get_weekly_stats",
                        lambda db, days_ago: stats_sequence[days_ago // 7])
    res = compute_momentum("/fake/db", n_weeks=4)
    assert res["recommendation"] == "EDGE_GROWING"
    assert res["trend"] == "IMPROVING"


def test_compute_momentum_degrading(monkeypatch):
    """compute_momentum detecte EDGE_FADING si WR baisse."""
    from scripts.v9_edge_momentum import compute_momentum
    stats_sequence = [
        {"n_total": 10, "wr_pct": 90.0, "expectancy_net": 5.0, "total_pips_net": 50.0, "period": "week0"},
        {"n_total": 10, "wr_pct": 70.0, "expectancy_net": 3.0, "total_pips_net": 30.0, "period": "week1"},
        {"n_total": 10, "wr_pct": 60.0, "expectancy_net": 1.0, "total_pips_net": 10.0, "period": "week2"},
        {"n_total": 10, "wr_pct": 40.0, "expectancy_net": -2.0, "total_pips_net": -20.0, "period": "week3"},
    ]
    monkeypatch.setattr("scripts.v9_edge_momentum.get_weekly_stats",
                        lambda db, days_ago: stats_sequence[days_ago // 7])
    res = compute_momentum("/fake/db", n_weeks=4)
    assert res["recommendation"] == "EDGE_FADING"
    assert res["trend"] == "DEGRADING"


def test_save_momentum(tmp_path, monkeypatch):
    """save_momentum ecrit le fichier."""
    from scripts.v9_edge_momentum import save_momentum
    momentum_dir = tmp_path / "edge_momentum"
    monkeypatch.setattr(
        "scripts.v9_edge_momentum.MOMENTUM_DIR", momentum_dir,
    )
    momentum = {
        "recommendation": "EDGE_STABLE",
        "weekly_stats": [],
        "ts": "2026-07-31T12:00:00",
    }
    path = save_momentum(momentum)
    assert path.exists()


def test_main_runs(monkeypatch, capsys):
    """CLI main execute sans erreur."""
    from scripts.v9_edge_momentum import main
    # Mock DB_PATH
    monkeypatch.setattr("core.v9.config.DB_PATH", "/nonexistent/path")
    exit_code = main(["--weeks", "4"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "EDGE MOMENTUM" in captured.out