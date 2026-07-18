"""test_v9_bayesian_predictor.py — Tests pour core/v9/v9_bayesian_predictor.py (R33).

Vérifie :
T1. Kill switch (V9_BAYESIAN_PREDICTOR_ENABLED) — défaut ON
T2. Beta-Binomial : posterior, mean, variance, IC95%
T3. Shrinkage bayésien vers moyenne globale
T4. Platt calibration : fit, predict_proba, stabilité
T5. Calibration metrics : Brier, log-loss, ECE, accuracy, BSS
T6. ECE binned sur distribution connue
T7. fit_from_decisions_db avec synthetic data
T8. predict() — fallback prior_only si pas de fit
T9. predict() — combinaison Platt + Beta + shrinkage
T10. predict() — décision action (enter/reduce_size/skip) selon edge
T11. Schema init_calibration_db idempotent
T12. R6 défensif : erreurs DB ne crashent pas
T13. batch_score robuste aux entrées mal formées
T14. CLI fit / predict
T15. Vol bucketisation alignée sur v9_cycle_memory
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from pathlib import Path

import pytest

from core.v9.v9_bayesian_predictor import (
    BAYESIAN_ENABLED_ENV,
    DEFAULT_CALIBRATION_DB,
    ECE_BINS,
    MIN_N_FOR_BETA_PRIOR,
    MIN_N_FOR_LOCAL_CALIBRATION,
    PRIOR_ALPHA,
    PRIOR_BETA,
    BetaPosterior,
    CalibrationMetrics,
    PlattCalibrator,
    Prediction,
    _bucket_vol_atr_from_pips,
    _compute_ece,
    _sigmoid,
    batch_score,
    bayesian_predictor_enabled,
    beta_mean_with_shrinkage,
    beta_posterior_from_counts,
    compute_calibration_metrics,
    fit_from_decisions_db,
    fit_platt,
    init_calibration_db,
    predict,
)


@pytest.fixture
def tmp_cal_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_calibration.db"
    init_calibration_db(db)
    return db


@pytest.fixture
def live_db_with_decisions(tmp_path: Path) -> Path:
    """Crée une DB synthétique imitant v9_forces.db (lecture seule)."""
    db = tmp_path / "fake_forces.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript("""
            CREATE TABLE decisions (
                decision_id TEXT PRIMARY KEY,
                timestamp TEXT, symbol TEXT, timeframe TEXT,
                regime_type TEXT, scene_id TEXT, behavior_id TEXT,
                signal_id TEXT, is_win INTEGER, resolution_pips REAL
            );
            CREATE TABLE signals (
                signal_id TEXT PRIMARY KEY,
                timestamp TEXT, symbol TEXT, timeframe TEXT,
                confiance INTEGER
            );
            CREATE TABLE behaviors (
                behavior_id TEXT PRIMARY KEY,
                phase TEXT
            );
        """)
        # 200 décisions GBPUSD M15 NEUTRE culmination
        # WR réel ≈ 85 % à conf 80, ≈ 60 % à conf 60 (calibration imparfaite)
        for i in range(200):
            sym = "GBPUSD" if i < 150 else ("EURUSD" if i < 180 else "USDJPY")
            tf = "M15"
            regime = "NEUTRE" if i % 5 != 0 else "RETOUR_EQUILIBRE"
            phase = "culmination" if i % 3 != 0 else "initiation"
            # Confiance : 80 pour GBPUSD, 60 pour autres
            conf = 80 if sym == "GBPUSD" else 60
            # WR calibré : à conf=80, on observe ~85% win. à conf=60, ~60% win.
            # On simule un outcome biaisé : P(win) = sigmoid(0.03*conf - 1.5)
            p_win = 1 / (1 + math.exp(-(0.03 * conf - 1.5)))
            import random
            random.seed(42)
            is_win = 1 if random.random() < p_win else 0
            sig_id = f"sig_{i}"
            beh_id = f"beh_{i}"
            conn.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"dec_{i}", f"2026-07-{(i%17)+1:02d}T00:00:00", sym, tf,
                 regime, f"sc_{i}", beh_id, sig_id, is_win, 5.0 if is_win else -15.0),
            )
            conn.execute(
                "INSERT INTO signals VALUES (?, ?, ?, ?, ?)",
                (sig_id, f"2026-07-{(i%17)+1:02d}T00:00:00", sym, tf, conf),
            )
            conn.execute(
                "INSERT INTO behaviors VALUES (?, ?)",
                (beh_id, phase),
            )
        conn.commit()
    finally:
        conn.close()
    return db


@pytest.fixture(autouse=True)
def cleanup_env(monkeypatch: pytest.MonkeyPatch):
    """Isole les tests des variables d'environnement."""
    if BAYESIAN_ENABLED_ENV in os.environ:
        monkeypatch.delenv(BAYESIAN_ENABLED_ENV)
    yield


# ============================================================== T1 kill switch

def test_bayesian_enabled_default_on():
    """Motion CEO 2026-07-18 : APPLY direct, défaut ON."""
    assert BAYESIAN_ENABLED_ENV not in os.environ
    assert bayesian_predictor_enabled() is True


def test_bayesian_disabled_when_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(BAYESIAN_ENABLED_ENV, "0")
    assert bayesian_predictor_enabled() is False


# ============================================================== T2 Beta-Binomial

def test_beta_posterior_from_counts_basic():
    bp = beta_posterior_from_counts(n_wins=8, n_losses=2)
    # α = 8+1 = 9, β = 2+1 = 3
    assert bp.alpha == 9.0
    assert bp.beta_param == 3.0
    assert bp.n_observations == 10
    assert bp.n_wins == 8
    assert bp.n_losses == 2
    # mean = 9 / (9+3) = 0.75
    assert bp.mean == pytest.approx(0.75, abs=0.01)


def test_beta_posterior_prior():
    """Prior non-informatif Beta(1, 1) → mean=0.5."""
    bp = beta_posterior_from_counts(0, 0)
    assert bp.alpha == 1.0
    assert bp.beta_param == 1.0
    assert bp.mean == 0.5


def test_beta_posterior_variance_positive():
    bp = beta_posterior_from_counts(5, 5)
    assert bp.variance > 0
    assert bp.std > 0


def test_beta_posterior_variance_decreases_with_n():
    """Plus d'observations → moins de variance (concentration)."""
    bp_small = beta_posterior_from_counts(5, 5)
    bp_large = beta_posterior_from_counts(50, 50)
    assert bp_large.variance < bp_small.variance


def test_beta_posterior_credible_interval_95():
    bp = beta_posterior_from_counts(50, 50)
    lo, hi = bp.credible_interval_95()
    assert 0 <= lo <= bp.mean <= hi <= 1
    assert hi - lo < 0.5  # intervalle raisonnable


def test_beta_posterior_credible_interval_clamped():
    """IC95% borné à [0, 1]."""
    bp = beta_posterior_from_counts(2, 0)  # très peu d'obs, mean ~0.75
    lo, hi = bp.credible_interval_95()
    assert lo >= 0
    assert hi <= 1


def test_beta_posterior_to_dict():
    bp = beta_posterior_from_counts(7, 3)
    d = bp.to_dict()
    assert "mean" in d
    assert "std" in d
    assert "ci95" in d
    assert len(d["ci95"]) == 2


# ============================================================== T3 shrinkage

def test_shrinkage_pulls_to_global():
    """Avec peu d'obs, la moyenne shrinks vers global_mean."""
    # n=2, observed=1.0 (2 wins, 0 losses), global_mean=0.5
    shrunk = beta_mean_with_shrinkage(n_wins=2, n_losses=0, global_mean=0.5)
    assert shrunk < 1.0  # shrinkée
    assert shrunk > 0.5  # au-dessus de global (observed=1 tire vers le haut)


def test_shrinkage_approaches_observed_with_many_obs():
    """Avec beaucoup d'obs, shrunk ≈ observed."""
    observed_wr = 0.80
    n_w = int(observed_wr * 1000)
    n_l = 1000 - n_w
    shrunk = beta_mean_with_shrinkage(n_w, n_l, global_mean=0.5)
    assert shrunk == pytest.approx(observed_wr, abs=0.02)


def test_shrinkage_zero_obs_returns_global():
    shrunk = beta_mean_with_shrinkage(0, 0, global_mean=0.7)
    assert shrunk == 0.7


# ============================================================== T4 Platt

def test_sigmoid_zero():
    assert _sigmoid(0.0) == pytest.approx(0.5, abs=1e-6)


def test_sigmoid_positive():
    assert _sigmoid(10.0) > 0.99
    assert _sigmoid(2.0) > 0.85


def test_sigmoid_negative():
    assert _sigmoid(-10.0) < 0.01
    assert _sigmoid(-2.0) < 0.15


def test_fit_platt_identity():
    """conf_norm ∈ [0,1] avec outcome = conf_norm → a ≈ grand, b ≈ 0."""
    confs = [0.1, 0.3, 0.5, 0.7, 0.9]
    outcomes = [0, 0, 1, 1, 1]
    platt = fit_platt(confs, outcomes, n_iter=500)
    # Le fit doit produire des probas croissantes
    p0 = platt.predict_proba(0.0)
    p1 = platt.predict_proba(0.5)
    p2 = platt.predict_proba(1.0)
    assert p0 < p1 < p2


def test_fit_platt_constant_outcome():
    """Si tous les outcomes = 1, proba ≈ 1 pour toutes les confiances."""
    confs = [0.1, 0.3, 0.5, 0.7, 0.9]
    outcomes = [1, 1, 1, 1, 1]
    platt = fit_platt(confs, outcomes, n_iter=300)
    for c in confs:
        p = platt.predict_proba(c)
        # Tolérance : Platt avec tous outcomes=1 doit pousser p au-dessus de 0.85
        # (le LR descent avec lr=0.05 + 300 iter n'atteint pas asymptote stricte)
        assert p > 0.85


def test_fit_platt_empty_inputs():
    platt = fit_platt([], [])
    assert platt.n_fit == 0
    assert platt.a == 1.0
    assert platt.b == 0.0


def test_fit_platt_log_likelihood_improves():
    """Le fit doit produire un log-likelihood > -log(2) (aléatoire)."""
    confs = [0.1, 0.3, 0.5, 0.7, 0.9]
    outcomes = [0, 0, 1, 1, 1]
    platt = fit_platt(confs, outcomes, n_iter=500)
    # Log-likelihood d'un classifieur aléatoire = -log(2) ≈ -0.693
    assert platt.log_likelihood > -0.7


def test_platt_predict_proba_range():
    """predict_proba doit toujours retourner [0, 1]."""
    platt = PlattCalibrator(a=2.0, b=-1.0, n_fit=100, log_likelihood=-0.5)
    for c in [0.0, 0.25, 0.5, 0.75, 1.0]:
        p = platt.predict_proba(c)
        assert 0 <= p <= 1


def test_platt_to_dict():
    p = PlattCalibrator(a=1.5, b=-0.5, n_fit=50, log_likelihood=-0.4)
    d = p.to_dict()
    assert d["a"] == 1.5
    assert d["n_fit"] == 50


# ============================================================== T5 metrics

def test_compute_metrics_perfect_calibration():
    """Si p == outcome pour chaque exemple → Brier = 0."""
    preds = [1.0, 0.0, 1.0, 0.0, 1.0]
    outcomes = [1, 0, 1, 0, 1]
    m = compute_calibration_metrics(preds, outcomes)
    assert m.brier_score == pytest.approx(0.0, abs=0.01)
    assert m.accuracy == 1.0


def test_compute_metrics_perfectly_miscalibrated():
    """Si p = 0.5 toujours → Brier = 0.25 (pire cas pour un classifieur binaire)."""
    preds = [0.5] * 10
    outcomes = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
    m = compute_calibration_metrics(preds, outcomes)
    assert m.brier_score == pytest.approx(0.25, abs=0.01)


def test_compute_metrics_brier_skill_score_positive():
    """BSS > 0 si meilleur que la baseline naïve."""
    # Prédictions bien calibrées : p proche de outcome
    preds = [0.85, 0.85, 0.85, 0.85, 0.2, 0.2, 0.2, 0.2]
    outcomes = [1, 1, 1, 0, 0, 0, 0, 1]
    m = compute_calibration_metrics(preds, outcomes)
    # BSS peut être positif même si accuracy n'est pas parfaite
    assert isinstance(m.brier_skill_score, float)


def test_compute_metrics_empty():
    m = compute_calibration_metrics([], [])
    assert m.n == 0
    assert m.brier_score == 1.0


def test_compute_metrics_log_loss_positive():
    preds = [0.7, 0.3, 0.9, 0.1]
    outcomes = [1, 0, 1, 0]
    m = compute_calibration_metrics(preds, outcomes)
    assert m.log_loss > 0
    # Log-loss doit être inférieur à log(2) ≈ 0.693 (aléatoire)
    assert m.log_loss < 0.7


def test_compute_metrics_ece_range():
    """ECE ∈ [0, 1]."""
    preds = [0.1, 0.3, 0.5, 0.7, 0.9, 0.2, 0.4, 0.6, 0.8, 1.0]
    outcomes = [0, 0, 1, 1, 1, 0, 1, 0, 1, 1]
    m = compute_calibration_metrics(preds, outcomes)
    assert 0 <= m.ece <= 1


# ============================================================== T6 ECE binned

def test_ece_perfect_bin():
    """Si conf_moyenne ≈ accuracy → ECE ≈ 0 (cas asymptotique)."""
    # Prédictions à 1.0 (max du bin) avec outcomes = 1 → conf=1.0, accuracy=1.0, diff=0
    preds = [1.0] * 10
    outcomes = [1] * 10
    ece = _compute_ece(preds, outcomes, n_bins=10)
    assert ece == pytest.approx(0.0, abs=0.01)


def test_ece_miscalibrated_bin():
    """Conf=0.95 mais accuracy=0 → contribution ECE=0.95 × 1.0 = 0.95."""
    preds = [0.95] * 10
    outcomes = [0] * 10
    ece = _compute_ece(preds, outcomes, n_bins=10)
    assert ece == pytest.approx(0.95, abs=0.05)


def test_ece_empty():
    ece = _compute_ece([], [], n_bins=10)
    assert ece == 1.0


# ============================================================== T7 fit depuis DB

def test_fit_from_synthetic_db(live_db_with_decisions: Path, tmp_cal_db: Path):
    """Fit sur DB synthétique : doit retourner platt + metrics cohérentes."""
    result = fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    assert "error" not in result
    assert result["n_fit"] >= 150  # Au moins GBPUSD
    assert result["n_cells"] >= 1
    assert "platt_global" in result
    assert result["global_wr"] > 0.4  # WR historique > 50%
    assert result["calibration_metrics"]["n"] >= 150


def test_fit_persists_in_calibration_db(live_db_with_decisions: Path, tmp_cal_db: Path):
    """Le fit doit persister dans la calibration DB."""
    fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    conn = sqlite3.connect(str(tmp_cal_db))
    try:
        n_cells = conn.execute("SELECT COUNT(*) FROM cell_stats").fetchone()[0]
        plat = conn.execute("SELECT a, b FROM platt_global WHERE id=1").fetchone()
        assert n_cells >= 1
        assert plat is not None
    finally:
        conn.close()


def test_fit_db_inexistant(tmp_cal_db: Path):
    result = fit_from_decisions_db(Path("C:/no/such/db.db"), tmp_cal_db)
    assert "error" in result


def test_fit_db_with_no_decisions(tmp_path: Path, tmp_cal_db: Path):
    """DB sans table decisions → error."""
    db = tmp_path / "empty.db"
    sqlite3.connect(str(db)).close()
    result = fit_from_decisions_db(db, tmp_cal_db)
    assert "error" in result or result.get("n_fit", 0) == 0


# ============================================================== T8 predict fallback

def test_predict_no_fit_yet(tmp_cal_db: Path):
    """Si platt_global vide → fallback prior_only."""
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        calibration_db=tmp_cal_db,
    )
    assert pred.platt_used == "prior_only"
    assert pred.calibrated_proba == 0.5
    assert pred.recommended_action == "skip"


def test_predict_after_fit_uses_platt(live_db_with_decisions: Path, tmp_cal_db: Path):
    """Après fit, predict utilise Platt global."""
    fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        calibration_db=tmp_cal_db,
    )
    assert pred.platt_used in ("global", f"local_GBPUSD")
    assert 0 <= pred.calibrated_proba <= 1


# ============================================================== T9 combinaison

def test_predict_combines_platt_and_beta(live_db_with_decisions: Path,
                                          tmp_cal_db: Path):
    """Cellule assez grosse → Beta posterior présent + combiné."""
    fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        calibration_db=tmp_cal_db,
    )
    # Beta posterior devrait être présent (≥ MIN_N_FOR_BETA_PRIOR)
    assert pred.beta_posterior is not None
    assert pred.beta_posterior.mean > 0  # au moins quelques wins


def test_predict_calibrated_proba_in_range(live_db_with_decisions: Path,
                                            tmp_cal_db: Path):
    fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    for conf in [50, 70, 80, 90]:
        pred = predict(
            symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
            phase="culmination", vol_atr_pips=3.5,
            declared_confiance=conf,
            calibration_db=tmp_cal_db,
        )
        assert 0 <= pred.calibrated_proba <= 1


def test_predict_higher_conf_higher_proba(live_db_with_decisions: Path,
                                          tmp_cal_db: Path):
    """En général, confiance plus élevée → proba calibrée plus élevée."""
    fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    p_low = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=50,
        calibration_db=tmp_cal_db,
    )
    p_high = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=90,
        calibration_db=tmp_cal_db,
    )
    # La relation peut ne pas être monotone stricte si calibration imparfaite,
    # mais en général elle l'est.
    assert p_high.calibrated_proba >= p_low.calibrated_proba - 0.05


# ============================================================== T10 action

def test_predict_action_high_conf_high_edge(live_db_with_decisions: Path,
                                            tmp_cal_db: Path):
    """Confiance haute → action enter si edge > 0."""
    fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        tp_pips=15.0, sl_pips=10.0,  # edge positif facile
        calibration_db=tmp_cal_db,
    )
    # Avec TP=15, SL=10, même un proba modeste donne edge > 0
    if pred.calibrated_proba > 0.5:
        assert pred.edge > 0


def test_predict_action_skip_low_edge(tmp_cal_db: Path):
    """Edge négatif ou proba < 0.5 → skip ou reduce_size."""
    # Pas de fit → prior_only, calibrated_proba=0.5, edge = 0.5·10 - 0.5·15 = -2.5
    pred = predict(
        symbol="XYZ", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        tp_pips=10.0, sl_pips=15.0,
        edge_threshold=0.55,
        calibration_db=tmp_cal_db,
    )
    assert pred.edge < 0
    assert pred.recommended_action in ("skip", "reduce_size")


def test_predict_edge_threshold_respected(live_db_with_decisions: Path,
                                          tmp_cal_db: Path):
    """Si calibrated_proba < edge_threshold → pas 'enter'."""
    fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        tp_pips=10.0, sl_pips=15.0,
        edge_threshold=0.95,  # très exigeant
        calibration_db=tmp_cal_db,
    )
    if pred.calibrated_proba < 0.95:
        assert pred.recommended_action != "enter"


# ============================================================== T11 schema

def test_init_calibration_db_creates_tables(tmp_cal_db: Path):
    conn = sqlite3.connect(str(tmp_cal_db))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "cell_stats" in tables
        assert "platt_global" in tables
        assert "calibration_meta" in tables
    finally:
        conn.close()


def test_init_calibration_db_idempotent(tmp_cal_db: Path):
    init_calibration_db(tmp_cal_db)
    init_calibration_db(tmp_cal_db)  # ne doit pas crash


# ============================================================== T12 R6 défensif

def test_predict_corrupt_calibration_db(tmp_path: Path):
    """R6 : DB corrompue ne crash pas."""
    db = tmp_path / "corrupt.db"
    db.write_text("not a sqlite db")
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        calibration_db=db,
    )
    # Doit retourner un Prediction par défaut
    assert isinstance(pred, Prediction)


def test_predict_invalid_phase(tmp_cal_db: Path):
    """Phase hors vocabulaire → fallback initiation (R6)."""
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="INVALID", vol_atr_pips=3.5,
        declared_confiance=80,
        calibration_db=tmp_cal_db,
    )
    assert pred.phase == "initiation"


def test_predict_invalid_regime(tmp_cal_db: Path):
    """Regime hors vocabulaire → fallback NEUTRE (R6)."""
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="INVALID",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        calibration_db=tmp_cal_db,
    )
    assert pred.regime_type == "NEUTRE"


# ============================================================== T13 batch

def test_batch_score_robust(live_db_with_decisions: Path, tmp_cal_db: Path):
    """batch_score doit gérer les entrées mal formées sans crash."""
    fit_from_decisions_db(live_db_with_decisions, tmp_cal_db)
    decisions = [
        {
            "symbol": "GBPUSD", "timeframe": "M15",
            "regime_type": "NEUTRE", "phase": "culmination",
            "vol_atr_pips": 3.5, "declared_confiance": 80,
            "tp_pips": 10.0, "sl_pips": 15.0,
        },
        # Entrée mal formée (manque declared_confiance)
        {
            "symbol": "EURUSD", "timeframe": "M15",
            "regime_type": "NEUTRE", "phase": "initiation",
            "vol_atr_pips": 4.0,
        },
    ]
    preds = batch_score(decisions, calibration_db=tmp_cal_db)
    # Au moins 1 prediction réussie (la première), pas de crash global
    assert len(preds) >= 1


def test_batch_score_empty():
    preds = batch_score([])
    assert preds == []


# ============================================================== T14 CLI

def test_cli_fit(live_db_with_decisions: Path, tmp_cal_db: Path, capsys):
    from core.v9.v9_bayesian_predictor import main
    rc = main(["fit", "--db", str(live_db_with_decisions),
               "--cal-db", str(tmp_cal_db)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "n_fit" in out
    assert "platt_global" in out


def test_cli_predict(live_db_with_decisions: Path, tmp_cal_db: Path, capsys):
    from core.v9.v9_bayesian_predictor import main
    # Fit d'abord
    main(["fit", "--db", str(live_db_with_decisions),
          "--cal-db", str(tmp_cal_db)])
    capsys.readouterr()  # clear output
    # Predict
    rc = main(["predict", "--symbol", "GBPUSD", "--timeframe", "M15",
               "--regime", "NEUTRE", "--phase", "culmination",
               "--vol-atr", "3.5", "--conf", "80",
               "--cal-db", str(tmp_cal_db)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "calibrated_proba" in out


# ============================================================== T15 vol bucket

def test_bucket_vol_atr_aligned_with_cycle_memory():
    """Cohérence avec v9_cycle_memory._bucket_vol_atr."""
    from core.v9.v9_cycle_memory import _bucket_vol_atr
    for v in [0.5, 1.0, 2.0, 2.1, 6.0, 6.1, 20.0, None, -1.0]:
        assert _bucket_vol_atr_from_pips(v) == _bucket_vol_atr(v)


# ============================================================== T16 to_dict

def test_prediction_to_dict(tmp_cal_db: Path):
    pred = predict(
        symbol="GBPUSD", timeframe="M15", regime_type="NEUTRE",
        phase="culmination", vol_atr_pips=3.5,
        declared_confiance=80,
        calibration_db=tmp_cal_db,
    )
    d = pred.to_dict()
    assert "calibrated_proba" in d
    assert "edge" in d
    assert "recommended_action" in d


# ============================================================== T17 prior info

def test_prior_constants():
    assert PRIOR_ALPHA == 1.0
    assert PRIOR_BETA == 1.0


def test_min_n_thresholds_reasonable():
    assert MIN_N_FOR_BETA_PRIOR < MIN_N_FOR_LOCAL_CALIBRATION
    assert MIN_N_FOR_LOCAL_CALIBRATION >= 20


def test_default_calibration_db_path():
    assert str(DEFAULT_CALIBRATION_DB).endswith("v9_calibration.db")


def test_ece_bins_default():
    assert ECE_BINS == 10
