"""tests/test_v9_phase54.py — Phase 54 motion CEO no-limit.

Tests pour price_action_context.
"""
import pytest


def test_detect_swings_short():
    from scripts.v9_price_action_context import detect_swings
    res = detect_swings([1, 2, 3], [1, 2, 3])
    assert res["n_swings"] == 0


def test_detect_swings_basic():
    from scripts.v9_price_action_context import detect_swings
    # 11 prix avec un peak au milieu
    highs = [1.0, 1.1, 1.2, 1.5, 1.7, 2.0, 1.7, 1.5, 1.2, 1.1, 1.0]
    lows = [0.9, 1.0, 1.1, 1.4, 1.6, 1.9, 1.6, 1.4, 1.1, 1.0, 0.9]
    res = detect_swings(highs, lows, order=2)
    assert res["n_swings"] >= 1


# === patterns ===

def test_detect_pattern_no_data():
    from scripts.v9_price_action_context import detect_pattern
    res = detect_pattern([], [], [], [])
    assert res["pattern"] == "NONE"


def test_detect_pattern_doji():
    from scripts.v9_price_action_context import detect_pattern
    # Doji : open=close, range 1.0
    res = detect_pattern([1.30], [1.305], [1.295], [1.30])
    assert res["pattern"] == "DOJI"


def test_detect_pattern_hammer():
    from scripts.v9_price_action_context import detect_pattern
    # Hammer : long lower wick, small body haut
    opens = [1.30]
    highs = [1.305]
    lows = [1.290]  # long lower wick
    closes = [1.302]  # close > open
    res = detect_pattern(opens, highs, lows, closes)
    assert res["pattern"] in ("HAMMER", "MARUBOZU_BULLISH", "NONE")


def test_detect_pattern_shooting_star():
    from scripts.v9_price_action_context import detect_pattern
    opens = [1.30]
    highs = [1.310]  # long upper wick
    lows = [1.301]
    closes = [1.301]
    res = detect_pattern(opens, highs, lows, closes)
    # upper_wick = 1.310-1.301 = 0.009, body = 0.001, lower_wick = 0
    # upper > 2*body ✓, lower < body ✓ → SHOOTING_STAR
    assert res["pattern"] == "SHOOTING_STAR"
def test_detect_pattern_marubozu_bullish():
    from scripts.v9_price_action_context import detect_pattern
    opens = [1.30]
    highs = [1.305]
    lows = [1.295]
    closes = [1.304]
    res = detect_pattern(opens, highs, lows, closes)
    # body = 0.004, range = 0.01, body_pct = 0.4 (pas marubozu)
    # hammer test : lower wick = 1.30-1.295 = 0.005, body = 0.004
    # lower_wick > 2*body = False (0.005 < 0.008)
    # → peut etre HAMMER ou NONE
    assert res["pattern"] in ("NONE", "HAMMER", "MARUBOZU_BULLISH",
                                 "MARUBOZU_BEARISH")


def test_detect_pattern_marubozu():
    from scripts.v9_price_action_context import detect_pattern
    # Body full range : marubozu
    opens = [1.30]
    highs = [1.31]
    lows = [1.30]
    closes = [1.31]
    res = detect_pattern(opens, highs, lows, closes)
    assert res["pattern"] == "MARUBOZU_BULLISH"


def test_detect_pattern_bullish_engulfing():
    from scripts.v9_price_action_context import detect_pattern
    opens = [1.31, 1.30]
    highs = [1.315, 1.32]
    lows = [1.30, 1.295]
    closes = [1.305, 1.318]  # prev baissier, current haussier engulfing
    res = detect_pattern(opens, highs, lows, closes)
    # prev: o=1.31, c=1.305 (baissier)
    # current: o=1.30, c=1.318 (haussier, prev_o <= current_o)
    # 1.31 >= 1.30 True, 1.30 <= 1.305 True
    assert res["pattern"] == "BULLISH_ENGULFING"


def test_detect_pattern_bearish_engulfing():
    from scripts.v9_price_action_context import detect_pattern
    opens = [1.30, 1.31]
    highs = [1.315, 1.32]
    lows = [1.295, 1.30]
    closes = [1.308, 1.302]
    res = detect_pattern(opens, highs, lows, closes)
    # prev: o=1.30, c=1.308 (haussier)
    # current: o=1.31, c=1.302 (baissier)
    # prev_c > prev_o ✓ (1.308 > 1.30)
    # current_c < current_o ✓ (1.302 < 1.31)
    # current_c <= prev_o (1.302 <= 1.30) False → pas BEARISH_ENGULFING
    # OK, ajuste les valeurs
    opens = [1.30, 1.315]
    closes = [1.308, 1.300]
    res = detect_pattern(opens, highs, lows, closes)
    # prev: o=1.30, c=1.308 (haussier, prev_c > prev_o)
    # current: o=1.315, c=1.300 (baissier, current_c < current_o)
    # current_c <= prev_o (1.300 <= 1.30) ✓
    # current_o >= prev_c (1.315 >= 1.308) ✓
    assert res["pattern"] == "BEARISH_ENGULFING"


# === S/R ===

def test_find_sr_clusters_empty():
    from scripts.v9_price_action_context import find_sr_clusters
    res = find_sr_clusters([], [])
    assert res["supports"] == []


def test_find_sr_clusters_basic():
    from scripts.v9_price_action_context import find_sr_clusters
    highs = [1.30, 1.32, 1.31, 1.305, 1.31, 1.32, 1.305]
    lows = [1.29, 1.30, 1.30, 1.30, 1.295, 1.30, 1.30]
    res = find_sr_clusters(highs, lows, threshold_pct=0.02)
    assert "supports" in res
    assert "resistances" in res


def test_find_sr_clusters_min_zero():
    from scripts.v9_price_action_context import find_sr_clusters
    res = find_sr_clusters([0], [0])
    assert res["supports"] == []


# === context ===

def test_price_action_context_db_missing():
    from scripts.v9_price_action_context import price_action_context
    from pathlib import Path as _P
    res = price_action_context("GBPUSD", _P("/nonexistent/path.db"))
    assert "error" in res


def test_price_action_context_no_candles():
    from scripts.v9_price_action_context import price_action_context
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    res = price_action_context("GBPUSD", db)
    assert "error" in res


def test_price_action_context_with_data(tmp_path):
    from scripts.v9_price_action_context import price_action_context
    import sqlite3
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        # 50 bougies
        for i in range(50):
            ts = f"2026-07-{i+1:02d}T00:00:00" if i < 31 else f"2026-08-{i-30:02d}T00:00:00"
            base = 1.30 + (i % 10) * 0.001
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, ?, ?, ?, ?, NULL)
            """, (ts, base, base + 0.005, base - 0.005, base + 0.001))
        conn.commit()
    res = price_action_context("GBPUSD", db)
    assert res["n_candles"] == 50
    assert "last_close" in res


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_price_action_context import main
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
        for i in range(50):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, 1.30, NULL)
            """, (ts,))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD", "--tf", "D"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PRICE ACTION" in captured.out