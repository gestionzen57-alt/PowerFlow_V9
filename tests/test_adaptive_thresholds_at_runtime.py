"""Tests — adaptive_thresholds_at_runtime (V9 P3 autopilot, 2026-07-13).

Couvre :
- adaptive_multiplier_for_vol_regime() retourne multiplicateur correct
  pour chaque (vol_regime, news_phase, timeframe) combinaison.
- Bornes de sécurité [0.5, 2.0] respectées.
- Fallback conservateur sur 1.0 pour état non-mappé.
- get_effective_thresholds() multiplie les baseline correctement.
- Composition multiplicative vs additive.
- Calibration empirique P3 = pure fonction sans side effect.

Régression couverte : 1132 verts doivent rester intacts (test isole).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9.adaptive_thresholds_at_runtime import (
    BASELINE_THRESHOLDS,
    MAX_MULTIPLIER,
    MIN_MULTIPLIER,
    NEWS_MULTIPLIER,
    SESSION_MULTIPLIER,
    TIMEFRAME_MULTIPLIER,
    VOL_MULTIPLIER,
    adaptive_multiplier_for_vol_regime,
    get_effective_thresholds,
)


# ── Constantes et sanity checks ────────────────────────────────────────


def test_baseline_aligned_with_config():
    """Les seuils baseline matchent core/v9/config.py (COALITION 5.38,
    ANTAGONISM 31.39, PLIURE 1.7). Toute régression ici = soit config
    drift, soit baseline_at_runtime pas resynced."""
    assert BASELINE_THRESHOLDS["COALITION"] == pytest.approx(5.38, abs=0.01)
    assert BASELINE_THRESHOLDS["ANTAGONISM"] == pytest.approx(31.39, abs=0.01)
    assert BASELINE_THRESHOLDS["PLIURE"] == pytest.approx(1.7, abs=0.01)


def test_vol_multiplier_table_complete():
    """Les 4 régimes de vol sont couverts."""
    assert set(VOL_MULTIPLIER.keys()) == {"LOW", "NORMAL", "HIGH", "EXTREME"}


def test_news_multiplier_table_complete():
    """Les 5 phases news sont couvertes."""
    assert set(NEWS_MULTIPLIER.keys()) == {
        "NORMAL", "POST_NEWS", "PRE_NEWS", "NEWS_SHOCK", "UNKNOWN",
    }


def test_timeframe_multiplier_table_complete():
    """Les 6 TF principaux sont couverts."""
    assert set(TIMEFRAME_MULTIPLIER.keys()) == {"M1", "M5", "M15", "H1", "H4", "D1"}


# ── DIVERSIFY 2026-07-16 — Gap 3 : session modulateur ──────────────────


def test_session_multiplier_table_complete():
    """Les 6 sessions (vocabulaire session_map) sont couvertes."""
    assert set(SESSION_MULTIPLIER.keys()) == {
        "asie", "sydney", "london", "new_york", "overlap", "inconnu",
    }


@pytest.mark.parametrize("session,expected", [
    ("asie", 0.8),
    ("sydney", 0.8),
    ("london", 1.2),
    ("new_york", 1.0),
    ("overlap", 1.3),
    ("inconnu", 1.0),
])
def test_multiplier_session_alone(session, expected):
    """Chaque session module le multiplicateur (vol=NORMAL, news=UNKNOWN)."""
    mult = adaptive_multiplier_for_vol_regime("NORMAL", session=session)
    assert mult == pytest.approx(expected, abs=0.001)


def test_multiplier_session_none_is_neutral():
    """session=None (défaut) → aucun effet (× 1.0)."""
    assert adaptive_multiplier_for_vol_regime("NORMAL", session=None) == pytest.approx(1.0)


def test_multiplier_session_unknown_fallback_1():
    """Session non-mappée → fallback conservateur × 1.0 (R6)."""
    assert adaptive_multiplier_for_vol_regime(
        "NORMAL", session="MYSTERY_SESSION"
    ) == pytest.approx(1.0)


def test_session_composes_with_vol():
    """Le multiplicateur session se compose multiplicativement avec la vol.
    HIGH (1.3) × overlap (1.3) = 1.69, borné [0.5, 2.0]."""
    mult = adaptive_multiplier_for_vol_regime("HIGH", session="overlap")
    assert mult == pytest.approx(1.3 * 1.3, abs=0.001)


def test_get_effective_thresholds_session_tightens():
    """En overlap (× 1.3), les seuils sont plus exigeants qu'en Asie (× 0.8)."""
    asie = get_effective_thresholds("NORMAL", session="asie")
    overlap = get_effective_thresholds("NORMAL", session="overlap")
    assert overlap["COALITION"] > asie["COALITION"]
    assert asie["COALITION"] == pytest.approx(BASELINE_THRESHOLDS["COALITION"] * 0.8, abs=0.01)


def test_bounds_defined():
    """MIN_MULTIPLIER et MAX_MULTIPLIER sont dans (0, 10] raisonnable."""
    assert 0.0 < MIN_MULTIPLIER <= 1.0
    assert 1.0 <= MAX_MULTIPLIER <= 5.0


# ── adaptive_multiplier_for_vol_regime ─────────────────────────────────


@pytest.mark.parametrize("vol_regime", ["LOW", "NORMAL", "HIGH", "EXTREME"])
def test_multiplier_vol_alone(vol_regime):
    """Multiplier par vol regime seul = valeur calibrée, bornée."""
    mult = adaptive_multiplier_for_vol_regime(vol_regime)
    assert mult == pytest.approx(VOL_MULTIPLIER[vol_regime], abs=0.01)
    assert MIN_MULTIPLIER <= mult <= MAX_MULTIPLIER


def test_multiplier_unknown_vol_fallback_1():
    """Un vol_regime inconnu (pas dans la table) → fallback × 1.0."""
    mult = adaptive_multiplier_for_vol_regime("UNKNOWN_FUTURE_REGIME")
    assert mult == pytest.approx(1.0, abs=0.01)


def test_multiplier_unknown_news_fallback_1():
    """Un news_phase inconnu → fallback × 1.0 (cumulé avec vol baseline)."""
    mult = adaptive_multiplier_for_vol_regime("NORMAL", news_phase="MYSTERY")
    assert mult == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("tf", ["M1", "M5", "M15", "H1", "H4", "D1"])
def test_multiplier_timeframe_alone(tf):
    """Multiplier timeframe seul, vol NORMAL × news UNKNOWN = tf_mult."""
    mult = adaptive_multiplier_for_vol_regime("NORMAL", news_phase="UNKNOWN", timeframe=tf)
    assert mult == pytest.approx(TIMEFRAME_MULTIPLIER[tf], abs=0.01)


@pytest.mark.parametrize("vol", ["LOW", "NORMAL", "HIGH", "EXTREME"])
@pytest.mark.parametrize("news", ["NORMAL", "POST_NEWS", "PRE_NEWS", "NEWS_SHOCK", "UNKNOWN"])
def test_multiplier_combined(vol, news):
    """Combinaison vol×news (sans TF, qui = 1.0)."""
    mult = adaptive_multiplier_for_vol_regime(vol, news_phase=news)
    expected = VOL_MULTIPLIER[vol] * NEWS_MULTIPLIER[news]
    expected_bounded = max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, expected))
    assert mult == pytest.approx(expected_bounded, abs=0.01)


def test_multiplier_extreme_double_high():
    """EXTREME × NEWS_SHOCK = 1.5 * 1.5 = 2.25 → borné MAX_MULTIPLIER = 2.0."""
    mult = adaptive_multiplier_for_vol_regime("EXTREME", news_phase="NEWS_SHOCK")
    assert mult == pytest.approx(MAX_MULTIPLIER, abs=0.01)


def test_multiplier_low_post_news_undershoot():
    """LOW × POST_NEWS = 1.0 * 0.9 = 0.9 — dans les bornes, pas borné."""
    mult = adaptive_multiplier_for_vol_regime("LOW", news_phase="POST_NEWS")
    assert mult == pytest.approx(0.9, abs=0.01)


def test_multiplier_extreme_m1_overshoot():
    """EXTREME × NEWS_SHOCK × M1 = 1.5*1.5*1.5 = 3.375 → borné MAX = 2.0."""
    mult = adaptive_multiplier_for_vol_regime("EXTREME", news_phase="NEWS_SHOCK", timeframe="M1")
    assert mult == pytest.approx(MAX_MULTIPLIER, abs=0.01)


# ── get_effective_thresholds ──────────────────────────────────────────


def test_thresholds_default_baseline():
    """Sans override → seuils × 1.0 = baseline (vol NORMAL/UNKNOWN/notf)."""
    eff = get_effective_thresholds()
    for name, base in BASELINE_THRESHOLDS.items():
        assert eff[name] == pytest.approx(base, abs=0.01)


def test_thresholds_extreme_double_high():
    """EXTREME × NEWS_SHOCK = ×2.0 (MAX borne). Seuils ×2."""
    eff = get_effective_thresholds("EXTREME", news_phase="NEWS_SHOCK")
    for name, base in BASELINE_THRESHOLDS.items():
        expected = round(base * 2.0, 2)
        assert eff[name] == pytest.approx(expected, abs=0.01)


def test_thresholds_low_post_news_slightly_tighter():
    """LOW × POST_NEWS = × 0.9. Seuils resserrés."""
    eff = get_effective_thresholds("LOW", news_phase="POST_NEWS")
    for name, base in BASELINE_THRESHOLDS.items():
        expected = round(base * 0.9, 2)
        assert eff[name] == pytest.approx(expected, abs=0.01)


def test_thresholds_with_tf_override():
    """HIGH × M5 × UNKNOWN = 1.3 * 1.2 = 1.56."""
    eff = get_effective_thresholds("HIGH", news_phase="UNKNOWN", timeframe="M5")
    mult = 1.3 * 1.2  # = 1.56
    for name, base in BASELINE_THRESHOLDS.items():
        expected = round(base * mult, 2)
        assert eff[name] == pytest.approx(expected, abs=0.01)


def test_thresholds_custom_baseline_override():
    """Permet de passer un baseline custom (test futur-proofing)."""
    custom = {"COALITION": 10.0, "ANTAGONISM": 50.0, "PLIURE": 3.0}
    eff = get_effective_thresholds("NORMAL", baseline=custom)
    assert eff["COALITION"] == pytest.approx(10.0, abs=0.01)
    assert eff["ANTAGONISM"] == pytest.approx(50.0, abs=0.01)
    assert eff["PLIURE"] == pytest.approx(3.0, abs=0.01)


def test_thresholds_pure_no_side_effect():
    """Multiples appels successifs de get_effective_thresholds ne mutent
    pas les constantes (no side effect)."""
    eff1 = get_effective_thresholds("EXTREME", news_phase="NEWS_SHOCK")
    eff2 = get_effective_thresholds("LOW", news_phase="POST_NEWS")
    eff3 = get_effective_thresholds("EXTREME", news_phase="NEWS_SHOCK")
    # eff1 et eff3 identiques (fonction pure)
    assert eff1 == eff3
    # eff2 différent (LOW donne baseline)
    assert eff1 != eff2
    # BASELINE_THRESHOLDS inchangé
    assert BASELINE_THRESHOLDS["COALITION"] == pytest.approx(5.38, abs=0.01)


# ── Idempotence / pas de fuite ─────────────────────────────────────


def test_module_import_no_side_effect():
    """Importer le module ne change pas l'état global."""
    # Importer une seconde fois ne doit pas changer le comportement
    from core.v9 import adaptive_thresholds_at_runtime as m2
    assert m2.BASELINE_THRESHOLDS is BASELINE_THRESHOLDS or (
        m2.BASELINE_THRESHOLDS["COALITION"] == BASELINE_THRESHOLDS["COALITION"]
    )
    assert adaptive_multiplier_for_vol_regime("NORMAL") == pytest.approx(1.0)
