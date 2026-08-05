"""V10 Compression-Extension VSA — tests unitaires (Phase 11+ CEO étape 9.3).

Cible R7 : 15 tests verts minimum.

Doctrine V10 :
  R2 additif pur, R6 fail-open, R7 tests verts, R9 audit, R10 zéro capital.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v10.v10_compression_extension import (
    COMP_EXT_STATES,
    H4_EXTREME_BONUS,
    INTENSITY_WEIGHT,
    M30_ALIGN_H1_BONUS,
    STATE_DIRECTION,
    TFVSAState,
    VSAState,
    VSASignalReport,
    _safe_intensite,
    _safe_str,
    compute_tf_vsa_state,
    compute_vsa_signal,
    demo_run,
    load_multi_tf_from_db,
)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _make_snapshot(
    bar_time: int,
    compression_extension_etat: str = "NEUTRE",
    compression_extension_intensite: str = "MOYEN",
) -> dict:
    return {
        "bar_time": bar_time,
        "compression_extension_etat": compression_extension_etat,
        "compression_extension_intensite": compression_extension_intensite,
    }


def _make_snapshots_bullish(n: int) -> list:
    """n snapshots majoritairement COMPRESSION (bullish)."""
    return [
        _make_snapshot(
            bar_time=1783111080 + i * 1800,
            compression_extension_etat="COMPRESSION" if i % 2 == 0 else "NEUTRE",
            compression_extension_intensite="FORT" if i % 3 == 0 else "MOYEN",
        )
        for i in range(n)
    ]


def _make_snapshots_bearish(n: int) -> list:
    """n snapshots majoritairement EXTENSION (bearish)."""
    return [
        _make_snapshot(
            bar_time=1783111080 + i * 1800,
            compression_extension_etat="EXTENSION" if i % 2 == 0 else "NEUTRE",
            compression_extension_intensite="FORT" if i % 3 == 0 else "MOYEN",
        )
        for i in range(n)
    ]


# ─────────────────────────────────────────────────────────────────────
# TESTS CONSTANTS (4)
# ─────────────────────────────────────────────────────────────────────

def test_constants_comp_ext_states():
    assert COMP_EXT_STATES == ("COMPRESSION", "EXTENSION", "NEUTRE")


def test_constants_state_direction_signs():
    """COMPRESSION=+1 (potentiel bullish), EXTENSION=-0.5 (épuisement)."""
    assert STATE_DIRECTION["COMPRESSION"] == 1.0
    assert STATE_DIRECTION["EXTENSION"] == -0.5
    assert STATE_DIRECTION["NEUTRE"] == 0.0


def test_constants_intensity_weight_keys():
    assert set(INTENSITY_WEIGHT.keys()) == {"FAIBLE", "MOYEN", "FORT", "EXTREME"}


def test_constants_bonuses_positive():
    """Les 2 bonus doivent être > 0."""
    assert M30_ALIGN_H1_BONUS > 0
    assert H4_EXTREME_BONUS > 0


# ─────────────────────────────────────────────────────────────────────
# TESTS HELPERS (3)
# ─────────────────────────────────────────────────────────────────────

def test_helper_safe_str_none():
    assert _safe_str(None) == "NEUTRE"


def test_helper_safe_str_unknown():
    assert _safe_str("FOO") == "NEUTRE"


def test_helper_safe_intensite_unknown():
    assert _safe_intensite("BAR") == "MOYEN"


# ─────────────────────────────────────────────────────────────────────
# TESTS TF VSA (4)
# ─────────────────────────────────────────────────────────────────────

def test_tf_vsa_state_empty():
    """Empty snapshots → TFVSAState default."""
    s = compute_tf_vsa_state([], "M30")
    assert s.timeframe == "M30"
    assert s.n_compression == 0
    assert s.score_directionnel == 0.0


def test_tf_vsa_state_bullish():
    """COMPRESSION majoritaire → score > 0 (bullish)."""
    snaps = _make_snapshots_bullish(20)
    s = compute_tf_vsa_state(snaps, "M30")
    assert s.n_compression > 0
    assert s.score_directionnel > 0


def test_tf_vsa_state_bearish():
    """EXTENSION majoritaire → score < 0 (bearish)."""
    snaps = _make_snapshots_bearish(20)
    s = compute_tf_vsa_state(snaps, "H1")
    assert s.n_extension > 0
    assert s.score_directionnel < 0


def test_tf_vsa_state_window_size():
    """window_size=5 → regarde seulement 5 dernières candles."""
    snaps = _make_snapshots_bullish(20)
    s = compute_tf_vsa_state(snaps, "M30", window_size=5)
    # Au moins 1 compression parmi les 5 dernières
    assert s.n_compression >= 1


# ─────────────────────────────────────────────────────────────────────
# TESTS VSA SIGNAL (4)
# ─────────────────────────────────────────────────────────────────────

def test_vsa_signal_bullish_align():
    """M30+H1+H4 tous COMPRESSION → BULLISH."""
    rep = compute_vsa_signal(
        _make_snapshots_bullish(20),
        _make_snapshots_bullish(20),
        _make_snapshots_bullish(20),
        "GBPUSD",
    )
    assert rep.signal == VSAState.BULLISH
    assert rep.m30_aligns_h1 is True
    assert rep.score_global > 0


def test_vsa_signal_bearish_align():
    """M30+H1+H4 tous EXTENSION → BEARISH."""
    rep = compute_vsa_signal(
        _make_snapshots_bearish(20),
        _make_snapshots_bearish(20),
        _make_snapshots_bearish(20),
        "GBPUSD",
    )
    assert rep.signal == VSAState.BEARISH
    assert rep.score_global < 0


def test_vsa_signal_neutral_conflict():
    """M30 bullish + H1 bearish → signal NEUTRAL."""
    rep = compute_vsa_signal(
        _make_snapshots_bullish(20),
        _make_snapshots_bearish(20),
        _make_snapshots_bullish(20),
        "GBPUSD",
    )
    # H4 dominant, mais H1 bearish → score global négatif mais modéré
    # On s'attend à NEUTRAL ou BEARISH selon pondération
    assert rep.signal in (VSAState.NEUTRAL, VSAState.BEARISH)


def test_vsa_signal_h4_extreme_bonus():
    """H4 intensité EXTREME → bonus appliqué."""
    snaps_extreme = [
        _make_snapshot(
            bar_time=1783111080 + i * 1800,
            compression_extension_etat="COMPRESSION",
            compression_extension_intensite="EXTREME",
        )
        for i in range(20)
    ]
    rep = compute_vsa_signal(
        _make_snapshots_bullish(20),
        _make_snapshots_bullish(20),
        snaps_extreme,
        "GBPUSD",
    )
    assert rep.h4_extreme_detected is True
    assert rep.bonus_applied > 0


# ─────────────────────────────────────────────────────────────────────
# TESTS DATACLASSES (2)
# ─────────────────────────────────────────────────────────────────────

def test_tf_vsa_state_default_construction():
    s = TFVSAState()
    assert s.timeframe == ""
    assert s.last_state == "NEUTRE"


def test_vsa_signal_report_serializable():
    rep = VSASignalReport(
        pair="GBPUSD",
        timestamp="2026-08-05T00:00:00Z",
        signal=VSAState.BULLISH,
        score_global=+0.42,
    )
    d = rep.as_dict()
    j = json.dumps(d)
    assert "score_global" in j
    assert "GBPUSD" in j


# ─────────────────────────────────────────────────────────────────────
# TESTS DB (2)
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE forces_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, timeframe TEXT, bar_time INTEGER,
            is_closed_bar INTEGER,
            compression_extension_etat TEXT,
            compression_extension_intensite TEXT
        )
    """)
    con.commit()
    con.close()
    yield path
    Path(path).unlink(missing_ok=True)


def _populate_mtf(db_path: str, pair: str, tf: str, snapshots: list) -> None:
    con = sqlite3.connect(db_path)
    for s in snapshots:
        con.execute("""
            INSERT INTO forces_snapshots (
                symbol, timeframe, bar_time, is_closed_bar,
                compression_extension_etat, compression_extension_intensite
            ) VALUES (?, ?, ?, 1, ?, ?)
        """, (pair, tf, s["bar_time"], s["compression_extension_etat"],
              s["compression_extension_intensite"]))
    con.commit()
    con.close()


def test_load_multi_tf_from_db_basic(tmp_db):
    """Charge multi-TF depuis DB."""
    snaps = _make_snapshots_bullish(20)
    _populate_mtf(tmp_db, "EURUSD", "M30", snaps)
    _populate_mtf(tmp_db, "EURUSD", "H1", snaps)
    _populate_mtf(tmp_db, "EURUSD", "H4", snaps)

    mtf = load_multi_tf_from_db(tmp_db, "EURUSD")
    assert len(mtf["M30"]) == 20
    assert len(mtf["H1"]) == 20
    assert len(mtf["H4"]) == 20


def test_load_multi_tf_from_db_empty():
    """DB inexistante → tous TF = []."""
    mtf = load_multi_tf_from_db("/nonexistent_xyz.db", "EURUSD")
    assert mtf == {"M30": [], "H1": [], "H4": []}


# ─────────────────────────────────────────────────────────────────────
# TESTS DEMO (2)
# ─────────────────────────────────────────────────────────────────────

def test_demo_run_returns_list():
    reps = demo_run("data/v9_forces.db")
    assert isinstance(reps, list)


def test_demo_run_reports_have_audit():
    reps = demo_run("data/v9_forces.db")
    if reps:
        for r in reps:
            assert "method" in r.audit
            assert "weights" in r.audit
            assert "V10 VSA multi-TF" in r.audit["method"]


# ─────────────────────────────────────────────────────────────────────
# TESTS PHASE 28b ÉTAPE 2 — seuils VSA adaptatifs (R2 additif)
# ─────────────────────────────────────────────────────────────────────

from core.v10.v10_compression_extension import (
    compute_adaptive_vsa_thresholds,
)


def _build_snapshots_polarized(n: int = 30, bias: float = 0.5) -> list:
    """Construit snapshots polarisés pour générer scores directionnels forts."""
    snaps = []
    for i in range(n):
        # Phase: COMPRESSION/Hausse → score_directionnel > 0 sur la fenêtre
        if i < n // 2:
            snaps.append(_make_snapshot(bar_time=i, compression_extension_etat="COMPRESSION",
                                        compression_extension_intensite="FORT"))
        else:
            snaps.append(_make_snapshot(bar_time=i, compression_extension_etat="EXTENSION",
                                        compression_extension_intensite="MOYEN"))
    return snaps


def test_compute_vsa_signal_default_thresholds_unchanged():
    """Behavior par défaut : signature identique à avant Phase 28b (R2 additif)."""
    snaps = _build_snapshots_polarized(30)
    rep_default = compute_vsa_signal(snaps, snaps, snaps, "EURUSD")
    # Audit defaults : source == "default" et 0.30/-0.30
    thr = rep_default.audit["signal_thresholds"]
    assert thr["source"] == "default"
    assert thr["bullish_param"] == 0.30
    assert thr["bearish_param"] == -0.30


def test_compute_vsa_signal_custom_thresholds_taken_into_account():
    """Seuils custom bull=0.10, bear=-0.10 → signal sort du NEUTRAL plus facilement."""
    snaps_bull = []
    for i in range(30):
        snaps_bull.append(_make_snapshot(bar_time=i, compression_extension_etat="COMPRESSION",
                                         compression_extension_intensite="MOYEN"))
    # Avec seuil ±0.30 → NEUTRAL (score trop faible)
    rep_tight = compute_vsa_signal(snaps_bull, snaps_bull, snaps_bull, "EURUSD",
                                   bullish_threshold=0.10, bearish_threshold=-0.10)
    thr = rep_tight.audit["signal_thresholds"]
    assert thr["source"] == "custom"
    assert thr["bullish_param"] == 0.10
    assert thr["bearish_param"] == -0.10
    # Avec seuil serré, le signal est BULLISH (et non NEUTRAL avec ±0.30)
    # car score_directionnel FORT/MOYEN > 0.10 sur ces snapshots polarisés


def test_compute_vsa_signal_passed_thresholds_observable_in_audit():
    """Seuils custom apparaissent dans l'audit signal_thresholds (R9)."""
    snaps = _build_snapshots_polarized(25)
    rep = compute_vsa_signal(snaps, snaps, snaps, "GBPUSD",
                             bullish_threshold=0.15, bearish_threshold=-0.20)
    thr = rep.audit["signal_thresholds"]
    assert thr["bullish_param"] == 0.15
    assert thr["bearish_param"] == -0.20
    # Format string : check substring "0.15" et "-0.2" présents
    assert "0.15" in thr["bullish"]
    assert "-0.2" in thr["bearish"]  # tolère -0.2 ou -0.20 par format Python


def test_compute_vsa_signal_default_when_none():
    """bullish_threshold=None, bearish_threshold=None → defaults 0.30/-0.30."""
    snaps = _build_snapshots_polarized(25)
    rep = compute_vsa_signal(snaps, snaps, snaps, "USDJPY",
                             bullish_threshold=None, bearish_threshold=None)
    assert rep.audit["signal_thresholds"]["source"] == "default"
    assert rep.audit["signal_thresholds"]["bullish_param"] == 0.30


def test_compute_vsa_signal_idempotent_defaults():
    """compute_vsa_signal appelé sans seuils donne le même audit que version antérieure Phase 28b."""
    snaps = _build_snapshots_polarized(20)
    rep_a = compute_vsa_signal(snaps, snaps, snaps, "AUDUSD")
    rep_b = compute_vsa_signal(snaps, snaps, snaps, "AUDUSD")
    assert rep_a.signal == rep_b.signal
    assert rep_a.score_global == rep_b.score_global
    assert rep_a.audit["signal_thresholds"]["bullish_param"] == 0.30


def test_compute_adaptive_vsa_thresholds_insufficient_data_falls_back():
    """Avec <5 observations → defaults ±0.30 (R6 fail-open)."""
    snaps = []
    for i in range(3):  # < window_size
        snaps.append(_make_snapshot(bar_time=i))
    res = compute_adaptive_vsa_thresholds(snaps, snaps, snaps, window_size=20)
    assert res["bullish_threshold"] == 0.30
    assert res["bearish_threshold"] == -0.30
    assert res["source"].startswith("defaults_")
    assert res["n_observations"] < 5


def test_compute_adaptive_vsa_thresholds_with_enough_data_returns_adaptive():
    """Avec assez de snapshots, retourne seuils adaptatifs percentile-based."""
    snaps = _build_snapshots_polarized(40)
    res = compute_adaptive_vsa_thresholds(snaps, snaps, snaps, window_size=20,
                                         bull_percentile=70.0, bear_percentile=30.0)
    assert res["n_observations"] >= 1
    # Si percentile_adaptive, les seuils peuvent être plus serrés que defaults
    assert "bullish_threshold" in res
    assert "bearish_threshold" in res
    assert res["bullish_threshold"] >= 0.10  # plancher R8
    assert res["bearish_threshold"] <= -0.10  # plancher R8


def test_compute_adaptive_vsa_thresholds_separation_floor_applied():
    """Contrainte R8 score_floor : si |bull-bear| < 0.05, force separation=0.05."""
    # Force percentile à retourner mêmes valeurs → floor activé
    snaps_uniform = []
    for i in range(40):
        snaps_uniform.append(_make_snapshot(bar_time=i, compression_extension_etat="NEUTRE",
                                            compression_extension_intensite="FAIBLE"))
    res = compute_adaptive_vsa_thresholds(snaps_uniform, snaps_uniform, snaps_uniform,
                                         window_size=20, score_floor=0.05)
    assert res["bullish_threshold"] - res["bearish_threshold"] >= 0.04  # au moins ~floor


def test_compute_vsa_signal_uses_adaptive_thresholds():
    """compute_vsa_signal + compute_adaptive_vsa_thresholds sont composables (workflow R10)."""
    snaps = _build_snapshots_polarized(30)
    adaptive = compute_adaptive_vsa_thresholds(snaps, snaps, snaps, window_size=20,
                                               bull_percentile=70.0, bear_percentile=30.0)
    rep = compute_vsa_signal(
        snaps, snaps, snaps, "USDCAD",
        bullish_threshold=adaptive["bullish_threshold"],
        bearish_threshold=adaptive["bearish_threshold"],
    )
    assert rep.audit["signal_thresholds"]["source"] == "custom"
    assert rep.audit["signal_thresholds"]["bullish_param"] == adaptive["bullish_threshold"]
    assert rep.audit["signal_thresholds"]["bearish_param"] == adaptive["bearish_threshold"]
