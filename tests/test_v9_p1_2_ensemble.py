"""tests/test_v9_p1_2_ensemble.py — P1-2 motion CEO 48h.

Tests pour price_action_ensemble (L16/L17).
"""
import pytest
import sqlite3


def test_load_candles_db_missing():
    from scripts.v9_price_action_ensemble import _load_candles
    from pathlib import Path as _P
    res = _load_candles(_P("/nonexistent/path.db"), "GBPUSD", "D", 5)
    assert res == ([], [], [], [])


def test_load_candles_with_data(tmp_path):
    from scripts.v9_price_action_ensemble import _load_candles
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        for i in range(5):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.31, 1.29, ?, NULL)
            """, (ts, 1.30 + i * 0.001))
        conn.commit()
    res = _load_candles(db, "GBPUSD", "D", 5)
    assert len(res[0]) == 5


def test_lever_l16_no_data():
    from scripts.v9_price_action_ensemble import lever_signal_l16
    from pathlib import Path as _P
    res = lever_signal_l16("GBPUSD", _P("/nonexistent/path.db"))
    assert "label" in res


def test_lever_l17_no_data():
    from scripts.v9_price_action_ensemble import lever_signal_l17
    from pathlib import Path as _P
    res = lever_signal_l17("GBPUSD", _P("/nonexistent/path.db"))
    assert "label" in res


def test_compute_enhanced_ensemble(tmp_path):
    from scripts.v9_price_action_ensemble import compute_enhanced_ensemble
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        for tf in ["d", "h4"]:
            conn.execute(f"""
                CREATE TABLE candles_{tf} (
                    id INTEGER, symbol TEXT, timestamp TEXT,
                    open REAL, high REAL, low REAL, close REAL, volume INTEGER
                )
            """)
        # 5 bougies daily range plat
        for i in range(5):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, 1.30, NULL)
            """, (ts,))
            conn.execute("""
                INSERT INTO candles_h4 VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, 1.30, NULL)
            """, (ts,))
        conn.commit()
    res = compute_enhanced_ensemble("GBPUSD", 12, 4, "FAVORABLE", 0.0, db)
    assert "decision" in res
    assert res["n_leviers"] >= 8  # 6 de base + L16 + L17


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_price_action_ensemble import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ENHANCED ENSEMBLE" in captured.out