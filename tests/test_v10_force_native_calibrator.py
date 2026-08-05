"""V10 Force Native Calibrator — tests unitaires (Phase 21+ CEO suite).

Cible R7 : 15 tests verts minimum.

Doctrine V10 :
  R2 additif pur, R6 fail-open, R7, R8 auto-calibration, R9 audit, R10.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v10.v10_force_native_calibrator import (
    INTENSITY_GRID,
    RECROISEMENT_BONUS_GRID,
    REJET_PENALTY_GRID,
    CalibratedParams,
    CalibrationReport,
    _valid_intensity_combo,
    _safe_pearson,
    _grid_combos,
    calibrate_intensity_to_pips,
    _evaluate_combo_on_pair_tf,
    _compute_pnl_native_with_params,
)
from core.v10.v10_force_native import (
    compute_force_native_features,
    INTENSITY_TO_PIPS as DEFAULT_INTENSITY_TO_PIPS,
)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _make_snapshot(bar_time, etat="NEUTRE", intensite="MOYEN", force_base=70.0, force_quote=30.0, close=1.1):
    return {
        "bar_time": bar_time,
        "close": close,
        "force_eur": force_base,
        "force_usd": force_quote,
        "force_gbp": 50.0, "force_jpy": 50.0, "force_cad": 50.0,
        "force_chf": 50.0, "force_aud": 50.0, "force_nzd": 50.0,
        "compression_extension_etat": etat,
        "compression_extension_intensite": intensite,
        "croisement_detecte": 0,
        "croisement_direction": "NEUTRE",
        "recroisement_detecte": 0,
        "rejet_repulsion_detecte": 0,
        "rejet_intensite": 0.0,
    }


def _make_snapshots(n=20, etat="NEUTRE", intensite="MOYEN"):
    return [_make_snapshot(1783111080 + i * 1800, etat=etat, intensite=intensite,
                            close=1.1 + i * 0.001) for i in range(n)]


# ─────────────────────────────────────────────────────────────────────
# TESTS CONSTANTS (4)
# ─────────────────────────────────────────────────────────────────────

def test_constants_intensity_grid_keys():
    """INTENSITY_GRID contient 4 intensités."""
    assert set(INTENSITY_GRID.keys()) == {"FAIBLE", "MOYEN", "FORT", "EXTREME"}


def test_constants_intensity_grid_values_non_empty():
    """Chaque intensité a ≥ 1 valeur candidate."""
    for k, vals in INTENSITY_GRID.items():
        assert len(vals) >= 1, f"{k} empty"
        assert all(v > 0 for v in vals), f"{k} has non-positive"


def test_constants_recroisement_grid_non_negative():
    """Recroisement bonus grid : ≥ 0."""
    assert all(v >= 0 for v in RECROISEMENT_BONUS_GRID)


def test_constants_rejet_grid_non_positive():
    """Rejet penalty grid : ≤ 0."""
    assert all(v <= 0 for v in REJET_PENALTY_GRID)


# ─────────────────────────────────────────────────────────────────────
# TESTS VALIDATION (3)
# ─────────────────────────────────────────────────────────────────────

def test_valid_intensity_combo_ordered():
    """Combo ordonné FAIBLE ≤ MOYEN ≤ FORT ≤ EXTREME → valide."""
    combo = {"FAIBLE": 1.0, "MOYEN": 3.0, "FORT": 5.0, "EXTREME": 8.0}
    assert _valid_intensity_combo(combo) is True


def test_valid_intensity_combo_unordered_faible_moyen():
    """FAIBLE > MOYEN → invalide."""
    combo = {"FAIBLE": 5.0, "MOYEN": 1.0, "FORT": 5.0, "EXTREME": 8.0}
    assert _valid_intensity_combo(combo) is False


def test_valid_intensity_combo_unordered_moyen_fort():
    """MOYEN > FORT → invalide."""
    combo = {"FAIBLE": 1.0, "MOYEN": 8.0, "FORT": 3.0, "EXTREME": 10.0}
    assert _valid_intensity_combo(combo) is False


# ─────────────────────────────────────────────────────────────────────
# TESTS PEARSON (3)
# ─────────────────────────────────────────────────────────────────────

def test_safe_pearson_basic():
    """Corrélation parfaite positive = +1."""
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 6.0, 8.0, 10.0]
    r = _safe_pearson(xs, ys)
    assert abs(r - 1.0) < 0.001


def test_safe_pearson_perfect_negative():
    """Corrélation parfaite négative = -1."""
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [10.0, 8.0, 6.0, 4.0, 2.0]
    r = _safe_pearson(xs, ys)
    assert abs(r - (-1.0)) < 0.001


def test_safe_pearson_constant():
    """xs constant → 0 (pas undefined)."""
    xs = [5.0, 5.0, 5.0, 5.0]
    ys = [1.0, 2.0, 3.0, 4.0]
    r = _safe_pearson(xs, ys)
    assert r == 0.0


# ─────────────────────────────────────────────────────────────────────
# TESTS GRID COMBOS (2)
# ─────────────────────────────────────────────────────────────────────

def test_grid_combos_non_empty():
    """Au moins 1 combo généré."""
    combos = _grid_combos()
    assert len(combos) > 0


def test_grid_combos_all_valid():
    """Tous les combos générés satisfont la contrainte d'ordonnancement."""
    combos = _grid_combos()
    for c in combos:
        assert _valid_intensity_combo(c["intensity_to_pips"])


# ─────────────────────────────────────────────────────────────────────
# TESTS EVALUATE COMBO (3)
# ─────────────────────────────────────────────────────────────────────

def test_evaluate_combo_insufficient_snapshots():
    """< horizon+1 snapshots → None."""
    snaps = _make_snapshots(n=3)
    metrics = _evaluate_combo_on_pair_tf(
        snaps, "EURUSD", "M30",
        intensity_to_pips=DEFAULT_INTENSITY_TO_PIPS,
        recroisement_bonus_pips=2.0,
        rejet_penalty_pips=-1.0,
        horizon=3,
    )
    assert metrics is None


def test_evaluate_combo_basic():
    """20 snapshots COMPRESSION MOYEN → retourne metrics valides."""
    snaps = _make_snapshots(n=20, etat="COMPRESSION", intensite="MOYEN")
    metrics = _evaluate_combo_on_pair_tf(
        snaps, "EURUSD", "M30",
        intensity_to_pips=DEFAULT_INTENSITY_TO_PIPS,
        recroisement_bonus_pips=2.0,
        rejet_penalty_pips=-1.0,
        horizon=3,
    )
    assert metrics is not None
    assert "wr_native" in metrics
    assert "wr_proxy" in metrics
    assert "delta_wr" in metrics
    assert 0.0 <= metrics["wr_native"] <= 1.0
    assert 0.0 <= metrics["wr_proxy"] <= 1.0


def test_evaluate_combo_custom_params_changes_pnl():
    """Params custom → pnl différent (R8 calibration)."""
    snaps = _make_snapshots(n=20, etat="COMPRESSION", intensite="FORT")
    # Conservative
    m_conservative = _evaluate_combo_on_pair_tf(
        snaps, "EURUSD", "M30",
        intensity_to_pips={"FAIBLE": 0.5, "MOYEN": 1.0, "FORT": 1.5, "EXTREME": 2.0},
        recroisement_bonus_pips=0.5,
        rejet_penalty_pips=-0.5,
    )
    # Agressive
    m_aggressive = _evaluate_combo_on_pair_tf(
        snaps, "EURUSD", "M30",
        intensity_to_pips={"FAIBLE": 2.0, "MOYEN": 5.0, "FORT": 7.0, "EXTREME": 12.0},
        recroisement_bonus_pips=4.0,
        rejet_penalty_pips=-3.0,
    )
    # Les pnl natifs moyens doivent différer
    assert m_conservative["avg_pnl_native"] != m_aggressive["avg_pnl_native"]


# ─────────────────────────────────────────────────────────────────────
# TESTS CALIBRATION (3)
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
            close REAL, is_closed_bar INTEGER,
            force_usd REAL, force_gbp REAL, force_eur REAL,
            force_jpy REAL, force_cad REAL, force_chf REAL,
            force_aud REAL, force_nzd REAL,
            compression_extension_etat TEXT,
            compression_extension_intensite TEXT
        )
    """)
    con.commit()
    con.close()
    yield path
    Path(path).unlink(missing_ok=True)


def _populate_mtf(db_path, pair, tf, n=20):
    con = sqlite3.connect(db_path)
    for i in range(n):
        con.execute("""
            INSERT INTO forces_snapshots (
                symbol, timeframe, bar_time, close, is_closed_bar,
                force_usd, force_gbp, force_eur, force_jpy, force_cad,
                force_chf, force_aud, force_nzd,
                compression_extension_etat, compression_extension_intensite
            ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPRESSION', 'MOYEN')
        """, (pair, tf, 1783111080 + i * 1800, 1.1 + i * 0.001,
              30.0, 50.0, 70.0, 50.0, 50.0, 50.0, 50.0, 50.0))
    con.commit()
    con.close()


def test_calibrate_insufficient_data():
    """DB inexistante → report avec error."""
    rep = calibrate_intensity_to_pips(
        "/nonexistent_xyz.db",
        pairs=("GBPUSD",),
        timeframes=("M30",),
        limit=50,
        max_combos=5,
    )
    assert "error" in rep.audit


def test_calibrate_returns_report(tmp_db):
    """Calibration retourne report avec best_params + top_10."""
    _populate_mtf(tmp_db, "GBPUSD", "M30", n=30)
    _populate_mtf(tmp_db, "GBPUSD", "H1", n=30)
    rep = calibrate_intensity_to_pips(
        tmp_db,
        pairs=("GBPUSD",),
        timeframes=("M30", "H1"),
        limit=50,
        max_combos=10,
    )
    assert isinstance(rep, CalibrationReport)
    assert rep.best_params.n_pairs_tf_evaluated >= 1
    assert len(rep.top_10_combos) <= 10


def test_calibrate_serializable(tmp_db):
    """Report JSON-sérialisable (R9 audit)."""
    _populate_mtf(tmp_db, "GBPUSD", "M30", n=30)
    rep = calibrate_intensity_to_pips(
        tmp_db, pairs=("GBPUSD",), timeframes=("M30",),
        limit=50, max_combos=5,
    )
    j = json.dumps(rep.as_dict())
    assert "best_params" in j
    assert "top_10_combos" in j


# ─────────────────────────────────────────────────────────────────────
# TESTS DATACLASSES (2)
# ─────────────────────────────────────────────────────────────────────

def test_calibrated_params_default():
    """CalibratedParams() défaut : champs initialisés."""
    p = CalibratedParams()
    assert p.intensity_to_pips == {}
    assert p.recroisement_bonus_pips == 0.0
    assert p.rejet_penalty_pips == 0.0


def test_calibrated_params_as_dict():
    """as_dict() retourne dict complet."""
    p = CalibratedParams(
        intensity_to_pips={"FAIBLE": 1.0, "MOYEN": 3.0, "FORT": 5.0, "EXTREME": 8.0},
        recroisement_bonus_pips=2.0,
        rejet_penalty_pips=-1.0,
        target_metric_value=0.05,
    )
    d = p.as_dict()
    assert d["target_metric_value"] == 0.05
    assert "FAIBLE" in d["intensity_to_pips"]
