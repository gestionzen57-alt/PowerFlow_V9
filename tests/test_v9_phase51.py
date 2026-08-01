"""tests/test_v9_phase51.py — Phase 51 motion CEO no-limit.

Tests pour july_2026_analysis.
"""
import pytest
import sqlite3


def test_symbols_list():
    from scripts.v9_july_2026_analysis import SYMBOLS
    assert "GBPUSD" in SYMBOLS
    assert "EURUSD" in SYMBOLS
    assert len(SYMBOLS) >= 5


def test_get_july_summary_db_missing():
    from scripts.v9_july_2026_analysis import get_july_summary
    from pathlib import Path as _P
    res = get_july_summary(_P("/nonexistent/path.db"), "GBPUSD")
    assert res["error"] == "db_missing"


def test_get_july_summary_no_table():
    from scripts.v9_july_2026_analysis import get_july_summary
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    res = get_july_summary(db, "GBPUSD")
    assert "error" in res


def test_get_july_summary_with_data(tmp_path):
    from scripts.v9_july_2026_analysis import get_july_summary
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
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, 1.30, NULL)
            """, (ts,))
        conn.commit()
    res = get_july_summary(db, "GBPUSD")
    assert res["symbol"] == "GBPUSD"
    assert res["n_candles"] == 31


def test_weekly_breakdown_db_missing():
    from scripts.v9_july_2026_analysis import weekly_breakdown
    from pathlib import Path as _P
    res = weekly_breakdown(_P("/nonexistent/path.db"), "GBPUSD")
    assert res == []


def test_weekly_breakdown_with_data(tmp_path):
    from scripts.v9_july_2026_analysis import weekly_breakdown
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        # W27 (2026-07-06 to 07-12) - haussiere
        for i, day in enumerate([6, 7, 8, 9, 10, 11, 12]):
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.301, 1.299,
                  ?, NULL)
            """, (f"2026-07-{day:02d}T00:00:00", 1.30 + i * 0.001))
        conn.commit()
    weeks = weekly_breakdown(db, "GBPUSD")
    # Au moins W27 a des data
    w27 = [w for w in weeks if w["week"] == "W27"]
    assert len(w27) == 1


def test_monthly_behavior():
    from scripts.v9_july_2026_analysis import monthly_behavior
    from pathlib import Path as _P
    res = monthly_behavior(_P("/nonexistent/path.db"))
    assert res["n_symbols"] == 0


def test_july_weekly_summary_no_data():
    from scripts.v9_july_2026_analysis import july_weekly_summary
    from pathlib import Path as _P
    res = july_weekly_summary(_P("/nonexistent/path.db"), "GBPUSD")
    assert res["n_up_weeks"] == 0
    assert res["trend"] == "NEUTRAL"


def test_july_weekly_summary_bullish(tmp_path):
    from scripts.v9_july_2026_analysis import july_weekly_summary
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        # W27 : haussiere
        for i, day in enumerate([6, 7, 8, 9, 10, 11, 12]):
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.31, 1.29, ?, NULL)
            """, (f"2026-07-{day:02d}T00:00:00", 1.30 + i * 0.001))
        conn.commit()
    res = july_weekly_summary(db, "GBPUSD")
    assert res["n_up_weeks"] >= 1


def test_anticipate_august():
    from scripts.v9_july_2026_analysis import anticipate_august
    res = anticipate_august()
    assert res["month_in"] == "2026-08"
    assert "NFP_USD" in str(res["drivers"])
    assert "USD_CONTINUE_BEARISH" in res["scenarios"]


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_july_2026_analysis import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()  # db vide
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "JUILLET 2026" in captured.out


def test_main_with_symbol(monkeypatch, capsys):
    from scripts.v9_july_2026_analysis import main
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
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, 1.30, NULL)
            """, (ts,))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Detail semaines" in captured.out