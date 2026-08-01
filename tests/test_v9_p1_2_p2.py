"""tests/test_v9_p1_2_p2.py — P1-2 / P1-3 / P2-1 / P2-2 motion CEO 48h.

Tests pour kalman + news_live + cot_live.
"""
import pytest


# === Kalman ===

def test_kalman_class_init():
    from scripts.v9_kalman_forecast import KalmanFilter1D
    kf = KalmanFilter1D()
    assert kf.x == 0.0
    assert kf.v == 0.0


def test_kalman_update():
    from scripts.v9_kalman_forecast import KalmanFilter1D
    kf = KalmanFilter1D()
    x, v = kf.update(1.30)
    assert x > 0
    # velocity peut etre 0 ou non selon le modele
    assert isinstance(v, float)


def test_kalman_forecast():
    from scripts.v9_kalman_forecast import KalmanFilter1D
    kf = KalmanFilter1D()
    for v in [1.30, 1.31, 1.32, 1.33, 1.34]:
        kf.update(v)
    forecast, unc = kf.forecast(4)
    assert forecast > 1.34
    assert unc > 0


def test_kalman_projection_empty():
    from scripts.v9_kalman_forecast import kalman_projection
    res = kalman_projection([])
    assert "error" in res


def test_kalman_projection_short():
    from scripts.v9_kalman_forecast import kalman_projection
    res = kalman_projection([1.30, 1.31])
    assert "error" in res


def test_kalman_projection_uptrend():
    from scripts.v9_kalman_forecast import kalman_projection
    closes = [1.30 + i * 0.001 for i in range(30)]
    res = kalman_projection(closes, horizon=4)
    assert res["direction"] == "UP"
    assert "inflection" in res


def test_kalman_projection_horizons():
    from scripts.v9_kalman_forecast import kalman_projection
    closes = [1.30 + i * 0.001 for i in range(30)]
    for h in [1, 4, 20]:
        res = kalman_projection(closes, horizon=h)
        assert res["horizon"] == h


def test_main_kalman_runs(monkeypatch, capsys):
    from scripts.v9_kalman_forecast import main
    import sqlite3
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    db = d / "v9.db"
    db.touch()
    monkeypatch.setattr("core.v9.config.DB_PATH", str(db))
    exit_code = main(["--horizon", "4"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "KALMAN" in captured.out


# === News live ===

def test_fetch_news_hardcoded():
    from scripts.v9_news_live import fetch_news_hardcoded
    res = fetch_news_hardcoded()
    assert len(res) >= 1
    assert all("title" in e for e in res)


def test_should_block_no_events():
    from scripts.v9_news_live import should_block_news
    res = should_block_news([])
    assert res["block"] is False


def test_should_block_low_impact():
    from scripts.v9_news_live import should_block_news
    from datetime import datetime, timezone
    events = [{
        "title": "MINOR", "impact": "LOW",
        "date": datetime.now(timezone.utc),
    }]
    res = should_block_news(events)
    assert res["block"] is False


def test_should_block_high_impact_near():
    from scripts.v9_news_live import should_block_news
    from datetime import datetime, timezone, timedelta
    events = [{
        "title": "NFP_USD", "impact": "HIGH",
        "date": datetime.now(timezone.utc) + timedelta(minutes=10),
    }]
    res = should_block_news(events)
    assert res["block"] is True


def test_main_news_runs(capsys):
    from scripts.v9_news_live import main
    exit_code = main(["--no-fetch"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "NEWS LIVE" in captured.out


# === COT live ===

def test_cot_signal_extreme_long():
    from scripts.v9_cot_live import cot_signal
    res = cot_signal("GBPUSD", 85.0)
    assert res["signal"] == "EXTREME_LONG"


def test_cot_signal_extreme_short():
    from scripts.v9_cot_live import cot_signal
    res = cot_signal("GBPUSD", 15.0)
    assert res["signal"] == "EXTREME_SHORT"


def test_cot_signal_bullish_lean():
    from scripts.v9_cot_live import cot_signal
    res = cot_signal("GBPUSD", 70.0)
    assert res["signal"] == "BULLISH_LEAN"


def test_cot_signal_neutral():
    from scripts.v9_cot_live import cot_signal
    res = cot_signal("GBPUSD", 50.0)
    assert res["signal"] == "NEUTRAL"


def test_load_cot_snapshot_empty():
    from scripts.v9_cot_live import load_cot_snapshot
    # Pas de fichier → ts None
    res = load_cot_snapshot()
    # Retourne soit {"ts": None} soit {"ts": "..."} si existe
    assert "ts" in res


def test_save_and_load_cot():
    from scripts.v9_cot_live import save_cot_snapshot, load_cot_snapshot
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "cot_snapshot.json"
        # Monkeypatch COT_CACHE_PATH
        import scripts.v9_cot_live as cl
        original = cl.COT_CACHE_PATH
        cl.COT_CACHE_PATH = path
        try:
            save_cot_snapshot([{"test": 1}])
            loaded = load_cot_snapshot()
            assert loaded["ts"] is not None
            assert len(loaded["data"]) == 1
        finally:
            cl.COT_CACHE_PATH = original


def test_get_cot_signal():
    from scripts.v9_cot_live import get_cot_signal
    res = get_cot_signal("GBPUSD", 75.0)
    assert res["signal"] == "BULLISH_LEAN"


def test_main_cot_runs(capsys):
    from scripts.v9_cot_live import main
    exit_code = main(["--symbol", "GBPUSD", "--net-long", "75"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "COT REPORT" in captured.out