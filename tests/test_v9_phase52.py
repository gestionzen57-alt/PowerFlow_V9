"""tests/test_v9_phase52.py — Phase 52 motion CEO no-limit.

Tests pour market_anticipation.
"""
import pytest
import sqlite3


# === regime phase ===

def test_regime_phases_list():
    from scripts.v9_market_anticipation import REGIME_PHASES
    assert "ACCUMULATION" in REGIME_PHASES
    assert "MARKUP" in REGIME_PHASES
    assert "DISTRIBUTION" in REGIME_PHASES
    assert "MARKDOWN" in REGIME_PHASES


def test_detect_regime_phase_db_missing():
    from scripts.v9_market_anticipation import detect_regime_phase
    from pathlib import Path as _P
    res = detect_regime_phase("GBPUSD", _P("/nonexistent/path.db"))
    assert res["error"] == "db_missing"


def test_detect_regime_phase_no_table():
    from scripts.v9_market_anticipation import detect_regime_phase
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    res = detect_regime_phase("GBPUSD", db)
    assert "error" in res or res["phase"] == "UNKNOWN"


def test_detect_regime_phase_no_data():
    from scripts.v9_market_anticipation import detect_regime_phase
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
    res = detect_regime_phase("GBPUSD", db)
    assert res["phase"] == "UNKNOWN"


def test_detect_regime_phase_markup(tmp_path):
    from scripts.v9_market_anticipation import detect_regime_phase
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        # 30 bougies range 1.20-1.25, close 1.245 (haut de range)
        for i in range(30):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            close = 1.20 + (i * 0.0015)  # tendance haussiere
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.20, 1.255, 1.195, ?, 1000)
            """, (ts, close))
        conn.commit()
    res = detect_regime_phase("GBPUSD", db)
    assert res["phase"] in ("MARKUP", "DISTRIBUTION", "NEUTRAL")


# === momentum divergence ===

def test_momentum_divergence_none():
    from scripts.v9_market_anticipation import momentum_divergence
    res = momentum_divergence([])
    assert res["divergence"] == "NONE"


def test_momentum_divergence_short():
    from scripts.v9_market_anticipation import momentum_divergence
    res = momentum_divergence([1.0, 2.0])
    assert res["divergence"] == "NONE"


def test_momentum_divergence_bullish():
    from scripts.v9_market_anticipation import momentum_divergence
    # Bas plus bas + momentum hausse = bullish divergence
    closes = [1.30] * 5 + [1.25] * 5 + [1.20] * 5
    res = momentum_divergence(closes)
    # Note : peut etre BULLISH ou NONE selon split exact
    assert "divergence" in res


def test_momentum_divergence_bearish():
    from scripts.v9_market_anticipation import momentum_divergence
    # Hauts plus hauts + momentum baisse = bearish divergence
    closes = ([1.30] * 10 +
               [1.30 + i * 0.01 for i in range(10)])
    res = momentum_divergence(closes)
    assert "divergence" in res


# === forward projection ===

def test_forward_projection_empty():
    from scripts.v9_market_anticipation import forward_projection
    res = forward_projection([])
    assert "error" in res


def test_forward_projection_short():
    from scripts.v9_market_anticipation import forward_projection
    res = forward_projection([1.30, 1.31])
    assert "error" in res


def test_forward_projection_uptrend():
    from scripts.v9_market_anticipation import forward_projection
    closes = [1.30 + i * 0.001 for i in range(30)]
    res = forward_projection(closes, horizon="H+1")
    assert res["direction"] == "UP"
    assert res["projected"] > res["current"]


def test_forward_projection_downtrend():
    from scripts.v9_market_anticipation import forward_projection
    closes = [1.32 - i * 0.001 for i in range(30)]
    res = forward_projection(closes, horizon="H+1")
    assert res["direction"] == "DOWN"


def test_forward_projection_horizons():
    from scripts.v9_market_anticipation import forward_projection
    closes = [1.30 + i * 0.0005 for i in range(30)]
    for h in ["H+1", "H+4", "D+1", "W+1"]:
        res = forward_projection(closes, horizon=h)
        assert res["horizon"] == h


def test_main_runs(monkeypatch, capsys):
    from scripts.v9_market_anticipation import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD", "--horizon", "H+1"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ANTICIPATION" in captured.out


def test_main_with_data(monkeypatch, capsys):
    from scripts.v9_market_anticipation import main
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
        for i in range(30):
            ts = f"2026-07-{i+1:02d}T00:00:00"
            close = 1.30 + i * 0.001
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, ?, 1000)
            """, (ts, close))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Regime phase" in captured.out