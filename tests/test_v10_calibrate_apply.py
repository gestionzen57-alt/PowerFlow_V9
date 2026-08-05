"""V10 Calibrate Apply — tests unitaires (Phase R).

Obligations :
  1. test_find_recalibrated_thresholds_none_r6
  2. test_apply_config_no_thresholds
  3. test_ensure_active_no_thresholds
  4. test_apply_config_with_path
  5. test_r2_additif_no_core_v9
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_calibrate_apply import (  # noqa: E402
    find_recalibrated_thresholds,
    ensure_active_thresholds,
    apply_to_decision_config,
    ACTIVE_SEUILS_NAME,
)


def test_find_recalibrated_thresholds_none_r6(tmp_path, monkeypatch):
    # pointe ROOT vers un répertoire vide → fail-open None
    monkeypatch.setattr("core.v10.v10_calibrate_apply.ROOT", tmp_path)
    assert find_recalibrated_thresholds() is None


def test_apply_config_no_thresholds(monkeypatch):
    monkeypatch.setattr("core.v10.v10_calibrate_apply.find_recalibrated_thresholds",
                        lambda: None)
    cfg = apply_to_decision_config()
    assert cfg["thresholds_pair_tf_path"] is None
    assert cfg["r8_active"] is False


def test_apply_config_with_path():
    cfg = apply_to_decision_config(threshold_path="config/x.json")
    assert cfg["thresholds_pair_tf_path"] == "config/x.json"
    assert cfg["r8_active"] is True


def test_ensure_active_no_thresholds(tmp_path, monkeypatch):
    monkeypatch.setattr("core.v10.v10_calibrate_apply.ROOT", tmp_path)
    res = ensure_active_thresholds(force_recalib=False)
    assert res["status"] == "no_thresholds"


def test_r2_additif_no_core_v9():
    src = (ROOT / "core/v10/v10_calibrate_apply.py").read_text(encoding="utf-8")
    assert "core.v9" not in src
    assert "from core.v9" not in src
    assert "import v9_" not in src
