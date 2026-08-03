"""Tests pour v9_adaptive_dd_tracker.py (Phase 137).

Couvre les cas critiques :
1. Module version + kill switch defaut OFF
2. Kill switch OFF -> pass-through (halt = False)
3. Vol spike (>=2.0) -> ×1.5
4. Vol calme (<=0.7) -> ×0.7
5. Vol normal -> ×1.0
6. Regime CASSURE -> ×1.2
7. Regime RETOUR_EQUILIBRE -> ×0.8
8. Regime autre -> ×1.0
9. Session asie -> ×0.5
10. Session overlap -> ×1.0
11. Combinaison : spike × CASSURE × asie = ×1.5 × ×1.2 × ×0.5 = ×0.9
12. track_drawdown : halt True si dd_current < threshold
13. track_drawdown : halt False si dd_current > threshold
14. Bornes finales [DD_MIN, 0]
15. R6 fail-open : input invalide -> multiplier 1.0
"""
import os

import pytest

from core.v9.kill_switches import get
from core.v9.v9_adaptive_dd_tracker import (
    DD_THRESHOLD_MAX,
    DD_THRESHOLD_MIN,
    REGIME_CASSURE_MULT,
    REGIME_RETOUR_EQUILIBRE_MULT,
    SESSION_ASIE_MULT,
    SESSION_OVERLAP_MULT,
    VERSION,
    VOL_CALME_MULT,
    VOL_SPIKE_MULT,
    adaptive_dd_tracker_enabled,
    compute_adaptive_dd_threshold,
    track_drawdown,
)


# ── Kill switch isolation ───────────────────────────────────────────
@pytest.fixture
def kill_137_on(monkeypatch):
    monkeypatch.setenv("V9_ADAPTIVE_DD_TRACKER_ENABLED", "1")
    return monkeypatch


# ── Module + constantes ─────────────────────────────────────────────
def test_module_version():
    assert VERSION == "1.0"


def test_kill_switch_default_off():
    """Defaut OFF (R25' strict motion CEO)."""
    assert get("V9_ADAPTIVE_DD_TRACKER_ENABLED", "0") == "0"


def test_constants():
    assert VOL_SPIKE_MULT == 1.5
    assert VOL_CALME_MULT == 0.7
    assert REGIME_CASSURE_MULT == 1.2
    assert REGIME_RETOUR_EQUILIBRE_MULT == 0.8
    assert SESSION_ASIE_MULT == 0.5
    assert SESSION_OVERLAP_MULT == 1.0
    assert DD_THRESHOLD_MIN == -300.0
    assert DD_THRESHOLD_MAX == 0.0


# ── compute_adaptive_dd_threshold ───────────────────────────────────
def test_compute_threshold_vol_spike():
    """Vol ratio >= 2.0 -> vol_mult = 1.5."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=2.5, regime="NEUTRE", session="overlap")
    assert r["vol_mult"] == 1.5
    assert r["dd_threshold"] == -150.0  # -100 * 1.5 * 1.0 * 1.0


def test_compute_threshold_vol_calme():
    """Vol ratio <= 0.7 -> vol_mult = 0.7."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=0.5, regime="NEUTRE", session="overlap")
    assert r["vol_mult"] == 0.7
    assert r["dd_threshold"] == -70.0  # -100 * 0.7 * 1.0 * 1.0


def test_compute_threshold_vol_normal():
    """Vol ratio entre 0.7 et 2.0 -> vol_mult = 1.0."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=1.0, regime="NEUTRE", session="overlap")
    assert r["vol_mult"] == 1.0
    assert r["dd_threshold"] == -100.0


def test_compute_threshold_regime_cassure():
    """Regime CASSURE -> regime_mult = 1.2 (DD seuil elargi)."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=1.0, regime="CASSURE", session="overlap")
    assert r["regime_mult"] == 1.2
    assert r["dd_threshold"] == -120.0


def test_compute_threshold_regime_retour_equilibre():
    """Regime RETOUR_EQUILIBRE -> regime_mult = 0.8 (DD seuil serre)."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=1.0, regime="RETOUR_EQUILIBRE", session="overlap")
    assert r["regime_mult"] == 0.8
    assert r["dd_threshold"] == -80.0


def test_compute_threshold_regime_neutre():
    """Regime autre (NEUTRE/EXTENSION/REJET) -> regime_mult = 1.0."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=1.0, regime="EXTENSION", session="overlap")
    assert r["regime_mult"] == 1.0


def test_compute_threshold_session_asie():
    """Session asie -> session_mult = 0.5 (DD seuil serre, liquidite basse)."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=1.0, regime="NEUTRE", session="asie")
    assert r["session_mult"] == 0.5
    assert r["dd_threshold"] == -50.0  # -100 * 1.0 * 1.0 * 0.5


def test_compute_threshold_session_overlap():
    """Session overlap -> session_mult = 1.0."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=1.0, regime="NEUTRE", session="overlap")
    assert r["session_mult"] == 1.0


def test_compute_threshold_combinaison_spike_cassure_asie():
    """spike × CASSURE × asie = 1.5 × 1.2 × 0.5 = 0.9 (× -100 = -90)."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=2.5, regime="CASSURE", session="asie")
    assert r["vol_mult"] == 1.5
    assert r["regime_mult"] == 1.2
    assert r["session_mult"] == 0.5
    # -100 * 1.5 * 1.2 * 0.5 = -90
    assert r["dd_threshold"] == -90.0


def test_compute_threshold_leviers_combinaison():
    """3 modificateurs actifs => 3 leviers L19 presents."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=2.5, regime="CASSURE", session="asie")
    assert len(r["leviers"]) == 3
    assert all(l.startswith("L19_dd_") for l in r["leviers"])


def test_compute_threshold_fail_open_invalid_input():
    """R6 fail-open : input None/invalide -> multiplier 1.0."""
    r = compute_adaptive_dd_threshold(dd_base=-100.0, vol_ratio=None, regime=None, session=None)
    assert r["vol_mult"] == 1.0
    assert r["regime_mult"] == 1.0
    assert r["session_mult"] == 1.0
    assert r["dd_threshold"] == -100.0


def test_compute_threshold_bornes_min():
    """Borne inferieure : si multiplicateur extreme, threshold clampe a DD_MIN."""
    # asie ×0.5 × CASSURE ×1.2 = ×0.6 → -100*0.6 = -60, OK
    # Si on prend un dd_base tres serre × modificateurs serres, peut-il depasser -300 ?
    # -1000 * 0.5 = -500 → clampe a -300
    r = compute_adaptive_dd_threshold(dd_base=-1000.0, vol_ratio=1.0, regime="NEUTRE", session="asie")
    assert r["dd_threshold"] >= DD_THRESHOLD_MIN
    assert r["dd_threshold"] == -300.0  # clampe


def test_compute_threshold_bornes_max():
    """Borne superieure : threshold <= 0 (DD ne peut pas etre positif)."""
    r = compute_adaptive_dd_threshold(dd_base=100.0, vol_ratio=1.0, regime="NEUTRE", session="overlap")
    # dd_base=100 (positif, ce qui n'a pas de sens mais on clampe)
    assert r["dd_threshold"] <= DD_THRESHOLD_MAX


# ── track_drawdown (verification HALT) ─────────────────────────────
def test_track_drawdown_kill_switch_off_passthrough():
    """Kill switch OFF -> halt toujours False (laisser DD Protector decider)."""
    r = track_drawdown(
        dd_current=-200.0,  # tres grave
        vol_ratio=1.0,
        regime="NEUTRE",
        session="overlap",
        dd_base=-100.0,
    )
    assert r["halt"] is False
    assert r["kill_switch_active"] is False
    assert r["reason"] == "kill_switch_off_pass_through"


def test_track_drawdown_halt_true_kill_on(kill_137_on):
    """dd_current < threshold (en valeur) => HALT True."""
    # vol spike × CASSURE × overlap : threshold = -100 * 1.5 * 1.2 * 1.0 = -180
    r = track_drawdown(
        dd_current=-200.0,  # plus grave que -180
        vol_ratio=2.5,
        regime="CASSURE",
        session="overlap",
        dd_base=-100.0,
    )
    assert r["kill_switch_active"] is True
    assert r["threshold"] == -180.0
    assert r["current"] == -200.0
    assert r["halt"] is True
    assert r["margin"] == -20.0  # -200 - (-180) = -20


def test_track_drawdown_halt_false_margin_positive(kill_137_on):
    """dd_current > threshold (DD moins grave) => HALT False."""
    r = track_drawdown(
        dd_current=-50.0,  # moins grave que -180
        vol_ratio=2.5,
        regime="CASSURE",
        session="overlap",
        dd_base=-100.0,
    )
    assert r["halt"] is False
    assert r["margin"] == 130.0  # -50 - (-180) = 130


def test_track_drawdown_session_derivation(kill_137_on):
    """Si session='auto' ou vide, derive de utc_hour (defaut overlap via defaut)."""
    # session vide + regime/spike → vol spike ×1.5, regime ×1.0, session ×1.0
    r = track_drawdown(
        dd_current=-100.0,
        vol_ratio=2.5,
        regime="NEUTRE",
        session="",
        dd_base=-100.0,
    )
    # session vide → _session_multiplier("") → "unknown" → 1.0
    assert r["threshold"] == -150.0  # -100 * 1.5 * 1.0 * 1.0


def test_track_drawdown_leviers(kill_137_on):
    """Leviers remontes dans track_drawdown depuis threshold_info."""
    r = track_drawdown(
        dd_current=-50.0,
        vol_ratio=2.5,
        regime="CASSURE",
        session="asie",
        dd_base=-100.0,
    )
    # 3 leviers attendus
    assert len(r["leviers"]) == 3
    assert all(l.startswith("L19_dd_") for l in r["leviers"])


def test_kill_switch_accesseur():
    """Accesseur booleen."""
    import inspect
    sig = inspect.signature(adaptive_dd_tracker_enabled)
    assert str(sig.return_annotation) == "bool"
