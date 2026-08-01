"""tests/test_v9_p1_ingest.py — P1-1 motion CEO 48h.

Tests pour live_candle_ingest.
"""
import pytest
import sqlite3


def test_init_candles_table():
    from scripts.v9_live_candle_ingest import init_candles_table
    import sqlite3
    conn = sqlite3.connect(":memory:")
    init_candles_table(conn, "d")
    row = conn.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name='candles_d'
    """).fetchone()
    assert row is not None
    conn.close()


def test_init_all_tf():
    from scripts.v9_live_candle_ingest import init_candles_table
    import sqlite3
    conn = sqlite3.connect(":memory:")
    for tf in ["d", "h4", "h1", "m15", "m5", "m1"]:
        init_candles_table(conn, tf)
    tables = conn.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'candles_%'
    """).fetchall()
    assert len(tables) == 6


def test_insert_candle():
    from scripts.v9_live_candle_ingest import (
        init_candles_table, insert_candle,
    )
    import sqlite3
    conn = sqlite3.connect(":memory:")
    init_candles_table(conn, "d")
    ok = insert_candle(conn, "D", "GBPUSD", "2026-07-31T00:00:00",
                        1.30, 1.31, 1.29, 1.305, 1000)
    assert ok is True
    row = conn.execute("SELECT * FROM candles_d").fetchone()
    assert row is not None


def test_insert_candle_idempotent():
    from scripts.v9_live_candle_ingest import (
        init_candles_table, insert_candle,
    )
    import sqlite3
    conn = sqlite3.connect(":memory:")
    init_candles_table(conn, "d")
    insert_candle(conn, "D", "GBPUSD", "2026-07-31T00:00:00",
                   1.30, 1.31, 1.29, 1.305, 1000)
    # Reinsert with same key → should be ignored
    ok = insert_candle(conn, "D", "GBPUSD", "2026-07-31T00:00:00",
                        1.40, 1.41, 1.39, 1.405, 2000)
    assert ok is True
    # Close still original
    row = conn.execute("SELECT close FROM candles_d").fetchone()
    assert row[0] == 1.305


def test_read_mt4_queue_no_file():
    from scripts.v9_live_candle_ingest import read_mt4_queue
    res = read_mt4_queue()
    assert res == []


def test_simulate_candles():
    from scripts.v9_live_candle_ingest import simulate_candles
    res = simulate_candles("GBPUSD", n=30)
    assert len(res) == 30
    assert res[0]["symbol"] == "GBPUSD"


def test_ingest_db_missing():
    from scripts.v9_live_candle_ingest import ingest
    from pathlib import Path as _P
    res = ingest("GBPUSD", _P("/nonexistent/path.db"))
    assert "error" in res


def test_ingest_simulate(tmp_path):
    from scripts.v9_live_candle_ingest import ingest
    db = tmp_path / "v9.db"
    res = ingest("GBPUSD", db, simulate=True)
    # Avec simulate=True, retourne {source, n_candles, n_inserted, symbol}
    assert "source" in res
    assert res.get("source") == "simulate"
    assert res.get("n_candles") == 30


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_live_candle_ingest import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--source", "simulate"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LIVE CANDLE INGEST" in captured.out