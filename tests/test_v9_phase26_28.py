"""tests/test_v9_phase26_28.py — Phase 26 + 28C motion CEO autopilote.

Tests pour feature importance + stress test.
"""
import pytest


# === v9_feature_importance ===

def test_get_paper_trades_full_db_missing(tmp_path):
    from scripts.v9_feature_importance import get_paper_trades_full
    assert get_paper_trades_full(tmp_path / "absent.db") == []


def test_ablation_study_insufficient():
    from scripts.v9_feature_importance import ablation_study
    res = ablation_study([{"pips_net": 10}] * 5)
    assert res == []


def test_ablation_study_basic():
    from scripts.v9_feature_importance import ablation_study
    trades = [
        {"symbol": "GBPUSD", "direction": "haussiere", "pips_net": 25.0,
         "close_reason": "TP_hit", "closed_at": "2026-07-31T11:30:00"},
    ] * 70 + [
        {"symbol": "EURUSD", "direction": "baissiere", "pips_net": -8.0,
         "close_reason": "SL_hit", "closed_at": "2026-07-31T15:30:00"},
    ] * 30
    results = ablation_study(trades)
    assert len(results) == 7  # 7 features
    # GBPUSD doit etre en haut (positive)
    gbpusd = next(r for r in results if r["feature"] == "symbol_gbpusd")
    assert gbpusd["delta"] > 0


def test_ablation_study_sorted():
    from scripts.v9_feature_importance import ablation_study
    trades = [{"pips_net": 25.0, "symbol": "GBPUSD", "direction": "haussiere",
               "close_reason": "TP_hit", "closed_at": "2026-07-31T11:30:00"}] * 50
    results = ablation_study(trades)
    # Trier par delta decroissant
    for i in range(len(results) - 1):
        assert results[i]["delta"] >= results[i + 1]["delta"]


# === v9_stress_test ===

def test_apply_scenario_wr_50():
    from scripts.v9_stress_test import apply_scenario
    pips = [25.0] * 90 + [-8.0] * 10
    res = apply_scenario(pips, "wr_50pct")
    # Inverser : WR devient ~10% (au lieu de 90%)
    assert res["new_exp"] < 0
    assert res["survived"] is False


def test_apply_scenario_spread_double():
    from scripts.v9_stress_test import apply_scenario
    pips = [23.5] * 80 + [-9.5] * 20
    res = apply_scenario(pips, "spread_double")
    # Spread double reduit expectancy de ~1.5p/trade
    assert res["impact_exp"] < 0
    assert abs(res["impact_exp"] - (-1.5)) < 0.1


def test_apply_scenario_loss_streak():
    from scripts.v9_stress_test import apply_scenario
    pips = [25.0] * 30
    res = apply_scenario(pips, "loss_streak_5")
    # 5 losses ajoutees au milieu
    assert res["n_trades"] == 35
    assert res["impact_exp"] < 0


def test_apply_scenario_edge_expires():
    from scripts.v9_stress_test import apply_scenario
    pips = [25.0] * 30
    res = apply_scenario(pips, "edge_expires")
    assert res["new_exp"] == 0.0
    assert res["survived"] is False


def test_apply_scenario_black_swan():
    from scripts.v9_stress_test import apply_scenario
    pips = [25.0] * 30
    res = apply_scenario(pips, "black_swan")
    assert res["n_trades"] == 31
    assert res["impact_total_pips"] == -50.0


def test_apply_scenario_unknown():
    from scripts.v9_stress_test import apply_scenario
    res = apply_scenario([1.0] * 20, "unknown_scenario")
    assert "error" in res


def test_apply_scenario_insufficient():
    from scripts.v9_stress_test import apply_scenario
    res = apply_scenario([], "wr_50pct")
    assert "error" in res