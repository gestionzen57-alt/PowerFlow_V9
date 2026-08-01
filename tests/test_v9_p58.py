"""tests/test_v9_p58.py — Phase 58 motion CEO validée.

Tests pour mt4_candle_bridge.
"""
import pytest
import sqlite3


def test_init_candles_table():
    from scripts.v9_mt4_candle_bridge import init_candles_table
    conn = sqlite3.connect(":memory:")
    init_candles_table(conn, "d")
    row = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='candles_d'
    """).fetchone()
    assert row is not None
    conn.close()


def test_parse_candle_line_empty():
    from scripts.v9_mt4_candle_bridge import parse_candle_line
    assert parse_candle_line("") is None


def test_parse_candle_line_header():
    from scripts.v9_mt4_candle_bridge import parse_candle_line
    assert parse_candle_line("SYMBOL,TF,TIMESTAMP,O,H,L,C,V") is None


def test_parse_candle_line_valid():
    from scripts.v9_mt4_candle_bridge import parse_candle_line
    res = parse_candle_line("GBPUSD,M1,2026-07-31T12:00:00,1.3000,1.3010,1.2990,1.3005,100")
    assert res["symbol"] == "GBPUSD"
    assert res["tf"] == "M1"
    assert res["open"] == 1.3000


def test_parse_candle_line_invalid():
    from scripts.v9_mt4_candle_bridge import parse_candle_line
    assert parse_candle_line("GBPUSD,M1,2026-07-31T12:00:00,1.3000") is None


def test_scan_bridge_dir_empty(tmp_path):
    from scripts.v9_mt4_candle_bridge import scan_bridge_dir
    assert scan_bridge_dir(tmp_path) == []


def test_scan_bridge_dir_with_files(tmp_path):
    from scripts.v9_mt4_candle_bridge import scan_bridge_dir
    (tmp_path / "candles_2026.csv").write_text("header\n")
    (tmp_path / "candles_2026.txt").write_text("header\n")
    files = scan_bridge_dir(tmp_path)
    assert len(files) == 2


def test_insert_candle_idempotent():
    from scripts.v9_mt4_candle_bridge import (
        init_candles_table, insert_candle,
    )
    conn = sqlite3.connect(":memory:")
    init_candles_table(conn, "d")
    ok1 = insert_candle(conn, "D", "GBPUSD", "2026-07-31T00:00:00",
                          1.30, 1.31, 1.29, 1.305, 100)
    ok2 = insert_candle(conn, "D", "GBPUSD", "2026-07-31T00:00:00",
                          1.40, 1.41, 1.39, 1.405, 200)
    assert ok1 is True
    assert ok2 is True
    row = conn.execute("SELECT close, volume FROM candles_d").fetchone()
    assert row[0] == 1.305  # garde l'original
    assert row[1] == 100


def test_bridge_ingest_no_files(tmp_path):
    from scripts.v9_mt4_candle_bridge import bridge_ingest
    db = tmp_path / "v9.db"
    res = bridge_ingest(tmp_path, db)
    assert "error" in res


def test_bridge_ingest_no_db(tmp_path):
    from scripts.v9_mt4_candle_bridge import bridge_ingest
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    (bridge / "candles.csv").write_text("header\n")
    res = bridge_ingest(bridge, tmp_path / "nonexistent.db")
    assert "error" in res


def test_bridge_ingest_with_data(tmp_path):
    from scripts.v9_mt4_candle_bridge import bridge_ingest
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    db = tmp_path / "v9.db"
    db.touch()  # create the file
    # CSV with 5 candles
    csv_content = (
        "SYMBOL,TF,TIMESTAMP,OPEN,HIGH,LOW,CLOSE,VOLUME\n"
        "GBPUSD,M1,2026-07-31T12:00:00,1.3000,1.3010,1.2990,1.3005,100\n"
        "GBPUSD,M1,2026-07-31T12:01:00,1.3005,1.3015,1.2995,1.3010,150\n"
        "GBPUSD,M1,2026-07-31T12:02:00,1.3010,1.3020,1.3000,1.3015,200\n"
        "GBPUSD,M5,2026-07-31T12:00:00,1.3000,1.3020,1.2990,1.3015,500\n"
        "EURUSD,M15,2026-07-31T12:00:00,1.0850,1.0860,1.0840,1.0855,300\n"
    )
    (bridge / "candles.csv").write_text(csv_content)
    res = bridge_ingest(bridge, db)
    assert "inserted" in res
    assert res["inserted"] == 5
    assert "m1" in res["by_tf"]
    assert "m5" in res["by_tf"]
    assert "GBPUSD" in res["by_symbol"]
    assert "EURUSD" in res["by_symbol"]


def test_bridge_ingest_invalid_lines(tmp_path):
    from scripts.v9_mt4_candle_bridge import bridge_ingest
    bridge = tmp_path / "bridge"
    bridge.mkdir()
    db = tmp_path / "v9.db"
    db.touch()
    csv_content = (
        "SYMBOL,TF,TIMESTAMP,OPEN,HIGH,LOW,CLOSE,VOLUME\n"
        "GBPUSD,M1,2026-07-31T12:00:00,1.3000,1.3010,1.2990,1.3005,100\n"
        "BADLINE\n"
        "GBPUSD,XX1,2026-07-31T12:00:00,1.3000,1.3010,1.2990,1.3005,100\n"
    )
    (bridge / "candles.csv").write_text(csv_content)
    res = bridge_ingest(bridge, db)
    assert res["inserted"] == 1
    assert res["invalid"] == 1


def test_main_runs_no_files(monkeypatch, capsys):
    from scripts.v9_mt4_candle_bridge import main
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--bridge-dir", str(d)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "MT4 CANDLE BRIDGE" in captured.out


def test_main_with_data(monkeypatch, capsys):
    from scripts.v9_mt4_candle_bridge import main
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    bridge = d / "bridge"
    bridge.mkdir()
    db = d / "v9.db"
    db.touch()
    (bridge / "candles.csv").write_text(
        "SYMBOL,TF,TIMESTAMP,OPEN,HIGH,LOW,CLOSE,VOLUME\n"
        "GBPUSD,M1,2026-07-31T12:00:00,1.3000,1.3010,1.2990,1.3005,100\n"
    )
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--bridge-dir", str(bridge)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MT4 CANDLE BRIDGE" in captured.out