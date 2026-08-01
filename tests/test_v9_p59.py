"""tests/test_v9_p59.py — Phase 59 motion CEO validée.

Tests pour oos_validator.
"""
import pytest
import sqlite3


def test_compute_trend_unknown():
    from scripts.v9_oos_validator import compute_trend
    assert compute_trend([]) == "UNKNOWN"


def test_compute_trend_uptrend():
    from scripts.v9_oos_validator import compute_trend
    closes = [1.30 + i * 0.001 for i in range(30)]
    assert compute_trend(closes) == "UPTREND"


def test_compute_trend_downtrend():
    from scripts.v9_oos_validator import compute_trend
    closes = [1.32 - i * 0.001 for i in range(30)]
    assert compute_trend(closes) == "DOWNTREND"


def test_compute_trend_ranging():
    from scripts.v9_oos_validator import compute_trend
    closes = [1.30] * 30
    assert compute_trend(closes) == "RANGING"


def test_fetch_candles_db_missing():
    from scripts.v9_oos_validator import fetch_candles
    from pathlib import Path as _P
    res = fetch_candles(_P("/nonexistent/path.db"), "GBPUSD", n=90)
    assert res == []


def test_fetch_candles_with_data(tmp_path):
    from scripts.v9_oos_validator import fetch_candles
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        for i in range(90):
            ts = f"2026-05-{i+1:02d}T00:00:00" if i < 31 else (
                f"2026-06-{i-30:02d}T00:00:00" if i < 61 else
                f"2026-07-{i-60:02d}T00:00:00"
            )
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.31, 1.29, ?, NULL)
            """, (ts, 1.30 + i * 0.001))
        conn.commit()
    res = fetch_candles(db, "GBPUSD", n=90)
    assert len(res) == 90


def test_walk_forward_no_data():
    from scripts.v9_oos_validator import walk_forward_validate
    from pathlib import Path as _P
    res = walk_forward_validate("GBPUSD", _P("/nonexistent/path.db"))
    assert "error" in res


def test_walk_forward_insufficient():
    from scripts.v9_oos_validator import walk_forward_validate
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    res = walk_forward_validate("GBPUSD", db)
    assert "error" in res


def test_walk_forward_with_data(tmp_path):
    from scripts.v9_oos_validator import walk_forward_validate
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        for i in range(90):
            day = (i % 30) + 1
            month = ((i // 30) + 5)
            ts = f"2026-{month:02d}-{day:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.31, 1.29, ?, NULL)
            """, (ts, 1.30 + i * 0.002))
        conn.commit()
    res = walk_forward_validate("GBPUSD", db)
    assert "verdict" in res


def test_main_no_data(monkeypatch, capsys):
    from scripts.v9_oos_validator import main
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "OOS VALIDATOR" in captured.out


def test_main_with_data(monkeypatch, capsys):
    from scripts.v9_oos_validator import main
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
        for i in range(90):
            day = (i % 30) + 1
            month = ((i // 30) + 5)
            ts = f"2026-{month:02d}-{day:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.31, 1.29, ?, NULL)
            """, (ts, 1.30 + i * 0.002))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "VERDICT" in captured.out