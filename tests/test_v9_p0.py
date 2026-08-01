"""tests/test_v9_p0.py — P0 motion CEO 48h Champ libre.

Tests pour backtest_multi_tf.
"""
import pytest
import sqlite3


def test_compute_trend_unknown():
    from scripts.v9_backtest_multi_tf import compute_trend_signal
    assert compute_trend_signal([]) == "UNKNOWN"


def test_compute_trend_uptrend():
    from scripts.v9_backtest_multi_tf import compute_trend_signal
    closes = [1.30 + i * 0.001 for i in range(30)]
    assert compute_trend_signal(closes) == "UPTREND"


def test_compute_trend_downtrend():
    from scripts.v9_backtest_multi_tf import compute_trend_signal
    closes = [1.32 - i * 0.001 for i in range(30)]
    assert compute_trend_signal(closes) == "DOWNTREND"


def test_compute_trend_ranging():
    from scripts.v9_backtest_multi_tf import compute_trend_signal
    closes = [1.30] * 30
    assert compute_trend_signal(closes) == "RANGING"


def test_fetch_daily_db_missing():
    from scripts.v9_backtest_multi_tf import fetch_daily_candles
    from pathlib import Path as _P
    res = fetch_daily_candles(_P("/nonexistent/path.db"),
                                 "GBPUSD", "2026-07-01", "2026-08-01")
    assert res == []


def test_fetch_daily_with_data(tmp_path):
    from scripts.v9_backtest_multi_tf import fetch_daily_candles
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        for i in range(31):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.31, 1.29, ?, NULL)
            """, (ts, 1.30 + i * 0.001))
        conn.commit()
    res = fetch_daily_candles(db, "GBPUSD", "2026-07-01", "2026-08-01")
    assert len(res) == 31


def test_backtest_no_data():
    from scripts.v9_backtest_multi_tf import backtest_confluence
    from pathlib import Path as _P
    res = backtest_confluence("GBPUSD", _P("/nonexistent/path.db"))
    assert "error" in res


def test_backtest_with_data(tmp_path):
    from scripts.v9_backtest_multi_tf import backtest_confluence
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        # 31 jours tendance haussiere
        for i in range(31):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            close = 1.30 + i * 0.002  # +2% sur le mois
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.31, 1.29, ?, NULL)
            """, (ts, close))
        conn.commit()
    res = backtest_confluence("GBPUSD", db, confluence_threshold=0.7)
    assert "n_trades" in res
    # Au moins 1 trade (le trend est UP)
    assert res["n_trades"] >= 1


def test_backtest_threshold_blocks_ranging(tmp_path):
    """Trend RANGING doit produire 0 trades si threshold > 0."""
    from scripts.v9_backtest_multi_tf import backtest_confluence
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        # Range plat
        for i in range(31):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, 1.30, NULL)
            """, (ts,))
        conn.commit()
    res = backtest_confluence("GBPUSD", db, confluence_threshold=0.7)
    assert res["n_trades"] == 0


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_backtest_multi_tf import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "BACKTEST MULTI-TF" in captured.out


def test_main_with_data(monkeypatch, capsys):
    from scripts.v9_backtest_multi_tf import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        for i in range(31):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.31, 1.29, ?, NULL)
            """, (ts, 1.30 + i * 0.001))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "BACKTEST MULTI-TF" in captured.out