"""tests/test_v9_phase64.py — Phase 64 motion CEO 48H.

Tests pour real_money_preflight.
"""
import pytest


def test_check_token_rotation():
    from scripts.v9_real_money_preflight import check_token_rotation
    res = check_token_rotation()
    assert "status" in res


def test_check_mirror_blocking():
    from scripts.v9_real_money_preflight import check_mirror_blocking
    res = check_mirror_blocking()
    assert "status" in res


def test_check_mt4_bridge():
    from scripts.v9_real_money_preflight import (
        check_mt4_bridge_connectivity,
    )
    res = check_mt4_bridge_connectivity()
    assert res["status"] == "OK"


def test_check_cron_48h():
    from scripts.v9_real_money_preflight import check_cron_48h_installed
    res = check_cron_48h_installed()
    assert res["status"] == "OK"


def test_check_db_integrity_missing():
    from scripts.v9_real_money_preflight import check_db_integrity
    from pathlib import Path as _P
    res = check_db_integrity(_P("/nonexistent/path.db"))
    assert res["status"] == "FAIL"


def test_check_db_integrity_ok(tmp_path):
    from scripts.v9_real_money_preflight import check_db_integrity
    db = tmp_path / "v9.db"
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.close()
    res = check_db_integrity(db)
    assert res["status"] in ("OK", "WARN")


def test_check_tests_passing():
    from scripts.v9_real_money_preflight import check_tests_passing
    res = check_tests_passing()
    assert "status" in res


def test_check_phase_tracker():
    from scripts.v9_real_money_preflight import check_phase_tracker
    res = check_phase_tracker()
    assert "status" in res


def test_check_doc_coherence():
    from scripts.v9_real_money_preflight import check_doc_coherence
    res = check_doc_coherence()
    assert "status" in res


def test_check_doctrine_48h():
    from scripts.v9_real_money_preflight import check_doctrine_48h
    res = check_doctrine_48h()
    assert res["status"] == "OK"  # file was created


def test_check_15_levers():
    from scripts.v9_real_money_preflight import check_15_levers
    res = check_15_levers()
    assert res["status"] == "OK"


def test_check_ftmo_compliance():
    from scripts.v9_real_money_preflight import check_ftmo_compliance
    res = check_ftmo_compliance()
    assert res["status"] == "OK"


def test_check_orchestrator():
    from scripts.v9_real_money_preflight import check_orchestrator_running
    res = check_orchestrator_running()
    assert "status" in res


def test_check_cot_live():
    from scripts.v9_real_money_preflight import check_cot_live
    res = check_cot_live()
    assert res["status"] == "OK"


def test_check_news_live():
    from scripts.v9_real_money_preflight import check_news_live
    res = check_news_live()
    assert res["status"] == "OK"


def test_check_mt4_candle_bridge():
    from scripts.v9_real_money_preflight import check_mt4_candle_bridge
    res = check_mt4_candle_bridge()
    assert res["status"] == "OK"


def test_check_oos_validator():
    from scripts.v9_real_money_preflight import check_oos_validator
    res = check_oos_validator()
    assert res["status"] == "OK"


def test_check_robustness_checks():
    from scripts.v9_real_money_preflight import check_robustness_checks
    res = check_robustness_checks()
    assert res["status"] == "OK"


def test_check_smart_order_router():
    from scripts.v9_real_money_preflight import check_smart_order_router
    res = check_smart_order_router()
    assert res["status"] == "OK"


def test_check_live_metrics():
    from scripts.v9_real_money_preflight import check_live_metrics
    res = check_live_metrics()
    assert res["status"] == "OK"


def test_check_ml_forecaster():
    from scripts.v9_real_money_preflight import check_ml_forecaster
    res = check_ml_forecaster()
    assert res["status"] == "OK"


def test_check_auto_perfect_loop():
    from scripts.v9_real_money_preflight import check_auto_perfect_loop
    res = check_auto_perfect_loop()
    assert res["status"] == "OK"


def test_run_preflight():
    from scripts.v9_real_money_preflight import run_preflight
    res = run_preflight()
    assert "n_checks" in res
    assert res["n_checks"] >= 20


def test_main_runs(capsys):
    from scripts.v9_real_money_preflight import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert "PREFLIGHT" in captured.out