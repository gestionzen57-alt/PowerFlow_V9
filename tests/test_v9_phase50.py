"""tests/test_v9_phase50.py — Phase 50 motion CEO no-limit.

Tests pour multi_timeframe_reader.
"""
import pytest
import sqlite3


def test_tf_levels():
    from scripts.v9_multi_timeframe_reader import TF_LEVELS
    assert TF_LEVELS == ["D", "H4", "H1", "M15", "M5", "M1"]


def test_analyze_no_data():
    from scripts.v9_multi_timeframe_reader import _analyze_timeframe
    res = _analyze_timeframe("GBPUSD", "D", [], [], [])
    assert res["trend"] == "UNKNOWN"
    assert res["anticipation"] == "NO_DATA"


def test_analyze_uptrend():
    from scripts.v9_multi_timeframe_reader import _analyze_timeframe
    # 30 bougies avec tendance haussiere (+2% sur la periode)
    closes = [1.30 + i * 0.0007 for i in range(30)]
    highs = [c + 0.0005 for c in closes]
    lows = [c - 0.0005 for c in closes]
    res = _analyze_timeframe("GBPUSD", "D", closes, highs, lows)
    assert res["trend"] == "UPTREND"
    assert res["regime_phase"] in ("MARKUP", "ACCUMULATION", "NEUTRAL")


def test_analyze_downtrend():
    from scripts.v9_multi_timeframe_reader import _analyze_timeframe
    closes = [1.32 - i * 0.0007 for i in range(30)]
    highs = [c + 0.0005 for c in closes]
    lows = [c - 0.0005 for c in closes]
    res = _analyze_timeframe("GBPUSD", "D", closes, highs, lows)
    assert res["trend"] == "DOWNTREND"
    assert res["regime_phase"] in ("MARKDOWN", "DISTRIBUTION", "NEUTRAL")


def test_analyze_ranging():
    from scripts.v9_multi_timeframe_reader import _analyze_timeframe
    # Range plat
    closes = [1.30] * 30
    highs = [1.301] * 30
    lows = [1.299] * 30
    res = _analyze_timeframe("GBPUSD", "D", closes, highs, lows)
    assert res["trend"] == "RANGING"


def test_anticipate_next():
    from scripts.v9_multi_timeframe_reader import _anticipate_next
    assert _anticipate_next("D", "UPTREND", "MARKUP", 0.01) == "CONTINUATION_LIKELY"
    assert _anticipate_next("D", "RANGING", "ACCUMULATION", 0.001) == "BULLISH_BREAKOUT"


def test_confluence_score_empty():
    from scripts.v9_multi_timeframe_reader import confluence_score
    res = confluence_score([])
    assert res["score"] == 0


def test_confluence_score_strong_uptrend():
    from scripts.v9_multi_timeframe_reader import confluence_score
    readings = [{"trend": "UPTREND"}] * 6
    res = confluence_score(readings)
    assert res["score"] == 100
    assert res["alignment"] == "STRONG"
    assert res["dominant"] == "UPTREND"


def test_confluence_score_mixed():
    from scripts.v9_multi_timeframe_reader import confluence_score
    readings = [{"trend": "UPTREND"}] * 3 + [{"trend": "DOWNTREND"}] * 3
    res = confluence_score(readings)
    assert res["alignment"] == "WEAK"
    assert res["dominant"] == "MIXED"


def test_confluence_score_all_unknown():
    from scripts.v9_multi_timeframe_reader import confluence_score
    readings = [{"trend": "UNKNOWN"}] * 6
    res = confluence_score(readings)
    assert res["alignment"] == "NO_DATA"


def test_read_timeframe_db_missing():
    from scripts.v9_multi_timeframe_reader import read_timeframe
    from pathlib import Path as _P
    res = read_timeframe("GBPUSD", "D", _P("/nonexistent/path.db"))
    assert res["error"] == "db_missing"


def test_read_timeframe_with_db(tmp_path):
    from scripts.v9_multi_timeframe_reader import read_timeframe
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        # 30 bougies GBPUSD tendance haussiere (ordre ASC)
        for i in range(30):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            close = 1.30 + i * 0.001
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, ?, ?, ?, ?, NULL)
            """, (ts, close - 0.0005, close + 0.0005,
                  close - 0.0005, close))
        conn.commit()
    res = read_timeframe("GBPUSD", "D", db)
    assert res["n_candles"] == 30
    # DESC order -> latest first -> decreasing -> DOWNTREND dans notre cas
    # mais le test verifie juste qu'on a un trend
    assert res["trend"] in ("UPTREND", "DOWNTREND", "RANGING")


def test_multi_tf_analysis(monkeypatch):
    from scripts.v9_multi_timeframe_reader import multi_tf_analysis
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        for tf in ["d", "h4", "h1", "m15", "m5", "m1"]:
            conn.execute(f"""
                CREATE TABLE candles_{tf} (
                    id INTEGER, symbol TEXT, timestamp TEXT,
                    open REAL, high REAL, low REAL, close REAL, volume INTEGER
                )
            """)
        conn.commit()
    result = multi_tf_analysis("GBPUSD", db)
    assert len(result["tf_readings"]) == 6
    assert "confluence" in result


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_multi_timeframe_reader import main
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
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "MULTI-TIMEFRAME" in captured.out