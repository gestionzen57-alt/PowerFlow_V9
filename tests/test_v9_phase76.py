"""tests/test_v9_phase76.py — Phase 76 motion CEO 48H (P2.3 audit Perplexity).

Tests pour ftmo_compliance_eur.
"""
import pytest


def test_get_pip_value_known_symbol():
    from scripts.v9_ftmo_compliance_eur import get_pip_value
    assert get_pip_value("GBPUSD", 0.01) == 0.10
    assert get_pip_value("USDJPY", 0.01) == 0.10
    assert get_pip_value("XAUUSD", 0.01) == 0.01


def test_get_pip_value_unknown_symbol():
    from scripts.v9_ftmo_compliance_eur import get_pip_value
    # Defaut 10.0 USD/pip pour 1 lot
    assert get_pip_value("UNKNOWNPAIR", 0.01) == 0.10


def test_compute_daily_dd_eur():
    from scripts.v9_ftmo_compliance_eur import compute_daily_dd_eur
    # GBPUSD 100 pips perte = 100 * 0.10 = 10 EUR
    assert compute_daily_dd_eur(-100.0, "GBPUSD", 0.01) == 10.0
    # JPY 100 pips perte = 100 * 0.10 = 10 EUR
    assert compute_daily_dd_eur(-100.0, "USDJPY", 0.01) == 10.0


def test_compute_total_dd_eur():
    from scripts.v9_ftmo_compliance_eur import compute_total_dd_eur
    assert compute_total_dd_eur(-200.0, "GBPUSD", 0.01) == 20.0


def test_ftmo_compliance_check_ok():
    from scripts.v9_ftmo_compliance_eur import ftmo_compliance_check
    # 10k EUR, -50 pips GBPUSD = 5 EUR (0.05%, sous 4%)
    res = ftmo_compliance_check(
        capital_eur=10000.0,
        daily_pips=-50.0,
        total_pips=-100.0,
        symbol="GBPUSD",
        lot_size=0.01,
    )
    assert res["daily_alert"] == "OK"
    assert res["total_alert"] == "OK"
    assert res["can_trade"] is True


def test_ftmo_compliance_check_warning_daily():
    from scripts.v9_ftmo_compliance_eur import ftmo_compliance_check
    # 10k EUR, -2000 pips GBPUSD = 200 EUR (2%, > 1% warning 50% de 4%)
    res = ftmo_compliance_check(
        capital_eur=10000.0,
        daily_pips=-2000.0,
        total_pips=-2000.0,
        symbol="GBPUSD",
        lot_size=0.01,
    )
    assert res["daily_alert"] == "WARNING"
    assert res["can_trade"] is True


def test_ftmo_compliance_check_critical_daily():
    from scripts.v9_ftmo_compliance_eur import ftmo_compliance_check
    # 10k EUR, -5000 pips GBPUSD = 500 EUR (5%, > 4% critical)
    res = ftmo_compliance_check(
        capital_eur=10000.0,
        daily_pips=-5000.0,
        total_pips=-5000.0,
        symbol="GBPUSD",
        lot_size=0.01,
    )
    assert res["daily_alert"] == "CRITICAL"
    assert res["can_trade"] is False


def test_ftmo_compliance_check_critical_total():
    from scripts.v9_ftmo_compliance_eur import ftmo_compliance_check
    # 10k EUR, daily -10 pips OK, total -10000 pips = 1000 EUR (10%, > 8% critical)
    res = ftmo_compliance_check(
        capital_eur=10000.0,
        daily_pips=-10.0,
        total_pips=-10000.0,
        symbol="GBPUSD",
        lot_size=0.01,
    )
    assert res["daily_alert"] == "OK"
    assert res["total_alert"] == "CRITICAL"
    assert res["can_trade"] is False


def test_ftmo_compliance_check_capital_zero():
    from scripts.v9_ftmo_compliance_eur import ftmo_compliance_check
    res = ftmo_compliance_check(0, -100.0, -100.0)
    assert "error" in res


def test_recommended_sizing_reduction_normal():
    from scripts.v9_ftmo_compliance_eur import recommended_sizing_reduction
    # Daily loss < 50% of 4% = no reduction
    factor = recommended_sizing_reduction(10000.0, -100.0, "GBPUSD", 0.01)
    assert factor == 1.0


def test_recommended_sizing_reduction_warning():
    from scripts.v9_ftmo_compliance_eur import recommended_sizing_reduction
    factor = recommended_sizing_reduction(10000.0, -2500.0, "GBPUSD", 0.01)
    assert factor == 0.5


def test_recommended_sizing_reduction_critical():
    from scripts.v9_ftmo_compliance_eur import recommended_sizing_reduction
    factor = recommended_sizing_reduction(10000.0, -5000.0, "GBPUSD", 0.01)
    assert factor == 0.0


def test_main_demo(capsys):
    from scripts.v9_ftmo_compliance_eur import main
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "FTMO COMPLIANCE EUR" in captured.out
    assert "Can trade" in captured.out