"""tests/test_live_pipeline_prewave.py — H-NEXT (post-rebase ZCode API).

Vérifie l'intégration du détecteur de pré-vague Fatman (Z11 ZCode) dans le
pipeline live (v10_live_pipeline.run_live_pipeline) :

  - compression sigma détectée → pre_wave=True + signal_score boost 1.15
    + watch_only=True (WATCH_ONLY, skip trade)
  - pas de compression → pre_wave=False, multiplier 1.0, watch_only=False
  - fail-open R6 : historique sigma absent/erreur → pre_wave=False

API ZCode conservée : detect_pre_wave(sigma_history, *, window, ratio,
min_history) → PreWaveAlert{pre_wave, direction, sigma_recent, sigma_hist,
compression_ratio, notes}

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
                      → contrôle sigma[-1] (dernière barre) et la série sigma.
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

    # Forces "neutre" : toutes proches → sigma très bas
    comp = (50.0, 50.5, 50.2, 49.8, 50.1, 50.0, 49.9, 50.3)

    for tf in ("M30", "H1", "H4", "D1"):
        step = 1800 if tf == "M30" else 3600 if tf == "H1" else 14400 if tf == "H4" else 86400
        for i in range(n):
            forces = comp
            # Dernières barres H1 → forces spécifiques (série sigma contrôlée)
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


# Séries H1 chronologiques (10 dernières barres) contrôlant la compression sigma.
# 6 premières à sigma ~20 puis 4 dernières à sigma ~8 → récent << historique.
_HI_SIG = (60.0, 20.0, 60.0, 20.0, 60.0, 20.0, 60.0, 20.0)  # sigma ~20
_LO_SIG = (48.0, 32.0, 48.0, 32.0, 48.0, 32.0, 48.0, 32.0)  # sigma ~8
_COMPRESS_SERIES = [_HI_SIG, _HI_SIG, _HI_SIG, _HI_SIG, _HI_SIG, _HI_SIG,
                    _LO_SIG, _LO_SIG, _LO_SIG, _LO_SIG]
# Sigma stable (toutes proches) → pas de compression.
_STABLE_SERIES = [
    (50.0, 50.5, 50.2, 49.8, 50.1, 50.0, 49.9, 50.3)] * 10


# ─────────────────────────────────────────────────────────────────────
# UNIT — detect_pre_wave (Z11 ZCode) contrat attendu par le pipeline
# ─────────────────────────────────────────────────────────────────────

def test_predictor_compression():
    """Compression : récent << historique → pre_wave=True."""
    hist = [70.0, 65.0, 60.0, 40.0, 30.0, 20.0, 18.0, 16.0]
    a = detect_pre_wave(hist, min_history=4, window=3)
    assert a.pre_wave is True
    assert a.compression_ratio <= 0.60


def test_predictor_no_compression():
    """Sigma stable → pre_wave=False."""
    hist = [40.0] * 22
    a = detect_pre_wave(hist)
    assert a.pre_wave is False


def test_predictor_fail_open_short():
    """Historique trop court → pre_wave=False (R6 fail-open)."""
    a = detect_pre_wave([50.0, 48.0])
    assert a.pre_wave is False
    assert any("historique trop court" in n for n in a.notes)


# ─────────────────────────────────────────────────────────────────────
# INTEGRATION — pipeline live (H-NEXT)
# ─────────────────────────────────────────────────────────────────────

def test_pipeline_fail_open_missing_db():
    """R6 fail-open : DB inexistante → pre_wave=False (défaut dataclass)."""
    rep = run_live_pipeline(
        "EURUSD", "/nonexistent_prewave_xyz.db",
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert "error" in rep.audit  # fail-open signalé
    assert rep.pre_wave is False
    assert rep.watch_only is False


def test_pipeline_compression_boost(tmp_db):
    """Compression détectée → pre_wave=True + multiplier 1.15 + watch_only."""
    db = tmp_db(_COMPRESS_SERIES)
    rep = run_live_pipeline(
        "EURUSD", db,
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert rep.pre_wave is True
    assert rep.watch_only is True
    assert rep.audit["pre_wave"]["signal_score_multiplier"] == 1.15
    assert rep.audit["pre_wave"]["detected"] is True


def test_pipeline_no_compression(tmp_db):
    """Pas de compression → pre_wave=False, multiplier 1.0, watch_only False."""
    db = tmp_db(_STABLE_SERIES)
    rep = run_live_pipeline(
        "EURUSD", db,
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    assert rep.pre_wave is False
    assert rep.watch_only is False
    assert rep.audit["pre_wave"]["signal_score_multiplier"] == 1.0


def test_pipeline_report_has_prewave_fields(tmp_db):
    """LivePipelineReport expose pre_wave + watch_only + sigma (R9)."""
    db = tmp_db(_COMPRESS_SERIES)
    rep = run_live_pipeline(
        "EURUSD", db,
        timestamp="2026-08-05T00:00:00Z",
        use_calibrated_thresholds=False,
        use_calibrated_intensity=False,
    )
    d = rep.as_dict()
    assert "pre_wave" in d
    assert "watch_only" in d
    assert "pre_wave_compression_ratio" in d
    assert d["pre_wave"] == rep.pre_wave


def test_pipeline_default_report_neutral():
    """LivePipelineReport() défaut : pre_wave=False, pas watch_only."""
    rep = LivePipelineReport()
    assert rep.pre_wave is False
    assert rep.watch_only is False


# ─────────────────────────────────────────────────────────────────────
# EXPORT — PreWaveAlert exporté dans __init__.py (H-NEXT)
# ─────────────────────────────────────────────────────────────────────

def test_pre_wave_alert_exported():
    """PreWaveAlert accessible via core.v10 (export __init__)."""
    from core.v10 import PreWaveAlert as ExportPreWave
    assert ExportPreWave is PreWaveAlert
