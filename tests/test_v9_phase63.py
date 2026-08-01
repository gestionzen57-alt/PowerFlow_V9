"""tests/test_v9_phase63.py — Phase 63 motion CEO 48H.

Tests pour ftmo_compliance.
"""
import pytest


def test_ftmo_limits():
    from scripts.v9_ftmo_compliance import FTMO_LIMITS
    assert FTMO_LIMITS["daily_dd_pct"] == 4.0
    assert FTMO_LIMITS["total_dd_pct"] == 8.0


def test_compute_pnl_from_trades():
    from scripts.v9_ftmo_compliance import compute_pnl_from_trades
    pnl = compute_pnl_from_trades([25.0, -8.0, 30.0])
    assert pnl == 47.0


def test_check_daily_dd_safe():
    from scripts.v9_ftmo_compliance import check_daily_dd
    # 100 perte sur 10000 capital = 1% (sous 2% warning)
    res = check_daily_dd(100.0, 10000.0)
    assert res["alert"] == "OK"


def test_check_daily_dd_warning():
    from scripts.v9_ftmo_compliance import check_daily_dd
    # 300 perte sur 10000 = 3% (entre 2% warning et 4% critical)
    res = check_daily_dd(300.0, 10000.0)
    assert res["alert"] == "WARNING"


def test_check_daily_dd_critical():
    from scripts.v9_ftmo_compliance import check_daily_dd
    # 500 perte sur 10000 = 5% (>= 4%)
    res = check_daily_dd(500.0, 10000.0)
    assert res["alert"] == "CRITICAL"


def test_compute_total_dd_safe():
    from scripts.v9_ftmo_compliance import compute_total_dd
    # 100 perte sur 10000 = 1% OK
    res = compute_total_dd(100.0, 10000.0)
    assert res["alert"] == "OK"


def test_compute_total_dd_critical():
    from scripts.v9_ftmo_compliance import compute_total_dd
    # 900 perte sur 10000 = 9% >= 8% CRITICAL
    res = compute_total_dd(900.0, 10000.0)
    assert res["alert"] == "CRITICAL"


def test_compute_sizing_safe():
    from scripts.v9_ftmo_compliance import compute_sizing
    res = compute_sizing(10000.0, 25.0, 8.0)
    assert res["lot_size"] > 0


def test_compute_sizing_reduce_at_dd():
    from scripts.v9_ftmo_compliance import compute_sizing
    safe = compute_sizing(10000.0, 25.0, 8.0, daily_dd_pct=1.0)
    warning = compute_sizing(10000.0, 25.0, 8.0, daily_dd_pct=3.0)
    assert warning["lot_size"] < safe["lot_size"]


def test_compute_sizing_kill_at_critical():
    from scripts.v9_ftmo_compliance import compute_sizing
    res = compute_sizing(10000.0, 25.0, 8.0, daily_dd_pct=4.5)
    assert res["lot_size"] == 0.0


def test_ftmo_status_safe():
    from scripts.v9_ftmo_compliance import ftmo_status
    # daily_pnl = -100 (loss), peak_pnl = -500 (5% sous 8%)
    res = ftmo_status(10000.0, -100.0, -500.0)
    assert res["can_trade"] is True


def test_ftmo_status_blocked():
    from scripts.v9_ftmo_compliance import ftmo_status
    # daily_pnl = -500 (5% > 4% limit), peak_pnl = -900 (9% > 8%)
    res = ftmo_status(10000.0, -500.0, -900.0)
    assert res["can_trade"] is False


def test_main_pnl(capsys):
    from scripts.v9_ftmo_compliance import main
    exit_code = main(["--capital", "10000", "--pnl", "100", "--peak",
                        "10500"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "FTMO" in captured.out


def test_main_blocked(capsys):
    from scripts.v9_ftmo_compliance import main
    exit_code = main(["--capital", "10000", "--pnl", "-500",
                        "--peak", "-9500"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "BLOCKED" in captured.out or "CRITICAL" in captured.out