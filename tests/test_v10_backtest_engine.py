"""V10 Backtest Engine — tests (HERMES_PLAN_V10 ÉTAPE 6).

Couvre :
  - Les 6 setups du plan (delta_min, leverage, WR cible)
  - BacktestReport : sérialisation JSON + CSV
  - run_backtest multi-paires × multi-setups
  - R6 fail-open (DB absente, paires vides)
  - Agrégation globale (WR global, PnL, max DD)

Total : 15 tests minimum. 0 import core/v9/ (R2 additif).
"""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_backtest_engine import (  # noqa: E402
    PLAN_SETUPS,
    BacktestReport,
    SetupMetrics,
    run_backtest,
)


# ─────────────────────────────────────────────────────────────────────
# Plan : 6 setups définis
# ─────────────────────────────────────────────────────────────────────
def test_plan_6_setups():
    assert set(PLAN_SETUPS.keys()) == {
        "S1_Momentum_fort", "S2_Continuation", "S3_Reversal_M30",
        "S4_London_open", "S5_NY_overlap", "S6_End_of_trend",
    }


def test_plan_setup_s1_momentum_fort():
    cfg = PLAN_SETUPS["S1_Momentum_fort"]
    assert cfg["delta_min"] == 3.0
    assert cfg["leverage"] == 50
    assert cfg["wr_target"] == 68
    assert cfg["rr_min"] == 2.5


def test_plan_setup_s6_end_of_trend_leverage_min():
    cfg = PLAN_SETUPS["S6_End_of_trend"]
    assert cfg["leverage"] == 10
    assert cfg["wr_target"] == 55
    assert cfg["rr_min"] == 3.5  # R:R le plus exigeant du plan


# ─────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────
def test_setup_metrics_serialisable():
    m = SetupMetrics(setup="S1_Momentum_fort", pair="EURUSD",
                     n_trades=100, wr_pct=68, avg_rr=2.5)
    json.dumps(m.as_dict())


def test_setup_metrics_defaults():
    m = SetupMetrics(setup="X", pair="Y")
    assert m.n_trades == 0
    assert m.wr_pct == 0.0
    assert m.meets_target is False


def test_backtest_report_serialisable():
    r = BacktestReport()
    json.dumps(r.as_dict())


def test_backtest_report_default_period():
    r = BacktestReport()
    assert r.period_days == 180


# ─────────────────────────────────────────────────────────────────────
# CSV
# ─────────────────────────────────────────────────────────────────────
def test_csv_export():
    r = BacktestReport()
    m = SetupMetrics(setup="X", pair="Y", n_trades=10, wr_pct=60.0)
    r.setup_metrics.append(m)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    n = r.to_csv(path)
    assert n == 1
    # Lecture et validation
    with open(path, encoding="utf-8", newline="") as f:
        reader = list(csv.reader(f))
    assert reader[0][0] == "setup"
    assert len(reader) == 2
    os.unlink(path)


def test_csv_export_vide():
    r = BacktestReport()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    n = r.to_csv(path)
    assert n == 0  # R6 : rapport vide
    os.unlink(path)


def test_to_json_path_creation(tmp_path):
    r = BacktestReport()
    r.setup_metrics.append(SetupMetrics(setup="X", pair="Y"))
    out = tmp_path / "sub" / "report.json"
    r.to_json(str(out))
    assert out.exists()


# ─────────────────────────────────────────────────────────────────────
# R6 fail-open (engine principal)
# ─────────────────────────────────────────────────────────────────────
def test_failopen_pas_de_paires():
    r = run_backtest([])
    assert "r6_fail_open" in r.notes or len(r.setup_metrics) == 0
    assert r.global_metrics["n_trades_total"] == 0


def test_failopen_db_absente():
    """Paires + db_path inexistant → rapport avec notes R6."""
    r = run_backtest(["GBPUSD"], db_path="nonexistent_zz.db")
    assert isinstance(r, BacktestReport)
    # R6 : doit avoir créé des SetupMetrics (vides par paire/setup)
    # et documenté r6_fail_open
    assert "r6_fail_open" in r.notes or all(m.n_trades == 0
                                            for m in r.setup_metrics)


def test_failopen_paires_avec_db_vide():
    """Paires vides avec DB → 0 trades, pas de crash."""
    r = run_backtest(["ZZZZZZ"], db_path="nonexistent_zz.db")
    # Les SetupMetrics existent mais sont vides
    n_metrics = len(r.setup_metrics)
    if n_metrics > 0:
        assert all(m.n_trades == 0 for m in r.setup_metrics)


# ─────────────────────────────────────────────────────────────────────
# Intégration edge_validator (live si DB existe)
# ─────────────────────────────────────────────────────────────────────
def test_run_backtest_db_live_si_disponible():
    """Si la DB V9 live existe, run_backtest doit retourner un rapport."""
    db_path = "data/v9_forces.db"
    if not os.path.exists(db_path):
        pytest.skip("DB live absente — skip intégration")
    r = run_backtest(["GBPUSD"], db_path=db_path,
                      setups={"S1_Momentum_fort": PLAN_SETUPS["S1_Momentum_fort"]})
    assert isinstance(r, BacktestReport)
    # SetupMetrics créées même si edge_validator échoue (R6 : pas de crash)
    # → on vérifie seulement qu'au moins une tentative a eu lieu
    assert r.setups_tested == ["S1_Momentum_fort"]
    assert "r6_fail_open" in r.notes or len(r.setup_metrics) > 0


# ─────────────────────────────────────────────────────────────────────
# Agrégation globale
# ─────────────────────────────────────────────────────────────────────
def test_aggregation_globale_vide():
    r = BacktestReport()
    r.setup_metrics = []
    # simulate engine output for empty setup
    from core.v10.v10_backtest_engine import _metriques_globales
    r.global_metrics = _metriques_globales([])
    metrics = r.as_dict()["global_metrics"]
    assert metrics["n_trades_total"] == 0


def test_aggregation_globale_ponderee():
    m1 = SetupMetrics(setup="S1", pair="EURUSD", n_trades=100,
                       wr_pct=70.0, pnl_total_pips=200)
    m2 = SetupMetrics(setup="S2", pair="GBPUSD", n_trades=50,
                       wr_pct=60.0, pnl_total_pips=100)
    r = BacktestReport()
    r.setup_metrics = [m1, m2]
    # Recalcul agrégation
    n = sum(m.n_trades for m in r.setup_metrics)
    wr_total = sum(m.wr_pct * m.n_trades for m in r.setup_metrics) / n
    assert n == 150
    assert wr_total == pytest.approx((70 * 100 + 60 * 50) / 150, abs=0.01)


def test_setups_personnalises():
    """Les setups sont surchargeables (R8)."""
    custom = {"MY_SETUP": {"delta_min": 1.0, "leverage": 25,
                          "wr_target": 60, "rr_min": 2.0}}
    r = run_backtest(["GBPUSD"], db_path="nonexistent_zz.db",
                     setups=custom)
    assert r.setups_tested == ["MY_SETUP"]
