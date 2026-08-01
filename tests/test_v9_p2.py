"""tests/test_v9_p2.py — P2-3/P2-4 motion CEO 48h.

Tests pour backtest_engine + order_flow.
"""
import pytest
import sqlite3


# === Backtest ===

def test_compute_metrics_empty():
    from scripts.v9_backtest_engine import compute_metrics
    res = compute_metrics([])
    assert res["n_trades"] == 0


def test_compute_metrics_basic():
    from scripts.v9_backtest_engine import compute_metrics
    pips = [25.0, -8.0, 30.0, -10.0]
    res = compute_metrics(pips)
    assert res["n_trades"] == 4
    assert res["wr"] == 0.5


def test_compute_metrics_with_dates():
    from scripts.v9_backtest_engine import compute_metrics
    pips = [25.0, -8.0, 30.0, -10.0, 15.0]
    dates = ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04",
              "2026-07-05"]
    res = compute_metrics(pips, dates=dates)
    assert res["n_trades"] == 5


def test_compute_metrics_drawdown():
    from scripts.v9_backtest_engine import compute_metrics
    # Suite avec gros drawdown
    pips = [25.0, -8.0, 25.0, -8.0, -50.0, 25.0]
    res = compute_metrics(pips)
    assert res["max_dd"] < 0


def test_run_backtest_no_data():
    from scripts.v9_backtest_engine import run_backtest
    from pathlib import Path as _P
    res = run_backtest("GBPUSD", _P("/nonexistent/path.db"))
    assert "error" in res


def test_run_backtest_with_data(tmp_path):
    from scripts.v9_backtest_engine import run_backtest
    db = tmp_path / "v9.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""
            CREATE TABLE candles_d (
                id INTEGER, symbol TEXT, timestamp TEXT,
                open REAL, high REAL, low REAL, close REAL, volume INTEGER
            )
        """)
        # 60 jours pour backtest
        for i in range(60):
            ts = f"2026-06-{i+1:02d}T00:00:00" if i < 30 else f"2026-07-{i-29:02d}T00:00:00"
            close = 1.30 + (i % 10) * 0.001
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, ?, NULL)
            """, (ts, close))
        conn.commit()
    res = run_backtest("GBPUSD", db)
    assert "n_trades" in res


def test_main_backtest_runs(monkeypatch, capsys):
    from scripts.v9_backtest_engine import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "BACKTEST" in captured.out


def test_main_with_data(monkeypatch, capsys):
    from scripts.v9_backtest_engine import main
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
        for i in range(60):
            ts = f"2026-06-{i+1:02d}T00:00:00" if i < 30 else f"2026-07-{i-29:02d}T00:00:00"
            conn.execute("""
                INSERT INTO candles_d VALUES
                (NULL, 'GBPUSD', ?, 1.30, 1.305, 1.295, ?, NULL)
            """, (ts, 1.30 + (i % 10) * 0.001))
        conn.commit()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--symbol", "GBPUSD"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "BACKTEST" in captured.out


# === Order flow ===

def test_detect_iceberg_no_data():
    from scripts.v9_order_flow_institution import detect_iceberg_orders
    res = detect_iceberg_orders([])
    assert "error" in res


def test_detect_iceberg_basic():
    from scripts.v9_order_flow_institution import detect_iceberg_orders
    # Trade split pattern : 5 trades meme prix, meme size
    trades = [
        {"price": 1.30, "size": 1.0, "side": "BUY", "ts": i}
        for i in range(5)
    ]
    res = detect_iceberg_orders(trades)
    assert "icebergs_detected" in res


def test_detect_stop_hunt_basic():
    from scripts.v9_order_flow_institution import detect_stop_hunt
    # Spike rapide haut puis retour
    prices = [1.30, 1.31, 1.33, 1.30]
    res = detect_stop_hunt(prices)
    assert "hunt_detected" in res


def test_detect_accumulation_basic():
    from scripts.v9_order_flow_institution import detect_accumulation
    # Accumulation : prices stables + gros volume
    trades = [
        {"price": 1.30 + i * 0.0001, "size": 100, "side": "BUY"}
        for i in range(10)
    ]
    res = detect_accumulation(trades)
    assert "accumulation_score" in res


def test_order_book_pressure_basic():
    from scripts.v9_order_flow_institution import order_book_pressure
    res = order_book_pressure(bid_volume=800, ask_volume=300)
    assert res["pressure"] == "STRONG_BID"


def test_order_book_pressure_neutral():
    from scripts.v9_order_flow_institution import order_book_pressure
    res = order_book_pressure(bid_volume=500, ask_volume=500)
    assert res["pressure"] == "NEUTRAL"


def test_main_order_flow_runs(capsys):
    from scripts.v9_order_flow_institution import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ORDER FLOW" in captured.out