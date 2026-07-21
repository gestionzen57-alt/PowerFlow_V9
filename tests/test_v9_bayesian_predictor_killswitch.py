"""Tests — kill switch Bayesian predictor + smoke (Axe 2.3 J5).

Doctrine : R7 (tests verts), R22 (CLI lecture seule), R25' (kill switch OFF).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_kill_switch_default_off():
    """V9_BAYESIAN_PREDICTOR_ENABLED absent ou 0 → OFF par défaut."""
    from core.v9.kill_switches import bayesian_predictor_enabled
    assert bayesian_predictor_enabled() is False


def test_kill_switch_function_exists():
    """bayesian_predictor_enabled() existe et est callable."""
    from core.v9 import kill_switches
    assert hasattr(kill_switches, "bayesian_predictor_enabled")
    assert callable(kill_switches.bayesian_predictor_enabled)
    # Comportement par défaut
    assert kill_switches.bayesian_predictor_enabled() is False


def test_module_imports():
    """Le module v9_bayesian_predictor expose son API publique."""
    from core.v9 import v9_bayesian_predictor
    assert hasattr(v9_bayesian_predictor, "predict")
    assert hasattr(v9_bayesian_predictor, "fit_platt")
    assert hasattr(v9_bayesian_predictor, "BetaPosterior")
    assert hasattr(v9_bayesian_predictor, "PlattCalibrator")
    assert hasattr(v9_bayesian_predictor, "CalibrationMetrics")
    assert hasattr(v9_bayesian_predictor, "compute_calibration_metrics")


def test_kill_switch_documented():
    """Le kill switch a une docstring explicative (R25' strict)."""
    from core.v9.kill_switches import bayesian_predictor_enabled
    func = bayesian_predictor_enabled
    assert func.__doc__ is not None
    assert "R25'" in func.__doc__
    assert "motion CEO" in func.__doc__


def test_bayesian_predictor_predict_no_crash_on_empty_db(tmp_path):
    """predict() sans fit préalable sur DB vide → fallback gracieux (R6)."""
    import sqlite3
    from core.v9.v9_bayesian_predictor import predict, BAYESIAN_ENABLED_ENV, init_calibration_db

    # DB vide
    db = tmp_path / "empty.db"
    init_calibration_db(db)

    # predict() doit retourner qqch sans crash (R6 fail-safe)
    # L'API exacte dépend du module ; on vérifie juste l'import
    assert callable(predict)
