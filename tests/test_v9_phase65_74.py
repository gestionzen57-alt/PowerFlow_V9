"""tests/test_v9_phase65_74.py — Phases 65-74 motion CEO 48H.

Tests pour smart_order_router + live_metrics + ml_forecaster +
performance_persistence + cross_pair_correlation + chaos_advanced +
adversarial_testing + e2e_pipeline + docs_sync + user_guide_enrich.
"""
import pytest


# === smart_order_router ===

def test_iceberg_split_basic():
    from scripts.v9_smart_order_router import iceberg_split
    orders = iceberg_split(1.0, 0.1)
    # 1.0 / 0.1 = 10 orders
    assert len(orders) == 10


def test_iceberg_split_zero():
    from scripts.v9_smart_order_router import iceberg_split
    assert iceberg_split(0, 0.1) == []
    assert iceberg_split(1.0, 0) == []


def test_twap_split():
    from scripts.v9_smart_order_router import twap_split
    orders = twap_split(1.0, duration_seconds=60, n_intervals=5)
    assert len(orders) == 5


def test_twap_split_zero():
    from scripts.v9_smart_order_router import twap_split
    assert twap_split(0, 60) == []
    assert twap_split(1.0, 60, n_intervals=0) == []


def test_vwap_split():
    from scripts.v9_smart_order_router import vwap_split
    orders = vwap_split(1.0, [100, 200, 300])
    assert len(orders) == 3


def test_vwap_split_empty():
    from scripts.v9_smart_order_router import vwap_split
    assert vwap_split(1.0, []) == []
    assert vwap_split(0, [100]) == []


def test_random_delay():
    from scripts.v9_smart_order_router import random_delay
    d = random_delay(min_ms=50, max_ms=100)
    assert 50 <= d <= 100


def test_route_order_iceberg():
    from scripts.v9_smart_order_router import route_order
    res = route_order("GBPUSD", 1.0, mode="iceberg", visible_qty=0.1)
    assert res["n_orders"] == 10


def test_route_order_twap():
    from scripts.v9_smart_order_router import route_order
    res = route_order("GBPUSD", 1.0, mode="twap", duration_seconds=60)
    assert res["n_orders"] == 10


def test_route_order_unknown():
    from scripts.v9_smart_order_router import route_order
    res = route_order("GBPUSD", 1.0, mode="unknown")
    assert res["n_orders"] == 0


def test_main_smart_order(capsys):
    from scripts.v9_smart_order_router import main
    exit_code = main(["--symbol", "GBPUSD", "--qty", "1.0",
                        "--mode", "iceberg"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "SMART ORDER" in captured.out


# === live_metrics ===

def test_compute_unrealized_pnl_empty():
    from scripts.v9_live_metrics import compute_unrealized_pnl
    res = compute_unrealized_pnl([], {})
    assert res["total_pnl_pips"] == 0.0


def test_compute_unrealized_pnl_long():
    from scripts.v9_live_metrics import compute_unrealized_pnl
    positions = [{"symbol": "GBPUSD", "direction": "LONG",
                   "entry": 1.30, "size": 0.1}]
    prices = {"GBPUSD": 1.3025}
    res = compute_unrealized_pnl(positions, prices)
    assert res["total_pnl_pips"] > 0


def test_compute_unrealized_pnl_short():
    from scripts.v9_live_metrics import compute_unrealized_pnl
    positions = [{"symbol": "GBPUSD", "direction": "SHORT",
                   "entry": 1.30, "size": 0.1}]
    prices = {"GBPUSD": 1.2975}
    res = compute_unrealized_pnl(positions, prices)
    assert res["total_pnl_pips"] > 0


def test_compute_greeks_delta():
    from scripts.v9_live_metrics import compute_greeks_delta
    positions = [
        {"symbol": "GBPUSD", "direction": "LONG", "size": 0.5},
        {"symbol": "EURUSD", "direction": "SHORT", "size": 0.3},
    ]
    res = compute_greeks_delta(positions, {})
    assert res["net_delta"] == 0.2


def test_compute_trade_flow_empty():
    from scripts.v9_live_metrics import compute_trade_flow
    res = compute_trade_flow([])
    assert res["buy_volume"] == 0


def test_compute_trade_flow_normal():
    from scripts.v9_live_metrics import compute_trade_flow
    trades = [{"side": "BUY", "volume": 100},
               {"side": "SELL", "volume": 50}]
    res = compute_trade_flow(trades)
    assert res["buy_volume"] == 100
    assert res["sell_volume"] == 50


def test_live_metrics():
    from scripts.v9_live_metrics import live_metrics
    res = live_metrics([], {}, [])
    assert "ts" in res


def test_main_live_metrics_demo(capsys):
    from scripts.v9_live_metrics import main
    exit_code = main(["--demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LIVE METRICS" in captured.out


# === ml_forecaster ===

def test_compute_features_insufficient():
    from scripts.v9_ml_forecaster import compute_features
    res = compute_features([])
    assert "error" in res


def test_compute_features_basic():
    from scripts.v9_ml_forecaster import compute_features
    closes = [1.30 + i * 0.001 for i in range(40)]
    res = compute_features(closes)
    assert "rsi" in res
    assert "macd" in res


def test_score_signal_insufficient():
    from scripts.v9_ml_forecaster import score_signal
    res = score_signal({"error": "x"})
    assert res["score"] == 0


def test_score_signal_neutral():
    from scripts.v9_ml_forecaster import score_signal
    features = {"rsi": 50, "sma_5": 1.30, "sma_20": 1.30,
                 "macd": 0, "bb_upper": 1.31, "bb_lower": 1.29,
                 "current": 1.30, "momentum_pips": 0}
    res = score_signal(features)
    assert "signal" in res


def test_score_signal_oversold():
    from scripts.v9_ml_forecaster import score_signal
    features = {"rsi": 25, "sma_5": 1.30, "sma_20": 1.30,
                 "macd": 0.001, "bb_upper": 1.31, "bb_lower": 1.29,
                 "current": 1.28, "momentum_pips": -100}
    res = score_signal(features)
    assert res["score"] >= 50


def test_forecast():
    from scripts.v9_ml_forecaster import forecast
    closes = [1.30 + i * 0.001 for i in range(40)]
    res = forecast(closes)
    assert "features" in res


def test_forecast_insufficient():
    from scripts.v9_ml_forecaster import forecast
    res = forecast([])
    assert "error" in res


def test_main_ml_demo(capsys):
    from scripts.v9_ml_forecaster import main
    exit_code = main(["--demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ML FORECASTER" in captured.out


# === performance_persistence ===

def test_load_history_empty(tmp_path, monkeypatch):
    from scripts.v9_performance_persistence import (
        load_history, HISTORY_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_performance_persistence.HISTORY_PATH",
        tmp_path / "history.json",
    )
    assert load_history() == []


def test_save_history(tmp_path, monkeypatch):
    from scripts.v9_performance_persistence import (
        save_history, HISTORY_PATH,
    )
    monkeypatch.setattr(
        "scripts.v9_performance_persistence.HISTORY_PATH",
        tmp_path / "history.json",
    )
    save_history([{"ts": "2026-07-31", "pnl_pips": 100.0}])
    assert (tmp_path / "history.json").exists()


def test_record_snapshot(tmp_path, monkeypatch):
    from scripts.v9_performance_persistence import (
        record_snapshot, HISTORY_PATH, load_history,
    )
    monkeypatch.setattr(
        "scripts.v9_performance_persistence.HISTORY_PATH",
        tmp_path / "history.json",
    )
    snap = record_snapshot({"pnl_pips": 100.0, "wr": 0.85})
    assert "ts" in snap
    history = load_history()
    assert len(history) == 1


def test_compute_trend_empty():
    from scripts.v9_performance_persistence import compute_trend
    res = compute_trend([])
    assert res["trend"] == "UNKNOWN"


def test_compute_trend_improving():
    from scripts.v9_performance_persistence import compute_trend
    history = [{"pnl_pips": i * 10.0} for i in range(10)]
    res = compute_trend(history)
    assert res["trend"] == "IMPROVING"


def test_compute_trend_degrading():
    from scripts.v9_performance_persistence import compute_trend
    history = [{"pnl_pips": -i * 10.0} for i in range(10)]
    res = compute_trend(history)
    assert res["trend"] == "DEGRADING"


def test_main_perf_status(monkeypatch, capsys):
    from scripts.v9_performance_persistence import main
    import tempfile
    from pathlib import Path
    monkeypatch.setattr(
        "scripts.v9_performance_persistence.HISTORY_PATH",
        Path(tempfile.mkdtemp()) / "history.json",
    )
    exit_code = main(["--status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "PERFORMANCE" in captured.out


def test_main_perf_record(monkeypatch, capsys):
    from scripts.v9_performance_persistence import main
    import tempfile
    from pathlib import Path
    monkeypatch.setattr(
        "scripts.v9_performance_persistence.HISTORY_PATH",
        Path(tempfile.mkdtemp()) / "history.json",
    )
    exit_code = main(["--record", "--pnl", "100", "--wr", "0.85"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "recorded" in captured.out


# === cross_pair_correlation ===

def test_compute_returns_empty():
    from scripts.v9_cross_pair_correlation import compute_returns
    assert compute_returns([]) == []
    assert compute_returns([1.30]) == []


def test_compute_returns_basic():
    from scripts.v9_cross_pair_correlation import compute_returns
    res = compute_returns([1.30, 1.31, 1.32])
    assert len(res) == 2
    assert res[0] > 0


def test_pearson_correlation_perfect():
    from scripts.v9_cross_pair_correlation import pearson_correlation
    res = pearson_correlation([1, 2, 3, 4], [2, 4, 6, 8])
    assert abs(res - 1.0) < 0.001


def test_pearson_correlation_inverse():
    from scripts.v9_cross_pair_correlation import pearson_correlation
    res = pearson_correlation([1, 2, 3, 4], [4, 3, 2, 1])
    assert abs(res - (-1.0)) < 0.001


def test_pearson_correlation_empty():
    from scripts.v9_cross_pair_correlation import pearson_correlation
    assert pearson_correlation([], []) == 0.0


def test_correlation_matrix():
    from scripts.v9_cross_pair_correlation import correlation_matrix
    prices_dict = {
        "GBPUSD": [1.30 + i * 0.001 for i in range(40)],
        "EURUSD": [1.08 + i * 0.0005 for i in range(40)],
    }
    res = correlation_matrix(prices_dict)
    assert "matrix" in res


def test_correlation_matrix_insufficient():
    from scripts.v9_cross_pair_correlation import correlation_matrix
    res = correlation_matrix({"GBPUSD": [1.30]})
    assert "error" in res


def test_detect_correlation_regime_normal():
    from scripts.v9_cross_pair_correlation import (
        detect_correlation_regime,
    )
    matrix = {"matrix": {"A": {"B": 0.2, "A": 1.0},
                         "B": {"A": 0.2, "B": 1.0}}}
    res = detect_correlation_regime(matrix)
    assert res["regime"] in ("NORMAL", "DIVERSIFIED")


def test_main_cross_pair_demo(capsys):
    from scripts.v9_cross_pair_correlation import main
    exit_code = main(["--demo"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CROSS-PAIR" in captured.out


# === chaos_advanced ===

def test_inject_partition():
    from scripts.v9_chaos_advanced import inject_partition
    res = inject_partition(["w1", "w2", "w3", "w4"], n_partitions=2)
    assert res["n_partitions"] == 2
    assert len(res["partitions"]) == 2


def test_inject_latency():
    from scripts.v9_chaos_advanced import inject_latency
    d = inject_latency(duration_ms=100)
    assert 0 <= d <= 100


def test_inject_packet_loss():
    from scripts.v9_chaos_advanced import inject_packet_loss
    res = inject_packet_loss(loss_pct=100.0)
    assert res is True


def test_inject_disk_full(tmp_path):
    from scripts.v9_chaos_advanced import inject_disk_full
    res = inject_disk_full(tmp_path, mb=1)
    assert "success" in res


def test_chaos_test_suite():
    from scripts.v9_chaos_advanced import chaos_test_suite
    res = chaos_test_suite()
    assert "partition" in res


def test_main_chaos(capsys):
    from scripts.v9_chaos_advanced import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CHAOS" in captured.out


# === adversarial_testing ===

def test_nan_infinity():
    from scripts.v9_adversarial_testing import test_nan_infinity
    res = test_nan_infinity()
    assert "results" in res


def test_negative_values():
    from scripts.v9_adversarial_testing import test_negative_values
    res = test_negative_values()
    assert "results" in res


def test_zero_values():
    from scripts.v9_adversarial_testing import test_zero_values
    res = test_zero_values()
    assert "results" in res


def test_extreme_values():
    from scripts.v9_adversarial_testing import test_extreme_values
    res = test_extreme_values()
    assert "results" in res


def test_run_adversarial():
    from scripts.v9_adversarial_testing import run_adversarial
    res = run_adversarial()
    assert "n_tests" in res


def test_main_adversarial(capsys):
    from scripts.v9_adversarial_testing import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ADVERSARIAL" in captured.out


# === e2e_pipeline ===

def test_e2e_pipeline():
    from scripts.v9_e2e_pipeline import e2e_pipeline
    res = e2e_pipeline("GBPUSD", n_signals=5)
    assert "signals" in res


def test_main_e2e(capsys):
    from scripts.v9_e2e_pipeline import main
    exit_code = main(["--symbol", "GBPUSD", "--n", "5"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "E2E" in captured.out


# === docs_sync ===

def test_count_modules():
    from scripts.v9_docs_sync import count_modules
    res = count_modules()
    assert "scripts" in res
    assert "core" in res
    assert "tests" in res


def test_count_loc():
    from scripts.v9_docs_sync import count_loc
    res = count_loc()
    assert res > 0


def test_generate_index():
    from scripts.v9_docs_sync import generate_index
    res = generate_index()
    assert "INDEX MODULES" in res


def test_check_doc_coherence():
    from scripts.v9_docs_sync import check_doc_coherence
    res = check_doc_coherence()
    assert "all_present" in res


def test_sync_all():
    from scripts.v9_docs_sync import sync_all
    res = sync_all()
    assert res["index_updated"]


def test_main_docs_sync(capsys):
    from scripts.v9_docs_sync import main
    exit_code = main(["--sync"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DOCS SYNC" in captured.out


def test_main_docs_status(capsys):
    from scripts.v9_docs_sync import main
    exit_code = main(["--status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "COHERENCE" in captured.out


# === user_guide_enrich ===

def test_list_recent_modules():
    from scripts.v9_user_guide_enrich import list_recent_modules
    res = list_recent_modules(days=7)
    assert isinstance(res, list)


def test_generate_user_guide():
    from scripts.v9_user_guide_enrich import generate_user_guide
    res = generate_user_guide()
    assert "USER GUIDE" in res


def test_enrich_user_guide():
    from scripts.v9_user_guide_enrich import enrich_user_guide
    res = enrich_user_guide()
    assert res["updated"]


def test_main_user_guide_enrich(capsys):
    from scripts.v9_user_guide_enrich import main
    exit_code = main(["--enrich"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "USER GUIDE" in captured.out


def test_main_user_guide_recent(capsys):
    from scripts.v9_user_guide_enrich import main
    exit_code = main(["--recent"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Modules recents" in captured.out
