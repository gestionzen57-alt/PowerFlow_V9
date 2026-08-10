"""V10 Fatman Bible Signals — tests (FATMAN BIBLE §5-§7).

Couvre :
  - Constantes (GAP, SIGMA, SAFE_HAVEN_CURRENCIES — ré-exportées)
  - Les 6 signaux S1-S6
  - Les 6 filtres Edge Fund
  - Les 4 principes Fatboy
  - apply_all_filters composite
  - R6 fail-open (données vides, paires invalides)
  - R9 audit (dataclass as_dict)

Total : 30 tests minimum. 0 import core/v9/ (R2 additif).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_fatman_bible_signals import (  # noqa: E402
    GAP_INSTITUTION,
    GAP_STANDARD,
    SIGMA_CONVERGENCE,
    SIGMA_DIVERGENCE,
    SAFE_HAVEN_CURRENCIES,
    BibleFilterResult,
    BibleSignalResult,
    apply_all_filters,
    filter_atr_dynamics,
    filter_correlation_with_open_positions,
    filter_news_window,
    filter_session,
    filter_spread,
    filter_sigma,
    principle_harmonie_tf,
    principle_safe_haven_filter,
    principle_sigma_check,
    principle_volume_required,
    signal_1_forte_faible,
    signal_2_inst,
    signal_3_divergence,
    signal_4_safe_haven_flip,
    signal_5_convergence,
    signal_6_continuation_mtf,
    # Z11 : Signal 7 — PRÉ-VAGUE
    signal_7_pre_wave,
)


def _fatman_scores_strong_usd() -> dict:
    """USD fort (90), EUR/JPY/CHF moyens, autres bas — gap élevé sur EURUSD."""
    return {"USD": 90.0, "EUR": 30.0, "JPY": 50.0, "CHF": 50.0,
            "GBP": 55.0, "CAD": 60.0, "AUD": 65.0, "NZD": 70.0}


def _fatman_scores_safe_haven() -> dict:
    """JPY + CHF dans top 3 → safe haven actif."""
    return {"JPY": 95.0, "CHF": 92.0, "USD": 60.0, "EUR": 55.0,
            "GBP": 50.0, "CAD": 45.0, "AUD": 40.0, "NZD": 38.0}


def _fatman_scores_neutral() -> dict:
    """8 devises autour de 50 (sigma < 12)."""
    return {"USD": 50.0, "EUR": 51.0, "JPY": 49.0, "CHF": 52.0,
            "GBP": 50.0, "CAD": 51.0, "AUD": 49.0, "NZD": 48.0}


# ─────────────────────────────────────────────────────────────────────
# Constantes (ré-exportées depuis FatmanCalculator)
# ─────────────────────────────────────────────────────────────────────
def test_constants_re_exported():
    assert GAP_STANDARD == 35.0
    assert GAP_INSTITUTION == 48.0
    assert SIGMA_CONVERGENCE == 12.0
    assert SIGMA_DIVERGENCE == 28.0
    assert SAFE_HAVEN_CURRENCIES == {"JPY", "CHF"}


# ─────────────────────────────────────────────────────────────────────
# BibleSignalResult dataclass
# ─────────────────────────────────────────────────────────────────────
def test_bible_signal_serialisable():
    s = BibleSignalResult(signal_id=1, pair="EURUSD", direction="LONG")
    json.dumps(s.as_dict())


def test_bible_filter_serialisable():
    r = BibleFilterResult("1", "session", True, "OK")
    json.dumps(r.as_dict())


# ─────────────────────────────────────────────────────────────────────
# Signal 1 — FORTE × FAIBLE Standard
# ─────────────────────────────────────────────────────────────────────
def test_signal_1_standard():
    s = signal_1_forte_faible("EURUSD", _fatman_scores_strong_usd())
    assert s is not None
    assert s.signal_id == 1
    assert s.pair == "EURUSD"
    assert s.direction in ("LONG", "SHORT")
    assert s.gap >= GAP_STANDARD


def test_signal_1_institutionnel_flag():
    """EUR 30 vs USD 90 = gap 60 >= GAP_INSTITUTION (48) → institutionnel."""
    s = signal_1_forte_faible("EURUSD", _fatman_scores_strong_usd())
    assert s.is_institutional is True


def test_signal_1_pas_de_signal_faible_gap():
    """8 devises autour de 50 → gap < 35 → None."""
    s = signal_1_forte_faible("EURUSD", _fatman_scores_neutral())
    assert s is None


def test_signal_1_paire_invalide_none():
    assert signal_1_forte_faible("XX", _fatman_scores_strong_usd()) is None


# ─────────────────────────────────────────────────────────────────────
# Signal 2 — FORTE × FAIBLE Institutionnel
# ─────────────────────────────────────────────────────────────────────
def test_signal_2_inst_threshold():
    s = signal_2_inst("EURUSD", _fatman_scores_strong_usd())
    assert s is not None
    assert s.is_institutional is True
    assert s.gap >= GAP_INSTITUTION
    assert s.wr_target == 71.0
    assert s.rr_target == 2.5


def test_signal_2_pas_sous_seuil():
    s = signal_2_inst("EURUSD", _fatman_scores_neutral())
    assert s is None


# ─────────────────────────────────────────────────────────────────────
# Signal 3 — DIVERGENCE EXTRÊME
# ─────────────────────────────────────────────────────────────────────
def test_signal_3_sigma_eleve():
    """Force σ > 28 en mettant des scores très dispersés."""
    scores = {"USD": 100.0, "EUR": 10.0, "JPY": 5.0, "CHF": 0.0,
              "GBP": 90.0, "CAD": 50.0, "AUD": 40.0, "NZD": 30.0}
    s = signal_3_divergence("EURUSD", scores)
    if s is not None:
        assert s.signal_id == 3
        assert s.sigma > SIGMA_DIVERGENCE


def test_signal_3_fail_si_sigma_faible():
    """σ faible (devises serrées) → aucun signal."""
    s = signal_3_divergence("EURUSD", _fatman_scores_neutral())
    assert s is None


# ─────────────────────────────────────────────────────────────────────
# Signal 4 — SAFE HAVEN FLIP (Fatboy)
# ─────────────────────────────────────────────────────────────────────
def test_signal_4_safe_haven_actif():
    """JPY + CHF dans top 3 → safe haven, vente risk-on."""
    pairs = ["AUDUSD", "NZDUSD", "USDJPY", "USDCHF"]
    results = signal_4_safe_haven_flip(_fatman_scores_safe_haven(),
                                       pairs=pairs)
    assert len(results) > 0
    assert all(r.is_safe_haven for r in results)


def test_signal_4_safe_haven_non_actif():
    """USD fort normal, JPY/CHF pas dans top 3 → 0 resultats."""
    res = signal_4_safe_haven_flip(_fatman_scores_strong_usd(),
                                    pairs=["EURUSD", "GBPUSD"])
    assert res == []


# ─────────────────────────────────────────────────────────────────────
# Signal 5 — CONVERGENCE FORTE
# ─────────────────────────────────────────────────────────────────────
def test_signal_5_convergence_sigma_bas_devises_serre():
    """σ < 12 (devises serrées) + top_2 séparé : signal de convergence."""
    scores = _fatman_scores_neutral()
    # Rendre top_2 = USD 80, EUR 60 (séparation 20 > 15)
    scores["USD"], scores["EUR"] = 80.0, 60.0
    s = signal_5_convergence("EURUSD", scores)
    if s is not None:
        assert s.signal_id == 5
        assert s.notes[0].startswith("CONVERGENCE")


def test_signal_5_sigma_eleve_donne_none():
    """σ > 12 → pas de convergence signal."""
    s = signal_5_convergence("EURUSD", _fatman_scores_strong_usd())
    assert s is None


# ─────────────────────────────────────────────────────────────────────
# Signal 6 — CONTINUATION M30 → H1 ALIGNÉ
# ─────────────────────────────────────────────────────────────────────
def test_signal_6_continuation_aligned():
    """M30 et H1 même direction (LONG base) → continuation."""
    m30 = {"EUR": 70.0, "USD": 50.0}
    h1 = {"EUR": 80.0, "USD": 50.0}
    s = signal_6_continuation_mtf("EURUSD", m30, h1)
    assert s is not None
    assert s.signal_id == 6
    assert s.is_aligned_mtf
    assert s.direction == "LONG"


def test_signal_6_opposes_mtf_donne_none():
    m30 = {"EUR": 70.0, "USD": 50.0}
    h1 = {"EUR": 30.0, "USD": 50.0}  # bearish H1
    s = signal_6_continuation_mtf("EURUSD", m30, h1)
    assert s is None


# ─────────────────────────────────────────────────────────────────────
# 6 filtres Edge Fund
# ─────────────────────────────────────────────────────────────────────
def test_filter_session_london():
    r = filter_session(10)  # 10 UTC = London
    assert r.passed


def test_filter_session_ny():
    r = filter_session(15)  # 15 UTC = NY
    assert r.passed


def test_filter_session_hors_session():
    r = filter_session(3)  # 3 UTC = Asian
    assert not r.passed


def test_filter_atr_dynamics_ok():
    r = filter_atr_dynamics(0.0010, 0.0008)  # ratio 1.25 > 0.7
    assert r.passed


def test_filter_atr_dynamics_calme():
    r = filter_atr_dynamics(0.0001, 0.0010)  # ratio 0.1
    assert not r.passed


def test_filter_atr_dynamics_invalide():
    r = filter_atr_dynamics(0, 0.0010)
    assert not r.passed


def test_filter_spread_ok():
    r = filter_spread(1.0, 1.0)  # ratio 1.0 < 2.0
    assert r.passed


def test_filter_spread_anormal():
    r = filter_spread(3.0, 1.0)  # ratio 3.0 > 2.0
    assert not r.passed


def test_filter_correlation_pas_d_open():
    r = filter_correlation_with_open_positions("EURUSD", {}, [])
    assert r.passed


def test_filter_correlation_open_correlee():
    corr = {"GBPUSD": 0.85}
    positions = ["GBPUSD"]
    r = filter_correlation_with_open_positions("EURUSD", corr, positions)
    assert not r.passed


def test_filter_correlation_open_decorrelee():
    corr = {"USDJPY": 0.4}
    positions = ["USDJPY"]
    r = filter_correlation_with_open_positions("EURUSD", corr, positions)
    assert r.passed


def test_filter_news_window_proche():
    r = filter_news_window(minutes_to_news=15)
    assert not r.passed


def test_filter_news_window_loin():
    r = filter_news_window(minutes_to_news=120)
    assert r.passed


def test_filter_news_window_failopen():
    """R6 : si pas de données news → fail-open pass."""
    r = filter_news_window(None)
    assert r.passed


def test_filter_sigma_ok():
    r = filter_sigma(15.0)
    assert r.passed


def test_filter_sigma_trop_bruit():
    r = filter_sigma(40.0)
    assert not r.passed


def test_filter_sigma_invalide():
    r = filter_sigma(0.0)
    assert not r.passed


# ─────────────────────────────────────────────────────────────────────
# 4 principes Fatboy
# ─────────────────────────────────────────────────────────────────────
def test_principle_sigma_check_convergence():
    ok, why = principle_sigma_check(8.0)
    assert ok and "convergence" in why


def test_principle_sigma_check_divergence():
    ok, why = principle_sigma_check(35.0)
    assert ok and "divergence" in why


def test_principle_sigma_check_zone_grise():
    ok, why = principle_sigma_check(20.0)
    assert not ok
    assert "zone grise" in why


def test_principle_harmonie_tf_aligned():
    m30 = {"EUR": 70.0, "USD": 50.0}
    h1 = {"EUR": 70.0, "USD": 50.0}
    assert principle_harmonie_tf(m30, h1, "EURUSD")


def test_principle_harmonie_tf_oppose():
    m30 = {"EUR": 70.0, "USD": 50.0}
    h1 = {"EUR": 30.0, "USD": 70.0}
    assert not principle_harmonie_tf(m30, h1, "EURUSD")


def test_principle_safe_haven_filter_actif():
    """Safe haven actif → pas d'entrée (filtrage)."""
    f = principle_safe_haven_filter(_fatman_scores_safe_haven())
    assert not f  # False → ne PAS entrer


def test_principle_safe_haven_filter_inactif():
    """Pas safe haven → OK pour entrer."""
    f = principle_safe_haven_filter(_fatman_scores_strong_usd())
    assert f


def test_principle_volume_required_ok():
    assert principle_volume_required(900, 1000)  # ratio 0.9 >= 0.8


def test_principle_volume_required_insuffisant():
    assert not principle_volume_required(100, 1000)  # ratio 0.1


def test_principle_volume_required_invalide():
    assert not principle_volume_required(100, 0)


# ─────────────────────────────────────────────────────────────────────
# Composite apply_all_filters
# ─────────────────────────────────────────────────────────────────────
def test_apply_all_filters_tous_verts():
    sig = BibleSignalResult(signal_id=1, pair="EURUSD", direction="LONG",
                              gap=60, sigma=15)
    r = apply_all_filters(
        sig,
        hour_utc=10, atr_now=0.0010, avg_atr_20d=0.0008,
        spread_now=1.0, spread_avg_daily=1.0, sigma=15,
        candidate_pair="EURUSD",
        corr_with_open={"GBPUSD": 0.3}, open_pairs=["GBPUSD"],
        minutes_to_news=120,
    )
    assert r.is_actionable
    assert all(r.filters_passed.values())


def test_apply_all_filters_uno_fail():
    sig = BibleSignalResult(signal_id=1, pair="EURUSD", direction="LONG",
                              gap=60, sigma=15)
    r = apply_all_filters(
        sig,
        hour_utc=3,  # FAIL session
        atr_now=0.0010, avg_atr_20d=0.0008,
        spread_now=1.0, spread_avg_daily=1.0, sigma=15,
        candidate_pair="EURUSD",
    )
    assert not r.is_actionable
    assert r.filters_passed["1"] is False  # session


# ─────────────────────────────────────────────────────────────────────
# R6 fail-open + R9 audit
# ─────────────────────────────────────────────────────────────────────
def test_r6_signaux_sur_data_vide():
    assert signal_1_forte_faible("EURUSD", {}) is None
    assert signal_2_inst("EURUSD", {}) is None


def test_r6_signal_safe_haven_renvoie_liste_vide():
    assert signal_4_safe_haven_flip({}, pairs=["EURUSD"]) == []


def test_r9_signal_audit_champs_complets():
    s = signal_1_forte_faible("EURUSD", _fatman_scores_strong_usd())
    d = s.as_dict()
    for k in ("signal_id", "pair", "direction", "confidence", "gap",
              "wr_target", "rr_target", "notes"):
        assert k in d


# ─────────────────────────────────────────────────────────────────────
# Signal 7 — PRÉ-VAGUE (Z11, 2026-08-10)
# ─────────────────────────────────────────────────────────────────────
def _compression_series() -> list:
    """Série sigma : compression nette en fin (récent << historique).

    recent_mean ≈ 26.4 vs hist_mean ≈ 46.0 → ratio ≈ 0.574 ≤ 0.60.
    """
    return [70.0, 68.0, 72.0, 65.0, 69.0, 66.0, 64.0, 61.0, 58.0,
            55.0, 52.0, 48.0, 42.0, 38.0, 34.0, 30.0, 27.0, 24.0,
            21.0, 18.0, 16.0, 14.0]


def _stable_series() -> list:
    """Série stable : pas de compression."""
    return [50.0] * 22


def test_z11_signal_7_pre_wave_compression():
    """Compression sigma + gap ≥ 30 → pré-vague direction base faible."""
    s = signal_7_pre_wave(
        _compression_series(), "EURUSD",
        {"EUR": 30.0, "USD": 90.0},  # base EUR faible → SHORT anticipé
    )
    assert s is not None
    assert s.signal_id == 7
    assert s.direction == "SHORT"
    assert s.wr_target == 65.0
    assert any("PRÉ-VAGUE" in n for n in s.notes)


def test_z11_signal_7_long_when_base_forte():
    """Base forte (delta > 0) → LONG anticipé malgré compression."""
    s = signal_7_pre_wave(
        _compression_series(), "EURUSD",
        {"EUR": 90.0, "USD": 30.0},  # base EUR forte → LONG anticipé
    )
    assert s is not None
    assert s.direction == "LONG"


def test_z11_signal_7_pas_de_compression_donne_none():
    """Série stable (pas de compression) → aucun signal."""
    s = signal_7_pre_wave(
        _stable_series(), "EURUSD",
        {"EUR": 30.0, "USD": 90.0},
    )
    assert s is None


def test_z11_signal_7_gap_insuffisant_donne_none():
    """Compression mais gap < 30 → pas d'entrée anticipée."""
    s = signal_7_pre_wave(
        _compression_series(), "EURUSD",
        {"EUR": 50.0, "USD": 60.0},  # gap 10 < 30
    )
    assert s is None


def test_z11_signal_7_historique_trop_court_failopen():
    """R6 : < 20 points → None (jamais d'exception)."""
    s = signal_7_pre_wave(
        [70.0, 65.0, 60.0, 55.0, 50.0], "EURUSD",
        {"EUR": 30.0, "USD": 90.0},
    )
    assert s is None


def test_z11_signal_7_confiance_gap():
    """Confidence = |delta| du gap Fatman."""
    s = signal_7_pre_wave(
        _compression_series(), "EURUSD",
        {"EUR": 20.0, "USD": 80.0},  # gap 60
    )
    assert s is not None
    assert s.confidence == 60.0
    assert s.gap == 60.0


def test_z11_signal_7_exported_in_all():
    """Z11 : signal_7_pre_wave exporté dans __all__ (R2 additif)."""
    from core.v10.v10_fatman_bible_signals import __all__ as bible_all
    assert "signal_7_pre_wave" in bible_all


def test_z11_wave_predictor_module_standalone():
    """Le détecteur fondation (H7) fonctionne en autonome (R6 fail-open)."""
    from core.v10.v10_fatman_wave_predictor import (
        PreWaveAlert,
        detect_pre_wave,
    )
    alert = detect_pre_wave(_compression_series())
    assert alert.pre_wave is True
    assert alert.compression_ratio <= 0.60
    assert alert.sigma_recent < alert.sigma_hist
    # fail-open : historique court
    assert detect_pre_wave([60.0, 50.0]).pre_wave is False
    # sérialisable (R9)
    import json
    json.dumps(alert.as_dict())
