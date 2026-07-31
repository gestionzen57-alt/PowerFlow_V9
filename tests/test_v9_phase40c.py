"""tests/test_v9_phase40c.py — Phase 40C motion CEO 48h.

Tests pour v9_sentiment_blacklister (Levier L15).
"""
import pytest
import sqlite3


def test_get_open_paper_trades_db_missing():
    from scripts.v9_sentiment_blacklister import get_open_paper_trades
    assert get_open_paper_trades("/nonexistent/path.db") == []


def test_get_open_paper_trades_with_db(tmp_path):
    from scripts.v9_sentiment_blacklister import get_open_paper_trades
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, direction TEXT,
                opened_at TEXT, closed_at TEXT, pips_net REAL
            )
        """)
        # 2 LONG ouverts + 1 ferme
        conn.execute("""
            INSERT INTO v9_paper_trades VALUES (NULL, 'GBPUSD', 'haussiere',
              '2026-07-31T11:00:00', NULL, NULL)
        """)
        conn.execute("""
            INSERT INTO v9_paper_trades VALUES (NULL, 'GBPUSD', 'haussiere',
              '2026-07-31T11:30:00', NULL, NULL)
        """)
        conn.execute("""
            INSERT INTO v9_paper_trades VALUES (NULL, 'GBPUSD', 'haussiere',
              '2026-07-31T10:00:00', '2026-07-31T10:30:00', 25.0)
        """)
        conn.commit()
    open_trades = get_open_paper_trades(db)
    assert len(open_trades) == 2


def test_apply_l15_no_blacklist_neutral():
    """L15 : sentiment NEUTRAL → no blacklist."""
    from scripts.v9_sentiment_blacklister import apply_l15_blacklist
    sentiment_data = {
        "sentiment": {"sentiment": "NEUTRAL", "score": 0.0},
        "directional": {"n_total": 10},
    }
    res = apply_l15_blacklist("/nonexistent/path.db", sentiment_data,
                                score_threshold=-0.5)
    assert res["applied"] is False
    assert res["n_blacklisted"] == 0


def test_apply_l15_blacklist_bearish(tmp_path):
    """L15 : sentiment BEARISH → blacklist LONG trades."""
    from scripts.v9_sentiment_blacklister import apply_l15_blacklist
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, direction TEXT,
                opened_at TEXT, closed_at TEXT, pips_net REAL
            )
        """)
        conn.execute("""
            INSERT INTO v9_paper_trades VALUES (NULL, 'GBPUSD', 'haussiere',
              '2026-07-31T11:00:00', NULL, NULL)
        """)
        conn.execute("""
            INSERT INTO v9_paper_trades VALUES (NULL, 'GBPUSD', 'baissiere',
              '2026-07-31T11:30:00', NULL, NULL)
        """)
        conn.commit()
    sentiment_data = {
        "sentiment": {"sentiment": "BEARISH", "score": -0.7},
        "directional": {"n_total": 10},
    }
    res = apply_l15_blacklist(db, sentiment_data, score_threshold=-0.5)
    assert res["applied"] is True
    assert res["n_blacklisted"] == 1  # 1 LONG (haussiere)
    assert res["sentiment"] == "BEARISH"


def test_apply_l15_bullish_no_blacklist():
    """L15 : sentiment BULLISH → no blacklist."""
    from scripts.v9_sentiment_blacklister import apply_l15_blacklist
    sentiment_data = {
        "sentiment": {"sentiment": "BULLISH", "score": 0.6},
        "directional": {"n_total": 10},
    }
    res = apply_l15_blacklist("/nonexistent/path.db", sentiment_data,
                                score_threshold=-0.5)
    assert res["applied"] is False


def test_apply_l15_db_missing():
    """L15 : DB absente → no blacklist (degrade)."""
    from scripts.v9_sentiment_blacklister import apply_l15_blacklist
    sentiment_data = {
        "sentiment": {"sentiment": "BEARISH", "score": -0.7},
        "directional": {"n_total": 10},
    }
    res = apply_l15_blacklist("/nonexistent/path.db", sentiment_data,
                                score_threshold=-0.5)
    assert res["applied"] is False
    assert res["reason"] == "DB missing"


def test_get_recent_sentiment_db_missing():
    from scripts.v9_sentiment_blacklister import get_recent_sentiment
    res = get_recent_sentiment("/nonexistent/path.db")
    assert "sentiment" in res


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_sentiment_blacklister import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, direction TEXT,
                opened_at TEXT, closed_at TEXT, pips_net REAL
            )
        """)
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--days", "7"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LEVIER L15" in captured.out