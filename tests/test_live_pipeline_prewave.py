"""tests/test_live_pipeline_prewave.py — H-NEXT.

Vérifie l'intégration du détecteur de pré-vague Fatman (H7) dans le
pipeline live (v10_live_pipeline.run_live_pipeline) :

  - COMPRESSION  → signal_score *= 1.15 (boost)
  - DIVERGENCE   → mode WATCH_ONLY (skip trade)
  - NEUTRAL      → aucun changement (multiplicateur 1.0, pas de watch_only)
  - fail-open R6 : historique sigma absent → NEUTRAL, pipeline intact

Doctrine : R2 additif pur, R6 fail-open, R9 audit, R10 compute only.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.v10.v10_fatman_wave_predictor import (
    PreWaveAlert,
    detect_pre_wave,
)
from core.v10.v10_live_pipeline import (
    LivePipelineReport,
    run_live_pipeline,
)

# ─────────────────────────────────────────────────────────────────────
# FIXTURE — DB forces_snapshots minimal (sigma calculable via forces)
# ─────────────────────────────────────────────────────────────────────

def _make_db(h1_force_series, n=30):
    """Crée une DB forces_snapshots avec n barres par TF.

    h1_force_series : liste chronologique de tuples de 8 forces (usd, gbp, eur,
                      jpy, cad, chf, aud, nzd) appliqués aux DERNIÈRES barres H1.
                      → contrôle sigma[-1] (dernière barre) et la pente sigma
                        (décroissance sur les 4 dernières barres).
    """
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
    base_bar = 1783111080  # epoch de départ

    # Forces "compression" : toutes les 8 devises proches → sigma très bas
    comp = (50.0, 50.5, 50.2, 49.8, 50.1, 50.0, 49.9, 50.3)

    for tf in ("M30", "H1", "H4", "D1"):
        step = 1800 if tf == "M30" else 3600 if tf == "H1" else 14400 if tf == "H4" else 86400
        for i in range(n):
            forces = comp
            # Dernières barres H1 → forces spécifiques au cas (série sigma contrôlée)
            if tf == "H1":
                offset_from_end = n - 1 - i  # 0 = dernière barre
                if offset_from_end < len(h1_force_series):
                    forces = h1_force_series[len(h1_force_series) - 1 - offset_from_end]
            con.execute("""
                INSERT INTO forces_snapshots (
                    symbol, timeframe, bar_time, close, is_closed_bar,
                    force_usd, force_gbp, force_eur, force_jpy, force_cad,
                    force_chf, force_aud, force_nzd,
                    compression_extension_etat, compression_extension_intensite
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPRESSION', 'MOYEN')
            """, ("EURUSD", tf, base_bar + i * step, 1.1 + i * 0.001, *forces))
    con.commit()
    con.close()
    return path


@pytest.fixture
def tmp_db():
    paths = []
    def _create(h1_force_series):
        p = _make_db(h1_force_series)
        paths.append(p)
        return p
    yield _create
    for p in paths:
        Path(p).unlink(missing_ok=True)


# Séries H1 chronologiques (4 dernières barres) contrôlant sigma.
#   DIVERGENCE : dernière barre sigma > 28 → watch_only.
#   COMPRESSION : série décroissante, dernière barre sigma ∈ [12,20], pente < -0.3.
#   NEUTRAL : dernière barre sigma dans plage mais pente plate.
_DIVERGENT_SERIES = [
    (50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0),  # sigma ~0
    (50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0),
    (50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0),
    (90.0, 10.0, 85.0, 15.0, 80.0, 20.0, 75.0, 25.0),  # sigma 33 → DIVERGENCE
]
# 4 barres H1 à sigma décroissant : 25 → 23 → 20 → 18 (dernière ∈ [12,20], pente < -0.3)
_COMPRESS_SERIES = [
    (75.0, 25.0, 75.0, 25.0, 75.0, 25.0, 75.0, 25.0),  # sigma ~25
    (73.0, 27.0, 73.0, 27.0, 73.0, 27.0, 73.0, 27.0),  # sigma ~23
    (70.0, 30.0, 70.0, 30.0, 70.0, 30.0, 70.0, 30.0),  # sigma ~20
    (68.0, 32.0, 68.0, 32.0, 68.0, 32.0, 68.0, 32.0),  # sigma ~18 → COMPRESSION
]


# ─────────────────────────────────────────────────────────────────────
# UNIT — detect_pre_wave (H7) contrat attendu par le pipeline
# ─────────────────────────────────────────────────────────────────────

def test_predictor_compression_phase():
    """Compression : sigma dans [12,20] + pente négative → COMPRESSION."""
    hist = [20.0, 18.5, 17.0, 15.5, 14.0]
    a = detect_pre_wave(hist)
    assert a.phase == "COMPRESSION"
    assert a.pre_wave is True


def test_predictor_divergence_phase():
    """Divergence : sigma > 28 → DIVERGENCE."""
    hist = [25.0, 27.0, 29.0, 31.0, 33.0]
    a = detect_pre_wave(hist)
    assert a.phase == "DIVERGENCE"
    assert a.pre_wave is True


def test_predictor_neutral_phase():
    """Neutral : sigma dans la plage mais pente plate → NEUTRAL."""
    hist = [15.0, 15.1, 15.0, 15.1, 15.0]
    a = detect_pre_wave(hist)
    assert a.phase == "NEUTRAL"
    assert a.pre_wave is False


# ─────────────────────────────────────────────────────────────────────
# INTEGRATION — pipeline live (H-NEXT)
# ─────────────────────────────────────────────────────────────────────

def test_pipeline_fail_open_missing_db():
    """R6 fail-open : DB inexistante → pre_wave_phase=NEUTRAL (défaut dataclass)."""
    rep = run_live_pipeline(
        "EURUSD", "/nonexistent_prewave_xyz.db",
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert "error" in rep.audit  # fail-open signalé
    assert rep.pre_wave_phase == "NEUTRAL"  # défaut dataclass
    assert rep.watch_only is False


def test_pipeline_watch_only_on_divergence(tmp_db):
    """DIVERGENCE → watch_only=True (skip trade), multiplier inchangé."""
    db = tmp_db(_DIVERGENT_SERIES)
    rep = run_live_pipeline(
        "EURUSD", db,
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert rep.watch_only is True
    assert rep.pre_wave_phase == "DIVERGENCE"
    assert rep.audit["pre_wave"]["watch_only"] is True
    assert rep.audit["pre_wave"]["signal_score_multiplier"] == 1.0


def test_pipeline_compression_boost_multiplier(tmp_db):
    """COMPRESSION → signal_score_multiplier == 1.15, pas watch_only."""
    db = tmp_db(_COMPRESS_SERIES)
    rep = run_live_pipeline(
        "EURUSD", db,
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert rep.pre_wave_phase == "COMPRESSION"
    assert rep.watch_only is False
    assert rep.audit["pre_wave"]["signal_score_multiplier"] == 1.15


def test_pipeline_report_has_prewave_fields(tmp_db):
    """LivePipelineReport expose pre_wave_phase + watch_only (R9)."""
    db = tmp_db(_COMPRESS_SERIES)
    rep = run_live_pipeline(
        "EURUSD", db,
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    d = rep.as_dict()
    assert "pre_wave_phase" in d
    assert "watch_only" in d
    assert "pre_wave_sigma_current" in d
    assert d["pre_wave_phase"] == rep.pre_wave_phase


def test_pipeline_default_report_neutral():
    """LivePipelineReport() défaut : NEUTRAL, pas watch_only."""
    rep = LivePipelineReport()
    assert rep.pre_wave_phase == "NEUTRAL"
    assert rep.watch_only is False


# ─────────────────────────────────────────────────────────────────────
# EXPORT — PreWaveAlert exporté dans __init__.py (H-NEXT)
# ─────────────────────────────────────────────────────────────────────

def test_pre_wave_alert_exported():
    """PreWaveAlert accessible via core.v10 (export __init__)."""
    from core.v10 import PreWaveAlert as ExportPreWave
    assert ExportPreWave is PreWaveAlert
