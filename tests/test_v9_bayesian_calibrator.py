"""Tests — bayesian_calibrator (Axe 1.1 J1, 2026-07-21).

Couvre BetaPosterior (moments, IC 95 %, prob_above), BayesianCalibrator
(fit_context / fit_all_contexts / is_edge_real / kelly_fraction), BrierScorer
(brier / reliability / Platt) et l'intégration signal_generator.calibrate_confidence.

R7 strict : ≥17 tests. Math pure vérifiée contre des valeurs fermées connues ;
le fallback pur (sans scipy) est exercé par les tests même quand scipy est présent
via `_betai` directement.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.v9 import bayesian_calibrator as bc
from core.v9.bayesian_calibrator import (
    BayesianCalibrator,
    BetaPosterior,
    BrierScorer,
)
from core.v9.signal_generator import calibrate_confidence


# ── BetaPosterior — moments ──────────────────────────────────────────
def test_beta_posterior_mean_uniform_prior():
    """Beta(1,1) (prior uniforme) a une moyenne de 0.5."""
    assert BetaPosterior(1.0, 1.0, 0).mean == pytest.approx(0.5)


def test_beta_posterior_mean_with_data():
    """Beta(11,3) (10 wins, 2 losses + prior) → mean ≈ 0.786."""
    assert BetaPosterior(11.0, 3.0, 12).mean == pytest.approx(11 / 14, abs=1e-9)


def test_beta_posterior_variance_decreases_with_n():
    """La variance postérieure décroît quand n (donc α+β) augmente."""
    assert BetaPosterior(2.0, 2.0, 2).variance > BetaPosterior(20.0, 20.0, 38).variance


def test_beta_posterior_invalid_params_raise():
    """α ou β ≤ 0 est invalide (garde-fou constructeur)."""
    with pytest.raises(ValueError):
        BetaPosterior(0.0, 1.0, 0)


# ── BetaPosterior — IC 95 % et prob_above ────────────────────────────
def test_credible_interval_95_contains_mean():
    """La moyenne est strictement à l'intérieur de l'IC 95 %."""
    post = BetaPosterior(11.0, 3.0, 12)
    lo, hi = post.credible_interval_95()
    assert lo < post.mean < hi
    assert 0.0 <= lo < hi <= 1.0


def test_prob_above_threshold_symmetric():
    """Beta(50,50) est symétrique autour de 0.5 → prob_above(0.5) ≈ 0.5."""
    assert BetaPosterior(50.0, 50.0, 98).prob_above(0.5) == pytest.approx(0.5, abs=1e-6)


def test_pure_python_betai_matches_scipy_when_available():
    """Le fallback pur `_betai` reproduit la CDF Beta (référence scipy si dispo,
    sinon valeurs fermées : CDF Beta(1,1)=x, symétrie Beta(a,a) en 0.5=0.5)."""
    # Beta(1,1) est la loi uniforme : CDF(x) = x.
    assert bc._betai(1.0, 1.0, 0.37) == pytest.approx(0.37, abs=1e-9)
    # Symétrie : CDF_Beta(a,a)(0.5) = 0.5.
    assert bc._betai(8.0, 8.0, 0.5) == pytest.approx(0.5, abs=1e-9)
    if bc._HAS_SCIPY:
        try:
            from scipy.stats import beta as sb
            ref = float(sb.cdf(0.5, 80, 20))
        except Exception:  # OpenBLAS OOM intermittent sur cet hôte — cross-check optionnel
            pytest.skip("scipy indisponible à l'exécution (OpenBLAS)")
        assert bc._betai(80.0, 20.0, 0.5) == pytest.approx(ref, abs=1e-9)


# ── is_edge_real ─────────────────────────────────────────────────────
def test_is_edge_real_positive_case():
    """Beta(80,20) : edge fortement crédible → is_edge=True, p_value<0.01."""
    calib = BayesianCalibrator(db_path="unused")
    is_edge, p_value = calib.is_edge_real(BetaPosterior(80.0, 20.0, 98))
    assert is_edge is True
    assert p_value < 0.01


def test_is_edge_real_negative_case():
    """Beta(50,50) : indiscernable du bruit → is_edge=False, p_value≈0.5."""
    calib = BayesianCalibrator(db_path="unused")
    is_edge, p_value = calib.is_edge_real(BetaPosterior(50.0, 50.0, 98))
    assert is_edge is False
    assert p_value == pytest.approx(0.5, abs=1e-6)


# ── kelly_fraction ───────────────────────────────────────────────────
def test_kelly_fraction_basic():
    """p=0.7, b=1, fraction=1.0 → Kelly complet (0.7−0.3)/1 = 0.4."""
    calib = BayesianCalibrator(db_path="unused")
    post = BetaPosterior(70.0, 30.0, 100)  # mean 0.7, edge confirmé
    assert calib.kelly_fraction(post, rr=1.0, fraction=1.0) == pytest.approx(0.4, abs=1e-9)


def test_kelly_fraction_with_floor():
    """Edge réel mais faible (p=0.52, n grand) → multiplicateur clampé au floor 0.3."""
    calib = BayesianCalibrator(db_path="unused")
    post = BetaPosterior(5200.0, 4800.0, 10000)  # mean 0.52, prob_above(0.5)≈1
    assert post.prob_above(0.5) >= calib.MIN_PROB_EDGE
    assert calib.kelly_fraction(post) == pytest.approx(0.3, abs=1e-9)


def test_kelly_fraction_with_cap():
    """p=0.95 : multiplicateur f_full/fraction = 0.9/0.25 = 3.6 → clampé au cap 2.0."""
    calib = BayesianCalibrator(db_path="unused")
    post = BetaPosterior(95.0, 5.0, 100)  # mean 0.95
    assert calib.kelly_fraction(post) == pytest.approx(2.0, abs=1e-9)


def test_kelly_fraction_none_if_n_low():
    """n < 20 → None (échantillon trop court, kill)."""
    calib = BayesianCalibrator(db_path="unused")
    assert calib.kelly_fraction(BetaPosterior(7.0, 4.0, 10)) is None


def test_kelly_fraction_none_if_edge_unconfirmed():
    """prob_above(0.5) < 0.6 (edge non confirmé) → None malgré n ≥ 20."""
    calib = BayesianCalibrator(db_path="unused")
    # Beta(11,10) : mean≈0.52 mais prob_above(0.5)≈0.55 < 0.6.
    post = BetaPosterior(11.0, 10.0, 25)  # n forcé ≥ 20 pour isoler le garde-fou d'edge
    assert post.prob_above(0.5) < calib.MIN_PROB_EDGE
    assert calib.kelly_fraction(post) is None


# ── BrierScorer ──────────────────────────────────────────────────────
def test_brier_score_perfect():
    """Prédictions parfaites [1.0, 0.0] vs [1, 0] → Brier 0.0."""
    assert BrierScorer.brier_score([1.0, 0.0], [1, 0]) == pytest.approx(0.0)


def test_brier_score_random():
    """Prédictions 0.5 systématiques → Brier 0.25 (aléatoire)."""
    assert BrierScorer.brier_score([0.5, 0.5], [1, 0]) == pytest.approx(0.25)


def test_reliability_table_bins():
    """100 prédictions réparties → toujours 10 bins, comptes sommant à 100."""
    preds = [i / 100.0 for i in range(100)]
    outs = [1 if i >= 50 else 0 for i in range(100)]
    table = BrierScorer.reliability_table(preds, outs, n_bins=10)
    assert len(table) == 10
    assert sum(b["count"] for b in table) == 100
    # Bin bien calibré : dans le dernier bin (preds ~0.9), tous les outcomes=1.
    assert table[-1]["mean_outcome"] == pytest.approx(1.0)


def test_platt_scale_fit():
    """Platt fit sur données synthétiques séparables → A>0, et sur un holdout
    la sigmoïde ajustée sépare correctement les deux classes."""
    # Données : x bas → y=0, x haut → y=1 (séparation nette autour de 0.5).
    train_x, train_y = [], []
    for i in range(200):
        x = i / 200.0
        train_x.append(x)
        train_y.append(1 if x > 0.5 else 0)
    a, b = BrierScorer.platt_scale(train_x, train_y)
    assert a > 0.0  # corrélation positive confiance→gain
    # Holdout : prédictions calibrées cohérentes avec la vérité.
    assert BrierScorer.apply_platt(0.9, a, b) > 0.5
    assert BrierScorer.apply_platt(0.1, a, b) < 0.5


# ── Intégration DB (fit_context / calibrate_confidence) ──────────────
def _make_test_db(path: Path, rows: list[dict]) -> None:
    """Crée une DB minimale `decisions` (colonnes réelles utilisées)."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE decisions (principes_json TEXT, symbol TEXT, timeframe TEXT, "
        "regime_type TEXT, is_win INTEGER, confiance INTEGER, "
        "resolution_strategy TEXT, timestamp TEXT)"
    )
    conn.executemany(
        "INSERT INTO decisions (principes_json, symbol, timeframe, regime_type, "
        "is_win, confiance, resolution_strategy, timestamp) VALUES "
        "(:principes_json, :symbol, :timeframe, :regime_type, :is_win, :confiance, "
        ":resolution_strategy, :timestamp)",
        rows,
    )
    conn.commit()
    conn.close()


def _row(principle, is_win, symbol="GBPUSD", tf="M5", regime="NEUTRE", conf=80):
    return {
        "principes_json": f'["{principle}"]',
        "symbol": symbol,
        "timeframe": tf,
        "regime_type": regime,
        "is_win": is_win,
        "confiance": conf,
        "resolution_strategy": "DYNAMIC",
        # 10:00 UTC → session 'london', dans la fenêtre 30 j (date du jour).
        "timestamp": "2026-07-21T10:00:00+00:00",
    }


def test_fit_context_reads_db(tmp_path):
    """fit_context agrège wins/losses réels et applique le prior Beta(1,1)."""
    db = tmp_path / "t.db"
    rows = [_row("P_A", 1) for _ in range(30)] + [_row("P_A", 0) for _ in range(10)]
    _make_test_db(db, rows)
    calib = BayesianCalibrator(db_path=db)
    post = calib.fit_context(("P_A", "GBPUSD", "M5", "london", "NEUTRE"))
    assert post.n == 40
    assert post.alpha == pytest.approx(31.0)  # 1 + 30 wins
    assert post.beta == pytest.approx(11.0)   # 1 + 10 losses
    assert post.mean == pytest.approx(31 / 42, abs=1e-9)


def test_fit_context_unknown_returns_prior(tmp_path):
    """Contexte inconnu → prior Beta(1,1), n=0 (R6 : pas d'exception)."""
    db = tmp_path / "t.db"
    _make_test_db(db, [_row("P_A", 1) for _ in range(5)])
    calib = BayesianCalibrator(db_path=db)
    post = calib.fit_context(("INEXISTANT", "GBPUSD", "M5", "london", "NEUTRE"))
    assert post.n == 0
    assert post.mean == pytest.approx(0.5)


def test_fit_all_contexts_min_n(tmp_path):
    """fit_all_contexts ne retient que les contextes n ≥ min_n."""
    db = tmp_path / "t.db"
    rows = [_row("P_A", 1) for _ in range(25)] + [_row("P_B", 1) for _ in range(5)]
    _make_test_db(db, rows)
    calib = BayesianCalibrator(db_path=db)
    contexts = calib.fit_all_contexts(min_n=20)
    keys = {k[0] for k in contexts}
    assert "P_A" in keys
    assert "P_B" not in keys  # n=5 < 20


def test_calibrate_confidence_with_posterior(tmp_path):
    """signal_generator.calibrate_confidence renvoie posterior.mean quand n≥20."""
    db = tmp_path / "t.db"
    rows = [_row("P_A", 1) for _ in range(30)] + [_row("P_A", 0) for _ in range(10)]
    _make_test_db(db, rows)
    calib = BayesianCalibrator(db_path=db)
    key = ("P_A", "GBPUSD", "M5", "london", "NEUTRE")
    out = calibrate_confidence(80.0, key, calib)
    assert out == pytest.approx(31 / 42, abs=1e-9)  # posterior.mean, pas 0.80


def test_calibrate_confidence_fallback(tmp_path):
    """Contexte sans données (n<20) → fallback raw_conf/100."""
    db = tmp_path / "t.db"
    _make_test_db(db, [_row("P_A", 1) for _ in range(5)])
    calib = BayesianCalibrator(db_path=db)
    out = calibrate_confidence(73.0, ("P_A", "GBPUSD", "M5", "london", "NEUTRE"), calib)
    assert out == pytest.approx(0.73)


def test_calibrate_confidence_db_inaccessible_fallback():
    """DB inexistante → fallback raw_conf/100 sans exception (R6)."""
    calib = BayesianCalibrator(db_path="C:/nope/does_not_exist_v9.db")
    out = calibrate_confidence(65.0, ("X", "Y", "Z", "london", "R"), calib)
    assert out == pytest.approx(0.65)
