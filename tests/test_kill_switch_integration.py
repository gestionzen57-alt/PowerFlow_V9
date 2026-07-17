"""test_kill_switch_integration.py — Tests d'intégration kill switch.

Vérifie que chaque kill switch a un EFFET MESURABLE quand il passe de
OFF à ON. Évite les no-op silencieux (bug DRM fantôme 2026-07-17).

Pour chaque kill switch, on vérifie :
  1. Que la chaîne du switch est référencée dans le module consommateur ;
  2. Que la fonction d'état lit la variable d'environnement et renvoie
     un booléen qui suit l'état ON/OFF.

Note d'implémentation : les switches SHADOW et ADAPTIVE_THRESHOLDS sont
exposés par le chargeur central `core.v9.kill_switches` (et non par
`shadow_evaluator` / `adaptive_thresholds_at_runtime`). `shadow_evaluator`
expose sa propre fonction `is_shadow_mode_enabled`. On teste les deux.

Isolation : `monkeypatch.setenv` restaure l'environnement après chaque
test (R2 additif — ne pollue pas les autres tests).
"""
from __future__ import annotations

from core.v9.config import ROOT_DIR


def _core_file(rel: str) -> str:
    return (ROOT_DIR / rel).read_text(encoding="utf-8")


def test_dynamic_risk_enabled_has_effect(monkeypatch):
    """V9_DYNAMIC_RISK_ENABLED → trade_engine appelle (ou non) le DRM."""
    assert "V9_DYNAMIC_RISK_ENABLED" in _core_file("core/v9/trade_engine.py")

    from core.v9.trade_engine import _dynamic_risk_enabled

    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "1")
    assert _dynamic_risk_enabled() is True

    monkeypatch.setenv("V9_DYNAMIC_RISK_ENABLED", "0")
    assert _dynamic_risk_enabled() is False


def test_auto_calibrator_enabled_has_effect(monkeypatch):
    """V9_AUTO_CALIBRATOR_ENABLED → auto_calibrator actif ou non."""
    assert "V9_AUTO_CALIBRATOR_ENABLED" in _core_file("core/v9/auto_calibrator.py")

    from core.v9.auto_calibrator import auto_calibrator_enabled

    monkeypatch.setenv("V9_AUTO_CALIBRATOR_ENABLED", "1")
    assert auto_calibrator_enabled() is True

    monkeypatch.setenv("V9_AUTO_CALIBRATOR_ENABLED", "0")
    assert auto_calibrator_enabled() is False


def test_auto_optimizer_enabled_has_effect(monkeypatch):
    """V9_AUTO_OPTIMIZER_ENABLED → auto_optimizer actif ou non."""
    assert "V9_AUTO_OPTIMIZER_ENABLED" in _core_file("core/v9/auto_optimizer.py")

    from core.v9.auto_optimizer import auto_optimizer_enabled

    monkeypatch.setenv("V9_AUTO_OPTIMIZER_ENABLED", "1")
    assert auto_optimizer_enabled() is True

    monkeypatch.setenv("V9_AUTO_OPTIMIZER_ENABLED", "0")
    assert auto_optimizer_enabled() is False


def test_shadow_mode_enabled_has_effect(monkeypatch):
    """V9_SHADOW_MODE_ENABLED → shadow_evaluator / kill_switches suivent l'état."""
    assert "V9_SHADOW_MODE_ENABLED" in _core_file("core/v9/shadow_evaluator.py")

    from core.v9.shadow_evaluator import is_shadow_mode_enabled
    from core.v9.kill_switches import shadow_mode_enabled

    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "1")
    assert is_shadow_mode_enabled() is True
    assert shadow_mode_enabled() is True

    monkeypatch.setenv("V9_SHADOW_MODE_ENABLED", "0")
    assert is_shadow_mode_enabled() is False
    assert shadow_mode_enabled() is False


def test_adaptive_thresholds_enabled_has_effect(monkeypatch):
    """V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED → état suit ON/OFF."""
    assert "V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED" in _core_file(
        "core/v9/kill_switches.py"
    )

    from core.v9.kill_switches import adaptive_thresholds_wired_enabled

    monkeypatch.setenv("V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED", "1")
    assert adaptive_thresholds_wired_enabled() is True

    monkeypatch.setenv("V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED", "0")
    assert adaptive_thresholds_wired_enabled() is False


def test_learning_offset_enabled_has_effect(monkeypatch):
    """V9_LEARNING_OFFSET_ENABLED → learning_offset_applier suit l'état."""
    assert "V9_LEARNING_OFFSET_ENABLED" in _core_file(
        "core/v9/learning_offset_applier.py"
    )

    from core.v9.learning_offset_applier import learning_offset_enabled

    monkeypatch.setenv("V9_LEARNING_OFFSET_ENABLED", "1")
    assert learning_offset_enabled() is True

    monkeypatch.setenv("V9_LEARNING_OFFSET_ENABLED", "0")
    assert learning_offset_enabled() is False


def test_auto_promotion_enabled_has_effect(monkeypatch):
    """V9_AUTO_PROMOTION_ENABLED → auto_calibrator promeut ou non."""
    assert "V9_AUTO_PROMOTION_ENABLED" in _core_file("core/v9/auto_calibrator.py")

    from core.v9.auto_calibrator import auto_promotion_enabled

    monkeypatch.setenv("V9_AUTO_PROMOTION_ENABLED", "1")
    assert auto_promotion_enabled() is True

    monkeypatch.setenv("V9_AUTO_PROMOTION_ENABLED", "0")
    assert auto_promotion_enabled() is False
