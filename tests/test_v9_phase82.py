"""tests/test_v9_phase82.py — Phase 82 motion CEO 48H (post-Plan C).

Tests pour live_data_integration.
"""
import pytest
from pathlib import Path


def test_required_tables_defined():
    from scripts.v9_live_data_integration import REQUIRED_TABLES
    assert "candles_d" in REQUIRED_TABLES
    assert "candles_h4" in REQUIRED_TABLES
    assert "candles_h1" in REQUIRED_TABLES
    assert "candles_m15" in REQUIRED_TABLES
    assert "candles_m5" in REQUIRED_TABLES
    assert "candles_m1" in REQUIRED_TABLES


def test_required_columns():
    from scripts.v9_live_data_integration import REQUIRED_COLUMNS
    assert "symbol" in REQUIRED_COLUMNS
    assert "tf" in REQUIRED_COLUMNS
    assert "timestamp" in REQUIRED_COLUMNS
    assert "open" in REQUIRED_COLUMNS
    assert "high" in REQUIRED_COLUMNS
    assert "low" in REQUIRED_COLUMNS
    assert "close" in REQUIRED_COLUMNS


def test_init_candles_tables(tmp_path):
    from scripts.v9_live_data_integration import init_candles_tables
    db = tmp_path / "v9.db"
    db.touch()
    ok = init_candles_tables(db)
    assert ok is True
    # Verifier que les tables existent
    import sqlite3
    with sqlite3.connect(str(db)) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = [t[0] for t in tables]
        assert "candles_d" in names
        assert "candles_h1" in names


def test_ingest_candles_batch(tmp_path):
    from scripts.v9_live_data_integration import (
        init_candles_tables, ingest_candles_batch,
    )
    db = tmp_path / "v9.db"
    db.touch()
    init_candles_tables(db)
    candles = [
        {"timestamp": "2026-07-31T12:00:00", "open": 1.30,
         "high": 1.301, "low": 1.299, "close": 1.3005},
        {"timestamp": "2026-07-31T13:00:00", "open": 1.301,
         "high": 1.302, "low": 1.300, "close": 1.3015},
    ]
    n = ingest_candles_batch(db, "GBPUSD", "h1", candles)
    assert n == 2


def test_ingest_invalid_tf():
    from scripts.v9_live_data_integration import ingest_candles_batch
    n = ingest_candles_batch(
        Path("nonexistent.db"), "GBPUSD", "invalid",
        [{"timestamp": "t", "open": 1, "high": 1, "low": 1, "close": 1}],
    )
    assert n == 0


def test_ingest_idempotent_replace(tmp_path):
    from scripts.v9_live_data_integration import (
        init_candles_tables, ingest_candles_batch, query_candles,
    )
    db = tmp_path / "v9.db"
    db.touch()
    init_candles_tables(db)
    candle = {"timestamp": "2026-07-31T12:00:00", "open": 1.30,
              "high": 1.301, "low": 1.299, "close": 1.3005}
    ingest_candles_batch(db, "GBPUSD", "h1", [candle])
    ingest_candles_batch(db, "GBPUSD", "h1", [candle])  # replace
    rows = query_candles(db, "GBPUSD", "h1", limit=10)
    assert len(rows) == 1


def test_query_candles_empty_db(tmp_path):
    from scripts.v9_live_data_integration import (
        init_candles_tables, query_candles,
    )
    db = tmp_path / "v9.db"
    db.touch()
    init_candles_tables(db)
    rows = query_candles(db, "GBPUSD", "h1", limit=10)
    assert rows == []


def test_query_candles_invalid_tf(tmp_path):
    from scripts.v9_live_data_integration import (
        init_candles_tables, query_candles,
    )
    db = tmp_path / "v9.db"
    db.touch()
    init_candles_tables(db)
    rows = query_candles(db, "GBPUSD", "invalid", limit=10)
    assert rows == []


def test_verify_pipeline_all_tf(tmp_path):
    from scripts.v9_live_data_integration import (
        init_candles_tables, ingest_candles_batch, verify_pipeline,
    )
    db = tmp_path / "v9.db"
    db.touch()
    init_candles_tables(db)
    for tf in ["d", "h4", "h1", "m15", "m5", "m1"]:
        candles = [
            {"timestamp": f"2026-07-31T{12 + i:02d}:00:00",
             "open": 1.30, "high": 1.301, "low": 1.299, "close": 1.3005}
            for i in range(5)
        ]
        ingest_candles_batch(db, "GBPUSD", tf, candles)
    res = verify_pipeline(db, "GBPUSD")
    assert res["all_tf_have_data"] is True
    assert res["total_candles"] == 30


def test_verify_pipeline_empty(tmp_path):
    from scripts.v9_live_data_integration import (
        init_candles_tables, verify_pipeline,
    )
    db = tmp_path / "v9.db"
    db.touch()
    init_candles_tables(db)
    res = verify_pipeline(db, "GBPUSD")
    assert res["all_tf_have_data"] is False
    assert res["total_candles"] == 0


def test_main_demo(capsys, tmp_path):
    from scripts.v9_live_data_integration import main
    db = tmp_path / "v9_test.db"
    db.touch()
    exit_code = main(["--db-path", str(db)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LIVE DATA INTEGRATION" in captured.out