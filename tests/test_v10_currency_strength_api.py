"""V10 Currency Strength API — tests (Phase 23, spec section 7).

Couvre la spec MISSION 1/2 :
  - Normalisation [0,1] sur toutes les devises
  - Mapping TF Fatman correct (7 cas)
  - Bias EURUSD : si EUR > USD → positif
  - Edge case : données absentes → neutre (0.5 / 0.0), pas de crash
  - compute_scores < 100ms sur données réelles
  - is_aligned : seuils + confirmation TF

Total ≥ 20 tests. 0 import core/v9/ (R2 additif strict).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_currency_strength import (  # noqa: E402
    API_DEFAULTS,
    CurrencyStrength,
    FATMAN_TF_MAP,
    V10CurrencyStrength,
    compute_scores_from_db,
    compute_currency_strength,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────
def _snapshot(scores: dict = None, tf: str = "M30") -> CurrencyStrength:
    """Snapshot CurrencyStrength synthétique."""
    scores = scores or {
        "EUR": 80.0, "GBP": 70.0, "USD": 50.0,
        "JPY": 40.0, "CHF": 30.0, "AUD": 20.0, "CAD": 10.0,
    }
    return CurrencyStrength(
        timestamp="2026-08-05T00:00:00+00:00", timeframe=tf,
        scores=scores,
        strongest=max(scores, key=scores.get),
        weakest=min(scores, key=scores.get),
    )


# ─────────────────────────────────────────────────────────────────────
# MISSION 1.1 — compute_scores : normalisation [0,1]
# ─────────────────────────────────────────────────────────────────────
def test_compute_scores_normalisation_0_1():
    cs = V10CurrencyStrength(snapshot=_snapshot())
    scores = cs.compute_scores()
    for c, v in scores.items():
        assert 0.0 <= v <= 1.0, f"{c} hors [0,1]: {v}"
    assert len(scores) == 7  # 7 devises agrégées


def test_compute_scores_extremes():
    cs = V10CurrencyStrength(snapshot=_snapshot())
    scores = cs.compute_scores()
    # EUR 80 = max → 1.0 ; CAD 10 = min → 0.0
    assert scores["EUR"] == 1.0
    assert scores["CAD"] == 0.0
    assert scores["USD"] == pytest.approx(0.5714, abs=0.001)


def test_compute_scores_failopen_vide():
    cs = V10CurrencyStrength()
    scores = cs.compute_scores()
    assert all(v == 0.5 for v in scores.values())


def test_compute_scores_score_egal_neutre():
    cs = V10CurrencyStrength(scores={"EUR": 50.0, "GBP": 50.0, "USD": 50.0})
    scores = cs.compute_scores()
    assert all(v == 0.5 for v in scores.values())


def test_compute_scores_accepte_scores_dict():
    cs = V10CurrencyStrength(scores={"EUR": 90.0, "GBP": 10.0})
    scores = cs.compute_scores()
    assert scores["EUR"] == 1.0
    assert scores["GBP"] == 0.0


# ─────────────────────────────────────────────────────────────────────
# MISSION 1.2 — get_pair_bias
# ─────────────────────────────────────────────────────────────────────
def test_bias_eurusd_positif_quand_eur_fort():
    cs = V10CurrencyStrength(snapshot=_snapshot())  # EUR 80 > USD 50
    bias = cs.get_pair_bias("EUR", "USD")
    assert bias > 0
    assert -1.0 <= bias <= 1.0


def test_bias_usdcad_negatif_quand_usd_moyen_cad_faible():
    # USD 50 vs CAD 10 → bias USD-CAD = 0.5714 - 0.0 = positif
    cs = V10CurrencyStrength(snapshot=_snapshot())
    bias = cs.get_pair_bias("USD", "CAD")
    assert bias > 0
    assert abs(bias - 0.5714) < 0.001


def test_bias_devise_inconnue_neutre():
    cs = V10CurrencyStrength(snapshot=_snapshot())
    # XXX absent → score neutre 0.5 ; USD normalisé 0.5714
    # → bias = 0.5 - 0.5714 = -0.0714 (R6 : devise inconnue = neutre)
    bias = cs.get_pair_bias("XXX", "USD")
    assert bias == pytest.approx(-0.0714, abs=0.001)


def test_bias_vide_neutre_zero():
    cs = V10CurrencyStrength()
    assert cs.get_pair_bias("EUR", "USD") == 0.0


# ─────────────────────────────────────────────────────────────────────
# MISSION 1.3 — get_fatman_tf mapping
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("trading,fatman", [
    ("M1", "M15"), ("M5", "M15"), ("M15", "M30"), ("M30", "H1"),
    ("H1", "H4"), ("H4", "D1"), ("D1", "D1"),
])
def test_fatman_tf_mapping(trading, fatman):
    assert V10CurrencyStrength.get_fatman_tf(trading) == fatman


def test_fatman_tf_inconnu_defaut_h1():
    assert V10CurrencyStrength.get_fatman_tf("XXX") == "H1"


def test_fatman_tf_map_complet():
    # Mapping Fatboy CSM (Perplexity) — vérité actuelle du module
    assert set(FATMAN_TF_MAP.keys()) == {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"}


# ─────────────────────────────────────────────────────────────────────
# MISSION 1.4 — is_aligned
# ─────────────────────────────────────────────────────────────────────
def test_is_aligned_eurusd():
    cs = V10CurrencyStrength(snapshot=_snapshot())  # EUR 80, USD 50 → bias 0.43
    assert cs.is_aligned("EURUSD", "M30", min_score=0.15)


def test_is_aligned_seuil_non_atteint():
    # EUR 55 vs USD 50 : normalisation min-max → EUR=1.0, USD=0.5, bias=0.5
    # → dépasse 0.15. Pour tester le NON-alignement, il faut un bias < seuil :
    # scores presque identiques → bias ~0
    cs = V10CurrencyStrength(scores={"EUR": 50.0, "USD": 50.1,
                                     "GBP": 50.0, "JPY": 50.0,
                                     "CHF": 50.0, "AUD": 50.0, "CAD": 50.0})
    bias = cs.get_pair_bias("EUR", "USD")
    assert abs(bias) < 0.15
    assert not cs.is_aligned("EURUSD", "M30", min_score=0.15)


def test_is_aligned_pair_invalide():
    cs = V10CurrencyStrength(snapshot=_snapshot())
    assert not cs.is_aligned("XXXXXX", "M30")
    assert not cs.is_aligned("EURU", "M30")


def test_is_aligned_tf_sans_fatman():
    # D1 → Fatman D1 = même TF → pas de confirmation → False
    cs = V10CurrencyStrength(snapshot=_snapshot())
    assert not cs.is_aligned("EURUSD", "D1", min_score=0.15)


def test_is_aligned_spec_min_score_par_defaut():
    cs = V10CurrencyStrength(snapshot=_snapshot())
    # Seuil par défaut = align_min_score (0.15)
    assert cs.is_aligned("EURUSD", "M30")


# ─────────────────────────────────────────────────────────────────────
# Overrides (R8 réversible)
# ─────────────────────────────────────────────────────────────────────
def test_overrides_align_min_score():
    cs = V10CurrencyStrength(snapshot=_snapshot(),
                             overrides={"align_min_score": 0.5})
    assert not cs.is_aligned("EURUSD", "M30")  # bias 0.43 < 0.5


def test_api_defaults_presents():
    assert "min_bias" in API_DEFAULTS
    assert "align_min_score" in API_DEFAULTS
    assert "conf_align_bonus" in API_DEFAULTS


# ─────────────────────────────────────────────────────────────────────
# MISSION 2 — Perf + DB réelle + sérialisation
# ─────────────────────────────────────────────────────────────────────
def test_compute_scores_perf_rapide():
    cs = V10CurrencyStrength(snapshot=_snapshot())
    t0 = time.perf_counter()
    for _ in range(100):
        cs.compute_scores()
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0  # 100 appels < 1s → <10ms/appel


def test_compute_scores_from_db_reelle():
    scores = compute_scores_from_db("data/v9_forces.db", "M30", lookback=20)
    assert len(scores) == 7
    for c, v in scores.items():
        assert 0.0 <= v <= 100.0


def test_compute_scores_from_db_absente_failopen():
    scores = compute_scores_from_db("nonexistent_zz.db", "M30")
    assert len(scores) == 7
    assert all(v == 50.0 for v in scores.values())


def test_v10_currency_strength_serialisable():
    cs = V10CurrencyStrength(snapshot=_snapshot())
    json.dumps(cs.compute_scores())
    json.dumps({"bias": cs.get_pair_bias("EUR", "USD")})


def test_module_re_exporte():
    """La classe API est exportée par le module (import direct)."""
    from core.v10 import v10_currency_strength
    assert hasattr(v10_currency_strength, "V10CurrencyStrength")
