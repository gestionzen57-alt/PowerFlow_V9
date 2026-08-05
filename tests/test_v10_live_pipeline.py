"""V10 Live Pipeline — tests (Phase 22+ CEO suite).

Cible R7 : 15 tests verts minimum.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v10.v10_live_pipeline import (
    DEFAULT_VSA_BULLISH_THRESHOLD,
    DEFAULT_VSA_BEARISH_THRESHOLD,
    DEFAULT_TF_WEIGHTS,
    DEFAULT_M30_SOLIDARITY_BONUS,
    LivePipelineReport,
    get_vsa_thresholds,
    get_intensity_calibrated,
    run_live_pipeline,
    demo_run_live_pipeline,
)


# ─────────────────────────────────────────────────────────────────────
# CONSTANTS (3)
# ─────────────────────────────────────────────────────────────────────

def test_constants_bullish_default_positive():
    assert DEFAULT_VSA_BULLISH_THRESHOLD > 0


def test_constants_bearish_default_negative():
    assert DEFAULT_VSA_BEARISH_THRESHOLD < 0


def test_constants_bonuses_weights():
    assert DEFAULT_M30_SOLIDARITY_BONUS > 0
    assert DEFAULT_TF_WEIGHTS["H4"] >= DEFAULT_TF_WEIGHTS["H1"]
    assert DEFAULT_TF_WEIGHTS["H1"] >= DEFAULT_TF_WEIGHTS["M30"]


# ─────────────────────────────────────────────────────────────────────
# HELPERS (3)
# ─────────────────────────────────────────────────────────────────────

def test_get_vsa_thresholds_default():
    """use_calibrated=False → defaults."""
    bull, bear = get_vsa_thresholds(use_calibrated=False)
    assert bull == DEFAULT_VSA_BULLISH_THRESHOLD
    assert bear == DEFAULT_VSA_BEARISH_THRESHOLD


def test_get_vsa_thresholds_calibrated_runs():
    """use_calibrated=True → grid search retourne seuils valides."""
    bull, bear = get_vsa_thresholds(
        db_path="data/v9_forces.db",
        use_calibrated=True,
    )
    assert bull > 0
    assert bear < 0


def test_get_intensity_calibrated_optional():
    """get_intensity_calibrated retourne Optional[CalibratedParams]."""
    calib = get_intensity_calibrated(db_path="data/v9_forces.db")
    # Optional : peut être None ou CalibratedParams
    assert calib is None or hasattr(calib, "intensity_to_pips")


# ─────────────────────────────────────────────────────────────────────
# FIXTURE (1)
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


def _populate_mtf(db_path, pair, n=30):
    con = sqlite3.connect(db_path)
    for tf in ("M30", "H1", "H4", "D1"):
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


# ─────────────────────────────────────────────────────────────────────
# RUN LIVE PIPELINE (5)
# ─────────────────────────────────────────────────────────────────────

def test_run_live_pipeline_db_missing():
    """DB inexistante → error dans audit (R6 fail-open)."""
    rep = run_live_pipeline(
        "GBPUSD", "/nonexistent_xyz.db",
        timestamp="2026-08-05T00:00:00Z",
    )
    assert "error" in rep.audit
    assert rep.vsa_signal == "NEUTRAL"


def test_run_live_pipeline_basic(tmp_db):
    """Pipeline live basique retourne LivePipelineReport valide."""
    _populate_mtf(tmp_db, "GBPUSD", n=30)
    rep = run_live_pipeline(
        "GBPUSD", tmp_db,
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,  # évite grid search long
        use_calibrated_intensity=False,
    )
    assert isinstance(rep, LivePipelineReport)
    assert rep.pair == "GBPUSD"
    assert rep.n_snapshots_m30 >= 5
    assert rep.n_snapshots_h1 >= 5
    assert rep.n_snapshots_h4 >= 5


def test_run_live_pipeline_vsa_signal_valid(tmp_db):
    """VSA signal ∈ {BULLISH, BEARISH, NEUTRAL}."""
    _populate_mtf(tmp_db, "GBPUSD", n=30)
    rep = run_live_pipeline(
        "GBPUSD", tmp_db,
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert rep.vsa_signal in ("BULLISH", "BEARISH", "NEUTRAL")


def test_run_live_pipeline_thresholds_source(tmp_db):
    """thresholds_source ∈ {calibrated_v2, default}."""
    _populate_mtf(tmp_db, "GBPUSD", n=30)
    rep = run_live_pipeline(
        "GBPUSD", tmp_db,
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert rep.thresholds_source == "default"
    assert rep.vsa_thresholds == (DEFAULT_VSA_BULLISH_THRESHOLD, DEFAULT_VSA_BEARISH_THRESHOLD)


def test_run_live_pipeline_serializable(tmp_db):
    """Report JSON-sérialisable (R9 audit)."""
    _populate_mtf(tmp_db, "GBPUSD", n=30)
    rep = run_live_pipeline(
        "GBPUSD", tmp_db,
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    j = json.dumps(rep.as_dict())
    assert "vsa_signal" in j
    assert "market_context_tradeable" in j


# ─────────────────────────────────────────────────────────────────────
# DEMO (2)
# ─────────────────────────────────────────────────────────────────────

def test_demo_run_returns_list():
    """demo_run_live_pipeline retourne liste."""
    reps = demo_run_live_pipeline(
        "data/v9_forces.db",
        pairs=("GBPUSD",),
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert isinstance(reps, list)


def test_demo_run_all_have_audit():
    """Chaque report a audit Phase 22+."""
    reps = demo_run_live_pipeline(
        "data/v9_forces.db",
        pairs=("GBPUSD", "USDCHF"),
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    for r in reps:
        assert "method" in r.audit
        assert "phases_integrated" in r.audit
        assert "V10 Live Pipeline" in r.audit["method"]
        assert "Phase 21+" in str(r.audit["phases_integrated"])


# ─────────────────────────────────────────────────────────────────────
# DATACLASS (1)
# ─────────────────────────────────────────────────────────────────────

def test_live_pipeline_report_default_construction():
    """LivePipelineReport() défaut : tous champs initialisés."""
    rep = LivePipelineReport()
    assert rep.timestamp == ""
    assert rep.pair == ""
    assert rep.vsa_signal == "NEUTRAL"
    assert rep.market_context_tradeable is False
    assert rep.market_context_tradeable_pairs == []
    assert rep.intensity_calibrated is False
