"""tests/test_v9_p0_dash.py — P0-2 motion CEO 48h.

Tests pour dashboard enhanced.
"""
import pytest
import sqlite3


def test_render_section():
    from scripts.v9_dashboard_enhanced import render_section
    out = render_section("TEST", ["line1", "line2"])
    assert "TEST" in out
    assert "line1" in out
    assert "line2" in out


def test_main_runs_db_empty(monkeypatch, capsys):
    from scripts.v9_dashboard_enhanced import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DASHBOARD ENHANCED" in captured.out
    assert "MULTI-TIMEFRAME" in captured.out
    assert "ANTICIPATION" in captured.out
    assert "PRICE ACTION" in captured.out


def test_main_with_data(monkeypatch, capsys):
    from scripts.v9_dashboard_enhanced import main
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
    assert "PRICE ACTION" in captured.out


def test_main_compact(monkeypatch, capsys):
    from scripts.v9_dashboard_enhanced import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--mode", "compact"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DASHBOARD" in captured.out