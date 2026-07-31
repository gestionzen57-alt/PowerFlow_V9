"""tests/test_v9_phase37.py — Phase 37 motion CEO 48h.

Tests pour v9_market_sentiment.
"""
import pytest
import sqlite3


def test_get_paper_trades_directional_db_missing():
    from scripts.v9_market_sentiment import get_paper_trades_directional
    res = get_paper_trades_directional("/nonexistent/path.db", days=7)
    assert res["error"] == "db_missing"


def test_get_paper_trades_directional_no_trades(tmp_path):
    from scripts.v9_market_sentiment import get_paper_trades_directional
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT, pips_net REAL, closed_at TEXT
            )
        """)
        conn.commit()
    res = get_paper_trades_directional(db, days=7)
    assert res["n_total"] == 0


def test_get_paper_trades_directional_bull(tmp_path):
    from scripts.v9_market_sentiment import get_paper_trades_directional
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT, pips_net REAL, closed_at TEXT
            )
        """)
        # 5 bull wins + 2 bear losses
        for d, p in [("haussiere", 25)] * 5 + [("baissiere", -8)] * 2:
            conn.execute("""
                INSERT INTO v9_paper_trades VALUES (NULL, ?, ?, '2026-07-31')
            """, (d, p))
        conn.commit()
    res = get_paper_trades_directional(db, days=7)
    assert res["bull_wins"] == 5
    assert res["bear_losses"] == 2
    assert res["bull_pips"] == 125.0
    assert res["bear_pips"] == -16.0


def test_compute_sentiment_bullish():
    from scripts.v9_market_sentiment import compute_sentiment
    directional = {
        "n_total": 10, "bull_pips": 200, "bear_pips": -50,
        "bull_wins": 8, "bull_losses": 0,
        "bear_wins": 1, "bear_losses": 1,
    }
    res = compute_sentiment(directional)
    assert res["sentiment"] == "BULLISH"
    assert res["score"] > 0


def test_compute_sentiment_bearish():
    from scripts.v9_market_sentiment import compute_sentiment
    directional = {
        "n_total": 10, "bull_pips": -100, "bear_pips": 200,
        "bull_wins": 1, "bull_losses": 4,
        "bear_wins": 4, "bear_losses": 1,
    }
    res = compute_sentiment(directional)
    assert res["sentiment"] == "BEARISH"
    assert res["score"] < 0


def test_compute_sentiment_neutral():
    from scripts.v9_market_sentiment import compute_sentiment
    directional = {
        "n_total": 10, "bull_pips": 100, "bear_pips": -100,
        "bull_wins": 4, "bull_losses": 1,
        "bear_wins": 4, "bear_losses": 1,
    }
    res = compute_sentiment(directional)
    assert res["sentiment"] == "NEUTRAL"


def test_compute_sentiment_empty():
    from scripts.v9_market_sentiment import compute_sentiment
    res = compute_sentiment({"n_total": 0})
    assert res["sentiment"] == "NEUTRAL"


def test_compute_sentiment_error():
    from scripts.v9_market_sentiment import compute_sentiment
    res = compute_sentiment({"error": "test"})
    assert res["sentiment"] == "NEUTRAL"


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_market_sentiment import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE v9_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT, pips_net REAL, closed_at TEXT
            )
        """)
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--days", "7"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MARKET SENTIMENT" in captured.out