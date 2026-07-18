"""test_v9_predictive_engine.py — Tests pour core/v9/v9_predictive_engine.py (R33).

Vérifie :
T1. Kill switch (V9_PREDICTIVE_ENGINE_ENABLED) — défaut ON
T2. _bucket_vol_atr aligné avec cycle_memory
T3. _sigmoid numérique stable
T4. predict_phase_transition avec transition data valide
T5. predict_phase_transition retourne distribution normalisée
T6. predict_phase_transition ajuste reversal_risk par durée
T7. predict_phase_transition ajuste reversal_risk par vol HIGH
T8. predict_phase_transition ajuste reversal_risk par divergence MTF
T9. predict_phase_transition fallback si pas de data
T10. predict_phase_transition fallback si phase invalide
T11. predict_phase_transition fallback si régime invalide
T12. predict_phase_transition fallback si kill switch OFF
T13. PredictiveContext frozen
T14. Prediction dataclass + to_dict
T15. _fallback_prediction defaults
T16. CLI dry-run
T17. R6 défensif : cycle DB corrompue ne crash pas
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from pathlib import Path

import pytest

from core.v9.v9_predictive_engine import (
    PREDICTIVE_ENABLED_ENV,
    DEFAULT_TP,
    DEFAULT_SL,
    VALID_PHASES,
    VALID_REGIMES,
    PredictiveContext,
    Prediction,
    _bucket_vol_atr,
    _expected_phase_duration,
    _fallback_prediction,
    _sigmoid,
    predict_phase_transition,
    predictive_engine_enabled,
)
from core.v9.v9_cycle_memory import (
    DEFAULT_DB_PATH,
    MIN_N_OBSERVATIONS,
    init_db as init_cycle_db,
    update as cycle_update,
    update_transition,
)


@pytest.fixture
def tmp_cycle_db(tmp_path: Path) -> Path:
    """DB cycle memory avec transitions marquov peuplées + 1 cellule stats."""
    db = tmp_path / "test_cycle.db"
    init_cycle_db(db)
    # 30 transitions : culmination → initiation (10), culmination → culmination (15),
    # culmination → resolution (3), culmination → developpement (2)
    for _ in range(10):
        update_transition("culmination", "initiation", "GBPUSD", "M15",
                          "NEUTRE", db_path=db)
    for _ in range(15):
        update_transition("culmination", "culmination", "GBPUSD", "M15",
                          "NEUTRE", db_path=db)
    for _ in range(3):
        update_transition("culmination", "resolution", "GBPUSD", "M15",
                          "NEUTRE", db_path=db)
    for _ in range(2):
        update_transition("culmination", "developpement", "GBPUSD", "M15",
                          "NEUTRE", db_path=db)
    # 1 cellule culmination avec stats : WR=80%, mean_duration=20 barres
    for _ in range(MIN_N_OBSERVATIONS + 5):
        cycle_update("GBPUSD", "M15", "NEUTRE", "culmination", 3.5,
                     is_win=True, duration_bars=20.0, db_path=db)
    return db


@pytest.fixture(autouse=True)
def cleanup_env(monkeypatch: pytest.MonkeyPatch):
    if PREDICTIVE_ENABLED_ENV in os.environ:
        monkeypatch.delenv(PREDICTIVE_ENABLED_ENV)
    yield


# ============================================================== T1 kill switch

def test_predictive_enabled_default_on():
    """Motion CEO 2026-07-18 : APPLY direct, défaut ON."""
    assert PREDICTIVE_ENABLED_ENV not in os.environ
    assert predictive_engine_enabled() is True


def test_predictive_disabled_when_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PREDICTIVE_ENABLED_ENV, "0")
    assert predictive_engine_enabled() is False


# ============================================================== T2 bucket vol

def test_bucket_vol_atr_aligned():
    """Cohérence avec v9_cycle_memory."""
    from core.v9.v9_cycle_memory import _bucket_vol_atr as cm_bucket
    for v in [0.5, 1.0, 2.0, 2.1, 6.0, 6.1, 20.0, None, -1.0]:
        assert _bucket_vol_atr(v) == cm_bucket(v)


# ============================================================== T3 sigmoid

def test_sigmoid_zero():
    assert _sigmoid(0.0) == pytest.approx(0.5, abs=1e-6)


def test_sigmoid_positive():
    assert _sigmoid(10.0) > 0.99
    assert _sigmoid(2.0) > 0.85


def test_sigmoid_negative():
    assert _sigmoid(-10.0) < 0.01
    assert _sigmoid(-2.0) < 0.15


def test_sigmoid_extreme():
    """Sigmoid stable numériquement même pour |x| grand."""
    assert 0 < _sigmoid(1e6) <= 1.0
    assert 0 <= _sigmoid(-1e6) < 1.0


# ============================================================== T4 predict avec data

def test_predict_with_valid_transition(tmp_cycle_db: Path):
    """Avec 30 transitions valides, predict retourne une distribution."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    assert isinstance(pred, Prediction)
    assert pred.phase_predicted in VALID_PHASES
    assert pred.confidence > 0  # On a 30 observations
    # Distribution doit contenir les 4 phases
    assert set(pred.phase_distribution.keys()) == set(VALID_PHASES)
    assert sum(pred.phase_distribution.values()) == pytest.approx(1.0, abs=0.01)


def test_predict_most_likely_phase(tmp_cycle_db: Path):
    """Avec 15/30 culminations, la plus probable est culmination."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination",
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    # 15/30 = 0.5 culmination, 10/30 = 0.33 initiation
    assert pred.phase_predicted == "culmination"
    assert pred.p_no_change == pytest.approx(0.5, abs=0.01)
    assert pred.p_reversal == pytest.approx(0.5, abs=0.01)


# ============================================================== T5 distribution normalisée

def test_distribution_sum_is_one(tmp_cycle_db: Path):
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="initiation",
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    # Sum = 1.0 (renormalisé même si certaines phases absentes)
    total = sum(pred.phase_distribution.values())
    assert total == pytest.approx(1.0, abs=0.001)


def test_distribution_all_phases_present(tmp_cycle_db: Path):
    """Même les phases sans transition doivent être dans la distribution (P=0)."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="initiation",
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    assert "culmination" in pred.phase_distribution
    assert "developpement" in pred.phase_distribution
    assert "initiation" in pred.phase_distribution
    assert "resolution" in pred.phase_distribution


# ============================================================== T6 ajustement durée

def test_reversal_risk_increases_with_duration(tmp_cycle_db: Path):
    """Si duration >> mean_duration, reversal_risk monte."""
    ctx_normal = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        duration_bars=20.0,  # = mean_duration
    )
    ctx_long = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        duration_bars=80.0,  # 4× la moyenne → basculement imminent
    )
    pred_normal = predict_phase_transition(ctx_normal, cycle_db=tmp_cycle_db)
    pred_long = predict_phase_transition(ctx_long, cycle_db=tmp_cycle_db)
    assert pred_long.reversal_risk > pred_normal.reversal_risk


def test_reversal_risk_short_duration(tmp_cycle_db: Path):
    """Si duration < mean, reversal_risk reste bas (pas de signal de bascule)."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        duration_bars=2.0,  # bien < mean_duration=20
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    # risk doit être proche de la base markov (pas boosté par durée)
    assert pred.reversal_risk < 0.7


# ============================================================== T7 ajustement vol HIGH

def test_reversal_risk_high_vol(tmp_cycle_db: Path):
    """vol HIGH → reversal_risk += 0.20."""
    ctx_low = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=1.0,  # LOW
    )
    ctx_high = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=15.0,  # HIGH
    )
    pred_low = predict_phase_transition(ctx_low, cycle_db=tmp_cycle_db)
    pred_high = predict_phase_transition(ctx_high, cycle_db=tmp_cycle_db)
    assert pred_high.reversal_risk > pred_low.reversal_risk
    # Delta ≈ 0.30 (HIGH bonus +0.20 + LOW malus -0.10)
    delta = pred_high.reversal_risk - pred_low.reversal_risk
    assert delta == pytest.approx(0.30, abs=0.05)


# ============================================================== T8 divergence MTF

def test_reversal_risk_mtf_divergence(tmp_cycle_db: Path):
    """mtf_divergence=True → reversal_risk += 0.30."""
    ctx_no = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", mtf_divergence=False,
    )
    ctx_yes = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", mtf_divergence=True,
    )
    pred_no = predict_phase_transition(ctx_no, cycle_db=tmp_cycle_db)
    pred_yes = predict_phase_transition(ctx_yes, cycle_db=tmp_cycle_db)
    assert pred_yes.reversal_risk > pred_no.reversal_risk
    assert (pred_yes.reversal_risk - pred_no.reversal_risk) == pytest.approx(0.30, abs=0.01)


def test_reversal_risk_capped_at_one(tmp_cycle_db: Path):
    """Tous les facteurs → reversal_risk ≤ 1.0."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=15.0,  # HIGH
        duration_bars=200.0,  # très long
        mtf_divergence=True,
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    assert 0 <= pred.reversal_risk <= 1.0


# ============================================================== T9 fallback no data

def test_predict_no_transition_data(tmp_path: Path):
    """DB cycle memory vide ou sans transitions → fallback."""
    db = tmp_path / "empty_cycle.db"
    init_cycle_db(db)
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination",
    )
    pred = predict_phase_transition(ctx, cycle_db=db)
    assert pred.confidence == 0.0
    assert "fallback" in pred.rationale


def test_predict_db_inexistant(tmp_path: Path):
    """DB absente → fallback."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination",
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_path / "no.db")
    assert pred.confidence == 0.0


# ============================================================== T10 phase invalide

def test_predict_invalid_phase(tmp_cycle_db: Path):
    """Phase hors vocabulaire → fallback."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="INVALID",
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    assert pred.confidence == 0.0


# ============================================================== T11 régime invalide

def test_predict_invalid_regime(tmp_cycle_db: Path):
    """Régime hors vocabulaire → fallback."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="WRONG",
        phase="culmination",
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    assert pred.confidence == 0.0


# ============================================================== T12 kill switch OFF

def test_predict_disabled_returns_fallback(tmp_cycle_db: Path,
                                            monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PREDICTIVE_ENABLED_ENV, "0")
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination",
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    assert pred.confidence == 0.0
    assert "disabled" in pred.rationale


# ============================================================== T13 PredictiveContext frozen

def test_context_frozen():
    """PredictiveContext est immuable (frozen=True)."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination",
    )
    with pytest.raises(Exception):  # FrozenInstanceError ou AttributeError
        ctx.symbol = "EURUSD"


# ============================================================== T14 Prediction dataclass

def test_prediction_to_dict(tmp_cycle_db: Path):
    pred = predict_phase_transition(
        PredictiveContext(
            symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
            phase="culmination",
        ),
        cycle_db=tmp_cycle_db,
    )
    d = pred.to_dict()
    assert "phase_predicted" in d
    assert "reversal_risk" in d
    assert "phase_distribution" in d


def test_prediction_frozen():
    """Prediction immuable."""
    pred = _fallback_prediction(
        PredictiveContext(
            symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
            phase="culmination",
        ),
        "test",
    )
    with pytest.raises(Exception):
        pred.phase_predicted = "resolution"


# ============================================================== T15 fallback defaults

def test_fallback_prediction_defaults():
    pred = _fallback_prediction(
        PredictiveContext(
            symbol="EURUSD", timeframe="M15", regime_type="NEUTRE",
            phase="developpement",
        ),
        "test_reason",
    )
    assert pred.phase_predicted == "developpement"
    assert pred.confidence == 0.0
    assert pred.p_win_given_phase is None
    assert "fallback" in pred.rationale
    assert "test_reason" in pred.rationale


# ============================================================== T16 CLI

def test_cli_dry_run(tmp_cycle_db: Path, capsys, monkeypatch: pytest.MonkeyPatch):
    """CLI retourne un Prediction sérialisé."""
    from core.v9.v9_predictive_engine import main
    # Patche DEFAULT_DB_PATH via monkeypatching du module
    import core.v9.v9_predictive_engine as pe_module
    monkeypatch.setattr(pe_module, "CYCLE_MEMORY_DB_PATH", tmp_cycle_db)
    monkeypatch.setenv("V9_CYCLE_MEMORY_ENABLED", "1")
    rc = main(["--symbol", "GBPUSD", "--phase", "culmination",
               "--vol-atr", "3.5", "--duration", "25"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "phase_predicted" in out
    assert "reversal_risk" in out


# ============================================================== T17 R6 défensif

def test_predict_handles_corrupt_cycle_db(tmp_path: Path):
    """R6 : DB corrompue ne crash pas."""
    db = tmp_path / "corrupt.db"
    db.write_text("not a sqlite db")
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination",
    )
    pred = predict_phase_transition(ctx, cycle_db=db)
    # Doit retourner un Prediction (fallback)
    assert isinstance(pred, Prediction)


# ============================================================== T18 p_win_given_phase

def test_p_win_given_phase_populated(tmp_cycle_db: Path):
    """Si la cellule de la phase prédite existe, p_win_given_phase est rempli."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    # On a populé 'culmination' dans tmp_cycle_db avec WR=1.0
    assert pred.p_win_given_phase is not None
    assert 0.5 <= pred.p_win_given_phase <= 1.0  # WR observé ~1.0


# ============================================================== T19 reversal_window_bars

def test_reversal_window_estimated(tmp_cycle_db: Path):
    """Si mean_duration connue, reversal_window_bars ≈ 30% de mean_duration."""
    ctx = PredictiveContext(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
    )
    pred = predict_phase_transition(ctx, cycle_db=tmp_cycle_db)
    # mean_duration ≈ 20 → window ≈ 6
    assert pred.reversal_window_bars >= 1
    assert pred.reversal_window_bars <= 20


def test_reversal_window_default_without_data():
    """Sans data, window = 5 (défaut)."""
    ctx = PredictiveContext(
        symbol="XYZ", timeframe="M15", regime_type="NEUTRE",
        phase="initiation",
    )
    pred = predict_phase_transition(ctx)
    assert pred.reversal_window_bars == 5


# ============================================================== T20 priors

def test_valid_phases_constant():
    assert set(VALID_PHASES) == {
        "culmination", "developpement", "initiation", "resolution",
    }


def test_valid_regimes_constant():
    assert "NEUTRE" in VALID_REGIMES
    assert "RETOUR_EQUILIBRE" in VALID_REGIMES
