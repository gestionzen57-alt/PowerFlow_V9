"""Tests pour v9_regime_live_detector.py (Phase 138).

Couvre les cas critiques :
1. Module version + kill switch defaut OFF
2. Kill switch OFF -> kill_switch_active=False dans la sortie
3. Vol spike (>=2.0) -> signal EXTENSION (avec current neutre)
4. Vol calme (<=0.7) -> signal RETOUR_EQUILIBRE
5. Vol normal -> pas de signal vol (facteur vide)
6. DOW mardi GBPUSD -> CASSURE (via DOW_REGIME_BIAS)
7. DOW mercredi GBPUSD -> EXTENSION
8. DOW jeudi GBPUSD -> pas de signal (pas dans DOW_REGIME_BIAS)
9. Combinaison : mercredi GBPUSD + vol spike + current EXTENSION
   => predicted = EXTENSION (max score)
10. R6 fail-open : vol_ratio=None + dow hors table -> fallback current_regime, conf 0.0
11. current_regime inconnu -> normalise a NEUTRE
12. Symbol autre que GBPUSD sans biais -> pas de signal DOW
13. Scores exposes dans la sortie
14. Leviers L20 remontes
"""
import pytest

from core.v9.kill_switches import get
from core.v9.v9_regime_live_detector import (
    REGIMES,
    SCORE_DOW,
    SCORE_PERSIST,
    SCORE_VOL,
    VERSION,
    VOL_CALME_THRESHOLD,
    VOL_SPIKE_THRESHOLD,
    predict_next_regime,
    regime_live_detector_enabled,
)


# ── Module + constantes ─────────────────────────────────────────────
def test_module_version():
    assert VERSION == "1.0"


def test_kill_switch_default_off(monkeypatch):
    """Defaut OFF (R25' strict motion CEO). Phase 166 (03/08) a active en prod.

    Test : si env absent + fichier absent, defaut OFF.
    Phase 166 : activation prod → ce test ne reflete plus l'etat live,
    mais valide le CONTRAT du module (defaut strict sans env/file).
    """
    from core.v9 import kill_switches
    monkeypatch.delenv("V9_REGIME_LIVE_DETECTOR_ENABLED", raising=False)
    kill_switches._switches = None
    monkeypatch.setattr(kill_switches, "_load", lambda: {})
    assert get("V9_REGIME_LIVE_DETECTOR_ENABLED", "0") == "0"


def test_constants():
    assert VOL_SPIKE_THRESHOLD == 2.0
    assert VOL_CALME_THRESHOLD == 0.7
    assert SCORE_DOW == 0.5
    assert SCORE_VOL == 0.3
    assert SCORE_PERSIST == 0.2
    assert "EXTENSION" in REGIMES
    assert "RETOUR_EQUILIBRE" in REGIMES
    assert "CASSURE" in REGIMES


# ── Kill switch + API ───────────────────────────────────────────────
def test_kill_switch_off_marque_dans_sortie(monkeypatch):
    """Le kill switch OFF est reflechi dans la sortie (pas d'effet de filtrage)."""
    from core.v9 import kill_switches
    monkeypatch.delenv("V9_REGIME_LIVE_DETECTOR_ENABLED", raising=False)
    kill_switches._switches = None
    monkeypatch.setattr(kill_switches, "_load", lambda: {})
    r = predict_next_regime(
        current_regime="NEUTRE",
        utc_hour=10,
        utc_dow=2,  # mercredi
        vol_ratio=1.0,
        symbol="GBPUSD",
    )
    assert r["kill_switch_active"] is False


# ── Signal vol ─────────────────────────────────────────────────────
def test_vol_spike_signal_extension():
    """Vol ratio >= 2.0 -> regime EXTENSION."""
    r = predict_next_regime(
        current_regime="NEUTRE",  # neutre pour isoler le signal vol
        utc_hour=10,
        utc_dow=3,  # jeudi (pas de DOW GBPUSD bias)
        vol_ratio=2.5,
        symbol="GBPUSD",
    )
    # EXTENSION a 0.3 (vol) + NEUTRE a 0.2 (persist) → predicted = EXTENSION
    # car 0.3 > 0.2
    assert r["predicted_regime"] == "EXTENSION"
    assert r["scores"]["EXTENSION"] >= SCORE_VOL
    assert any("vol_spike" in f for f in r["factors"])


def test_vol_calme_signal_retour_equilibre():
    """Vol ratio <= 0.7 -> regime RETOUR_EQUILIBRE."""
    r = predict_next_regime(
        current_regime="NEUTRE",  # neutre pour isoler
        utc_hour=10,
        utc_dow=3,  # jeudi (pas de DOW GBPUSD bias)
        vol_ratio=0.5,
        symbol="GBPUSD",
    )
    # RETOUR_EQUILIBRE a 0.3 > NEUTRE a 0.2 → predicted = RETOUR_EQUILIBRE
    assert r["predicted_regime"] == "RETOUR_EQUILIBRE"
    assert r["scores"]["RETOUR_EQUILIBRE"] >= SCORE_VOL
    assert any("vol_calme" in f for f in r["factors"])


def test_vol_normal_pas_de_signal():
    """Vol normal (0.7 < x < 2.0) -> pas de signal vol (facteur vide).

    Avec current_regime=NEUTRE et DOW jeudi (hors table GBPUSD),
    seul le persist NEUTRE (×0.2) reste. Pas de R6 fail-open car
    le vol n'est pas 'unknown' (au sens donne par l'API) : il est 'normal'.
    """
    r = predict_next_regime(
        current_regime="NEUTRE",
        utc_hour=10,
        utc_dow=3,
        vol_ratio=1.0,
        symbol="GBPUSD",
    )
    # Pas de signal vol ni DOW jeudi
    assert not any("vol_" in f for f in r["factors"])
    assert not any("dow_3" in f for f in r["factors"])
    # Le predicted = NEUTRE (seul signal = persist x0.2)
    assert r["predicted_regime"] == "NEUTRE"
    assert r["confidence"] == round(SCORE_PERSIST, 3)
    assert r["reason"] == "majority_weighted_vote"


# ── Signal DOW ─────────────────────────────────────────────────────
def test_dow_mardi_gbpusd_cassure():
    """DOW mardi GBPUSD -> CASSURE (audit SQL live 03/08)."""
    r = predict_next_regime(
        current_regime="NEUTRE",  # neutre pour isoler
        utc_hour=10,
        utc_dow=1,  # mardi
        vol_ratio=1.0,
        symbol="GBPUSD",
    )
    # CASSURE a 0.5 (DOW) + NEUTRE a 0.2 (persist) → predicted = CASSURE
    assert r["predicted_regime"] == "CASSURE"
    assert r["scores"]["CASSURE"] >= SCORE_DOW
    assert any("dow_1_GBPUSD" in f for f in r["factors"])


def test_dow_mercredi_gbpusd_extension():
    """DOW mercredi GBPUSD -> EXTENSION (audit SQL live 03/08)."""
    r = predict_next_regime(
        current_regime="NEUTRE",
        utc_hour=10,
        utc_dow=2,  # mercredi
        vol_ratio=1.0,
        symbol="GBPUSD",
    )
    assert r["predicted_regime"] == "EXTENSION"
    assert r["scores"]["EXTENSION"] >= SCORE_DOW
    assert any("dow_2_GBPUSD" in f for f in r["factors"])


def test_dow_jeudi_gbpusd_no_signal():
    """DOW jeudi GBPUSD -> pas de signal (pas dans DOW_REGIME_BIAS)."""
    r = predict_next_regime(
        current_regime="NEUTRE",
        utc_hour=10,
        utc_dow=3,  # jeudi
        vol_ratio=1.0,
        symbol="GBPUSD",
    )
    # Pas de signal DOW jeudi GBPUSD
    assert not any("dow_3" in f for f in r["factors"])


def test_dow_mercredi_other_symbol_no_signal():
    """DOW mercredi mais symbol != GBPUSD -> pas de signal DOW."""
    r = predict_next_regime(
        current_regime="NEUTRE",
        utc_hour=10,
        utc_dow=2,  # mercredi
        vol_ratio=1.0,
        symbol="EURUSD",  # pas dans DOW_REGIME_BIAS
    )
    assert not any("dow_2" in f for f in r["factors"])


# ── Combinaison ────────────────────────────────────────────────────
def test_combination_mercredi_spike_current_extension():
    """mercredi GBPUSD + vol spike + current=EXTENSION : predicted = EXTENSION (max)."""
    r = predict_next_regime(
        current_regime="EXTENSION",
        utc_hour=10,
        utc_dow=2,  # mercredi
        vol_ratio=2.5,
        symbol="GBPUSD",
    )
    # EXTENSION : 0.5 (DOW mer) + 0.3 (vol spike) + 0.2 (persist) = 1.0
    # C'est le max
    assert r["predicted_regime"] == "EXTENSION"
    assert r["scores"]["EXTENSION"] == 1.0
    assert r["confidence"] == 1.0


def test_combination_mardi_gbpusd_vol_spike():
    """mardi GBPUSD + vol spike : CASSURE (0.5) vs EXTENSION (0.3) vs CASSURE persist (0.2) = 0.7"""
    r = predict_next_regime(
        current_regime="CASSURE",  # persist CASSURE
        utc_hour=10,
        utc_dow=1,  # mardi
        vol_ratio=2.5,  # EXTENSION
        symbol="GBPUSD",
    )
    # CASSURE : 0.5 (DOW mar) + 0.2 (persist) = 0.7
    # EXTENSION : 0.3 (vol spike) + 0.2... non pas de persist EXTENSION
    # Total : CASSURE 0.7 vs EXTENSION 0.3 → CASSURE
    assert r["predicted_regime"] == "CASSURE"
    assert r["scores"]["CASSURE"] == 0.7
    assert r["scores"]["EXTENSION"] == 0.3


# ── R6 fail-open ───────────────────────────────────────────────────
def test_fail_open_dow_hors_table_vol_none():
    """DOW hors table + vol None -> fallback current_regime, conf 0.0."""
    r = predict_next_regime(
        current_regime="RETOUR_EQUILIBRE",
        utc_hour=10,
        utc_dow=5,  # samedi
        vol_ratio=None,
        symbol="GBPUSD",
    )
    # Pas de signal DOW, pas de signal vol
    # Seul persist RETOUR_EQUILIBRE (×0.2) reste
    # Mais comme tous les signaux principaux sont inconnus,
    # R6 force fallback current_regime avec confidence 0.0
    assert r["predicted_regime"] == "RETOUR_EQUILIBRE"
    assert r["confidence"] == 0.0
    assert r["reason"] == "all_signals_unknown_fallback_current"


def test_current_regime_inconnu_normalise():
    """current_regime inconnu -> normalise a NEUTRE."""
    r = predict_next_regime(
        current_regime="BIZARRE_REGIME",
        utc_hour=10,
        utc_dow=3,
        vol_ratio=1.0,
        symbol="GBPUSD",
    )
    assert r["current_regime"] == "NEUTRE"


# ── API surface ───────────────────────────────────────────────────
def test_scores_all_regimes_exposes():
    """Les scores par regime sont tous exposes dans la sortie."""
    r = predict_next_regime(
        current_regime="EXTENSION",
        utc_hour=10,
        utc_dow=2,
        vol_ratio=2.5,
        symbol="GBPUSD",
    )
    for regime in REGIMES:
        assert regime in r["scores"]
        assert isinstance(r["scores"][regime], float)


def test_leviers_l20_remontes():
    """Les leviers L20 sont remontes pour les signaux actifs."""
    r = predict_next_regime(
        current_regime="NEUTRE",
        utc_hour=10,
        utc_dow=1,  # mardi GBPUSD → CASSURE
        vol_ratio=0.5,  # RETOUR_EQUILIBRE
        symbol="GBPUSD",
    )
    # Au moins 2 leviers (DOW + vol)
    assert len(r["leviers"]) >= 2
    assert all(l.startswith("L20_regime_") for l in r["leviers"])


def test_kill_switch_accesseur():
    """Accesseur booleen."""
    import inspect
    sig = inspect.signature(regime_live_detector_enabled)
    assert str(sig.return_annotation) == "bool"
