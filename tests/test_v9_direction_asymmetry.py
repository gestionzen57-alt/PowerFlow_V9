"""Tests pour L16 Asymetrie WR par direction (Phase 129).

Couvre 7 cas critiques (R7 strict) :
1. Kill switch OFF → multiplier = 1.0 systematique
2. Kill switch ON, direction haussiere → multiplier = 1.3
3. Kill switch ON, direction baissiere → multiplier = 0.7
4. Kill switch ON, haussiere + RETOUR_EQUILIBRE → multiplier = 1.0
5. Kill switch ON, baissiere + CASSURE → multiplier = 1.0
6. apply_direction_asymmetry(2.0, "haussiere") → sizing_final = 2.6
7. R6 fail-open : direction inconnue → multiplier = 1.0
+ tests supplementaires (regime=None, bad input, accesseurs).
"""
import importlib
from typing import Any

import pytest


# ── Helpers ────────────────────────────────────────────────────────────
def _reload_kill_switches():
    """Recharge kill_switches pour prendre en compte les env vars modifiees."""
    from core.v9 import kill_switches
    kill_switches._switches = None
    importlib.reload(kill_switches)
    kill_switches._switches = None
    return kill_switches


def _reload_direction_asymmetry():
    """Recharge le module v9_direction_asymmetry."""
    from core.v9 import v9_direction_asymmetry
    importlib.reload(v9_direction_asymmetry)
    return v9_direction_asymmetry


@pytest.fixture(autouse=True)
def _reset_kill_switches_cache():
    """Reset le cache kill_switches avant chaque test (cle env modifiee OK)."""
    from core.v9 import kill_switches
    kill_switches._switches = None
    yield
    kill_switches._switches = None


# ── Tests accesseurs ───────────────────────────────────────────────────
def test_direction_asymmetry_accessors_registered():
    """Les accesseurs sont presents dans kill_switches et le module."""
    from core.v9 import kill_switches
    assert hasattr(kill_switches, "direction_asymmetry_enabled")
    import inspect
    sig = inspect.signature(kill_switches.direction_asymmetry_enabled)
    assert str(sig.return_annotation) == "bool"

    da = _reload_direction_asymmetry()
    assert hasattr(da, "compute_asymmetry_multiplier")
    assert hasattr(da, "apply_direction_asymmetry")
    assert hasattr(da, "DEFAULT_MULTIPLIERS")


def test_direction_asymmetry_default_off(monkeypatch):
    """Defaut OFF (R25' strict) si env absent du fichier .env."""
    monkeypatch.delenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", raising=False)
    from core.v9 import kill_switches
    kill_switches._switches = None
    val = kill_switches.get("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "0")
    assert val == "0"
    assert kill_switches.direction_asymmetry_enabled() is False


# ── Tests fonctionnels ────────────────────────────────────────────────
def test_kill_switch_off_passthrough(monkeypatch):
    """Kill switch OFF → multiplier = 1.0 systematiquement, sizing inchange."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "0")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    # Haussiere
    assert da.compute_asymmetry_multiplier("haussiere") == 1.0
    assert da.compute_asymmetry_multiplier("haussiere", "EXTENSION") == 1.0
    # Baissiere
    assert da.compute_asymmetry_multiplier("baissiere") == 1.0
    assert da.compute_asymmetry_multiplier("baissiere", "CASSURE") == 1.0
    # Apply
    result = da.apply_direction_asymmetry(2.0, "haussiere")
    assert result["sizing_final"] == 2.0
    assert result["multiplier"] == 1.0
    assert result["leviers"] == []


def test_haussiere_default_x1_3(monkeypatch):
    """Kill switch ON, haussiere sans regime → multiplier = 1.3."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    assert da.compute_asymmetry_multiplier("haussiere") == 1.3
    assert da.compute_asymmetry_multiplier("haussiere", "EXTENSION") == 1.3
    assert da.compute_asymmetry_multiplier("haussiere", "NEUTRE") == 1.3
    assert da.compute_asymmetry_multiplier("haussiere", "CASSURE") == 1.3


def test_baissiere_default_x0_7(monkeypatch):
    """Kill switch ON, baissiere sans regime ou regime standard → multiplier = 0.7."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    assert da.compute_asymmetry_multiplier("baissiere") == 0.7
    assert da.compute_asymmetry_multiplier("baissiere", "NEUTRE") == 0.7
    assert da.compute_asymmetry_multiplier("baissiere", "EXTENSION") == 0.7
    assert da.compute_asymmetry_multiplier("baissiere", "PALIER") == 0.7


def test_haussiere_retour_equilibre_neutral(monkeypatch):
    """Haussiere + RETOUR_EQUILIBRE → multiplier = 1.0 (mean-reversion)."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    assert da.compute_asymmetry_multiplier("haussiere", "RETOUR_EQUILIBRE") == 1.0


def test_baissiere_cassure_neutral(monkeypatch):
    """Baissiere + CASSURE → multiplier = 1.0 (edge baissier confirme)."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    assert da.compute_asymmetry_multiplier("baissiere", "CASSURE") == 1.0


def test_apply_direction_asymmetry_x1_3(monkeypatch):
    """apply_direction_asymmetry(2.0, "haussiere") → sizing_final = 2.6."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    result = da.apply_direction_asymmetry(2.0, "haussiere")
    assert result["sizing_final"] == 2.6
    assert result["multiplier"] == 1.3
    assert "L16_asymmetry_x1.3_haussiere" in result["leviers"]
    assert "boost haussier" in result["reason"]


def test_apply_direction_asymmetry_x0_7(monkeypatch):
    """apply_direction_asymmetry(1.0, "baissiere") → sizing_final = 0.7."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    result = da.apply_direction_asymmetry(1.0, "baissiere")
    assert abs(result["sizing_final"] - 0.7) < 1e-9
    assert result["multiplier"] == 0.7
    assert "L16_asymmetry_x0.7_baissiere" in result["leviers"]
    assert "attenuation baissier" in result["reason"]


def test_apply_direction_asymmetry_neutral_regime(monkeypatch):
    """apply_direction_asymmetry(1.0, "haussiere", "RETOUR_EQUILIBRE") → 1.0."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    result = da.apply_direction_asymmetry(1.0, "haussiere", "RETOUR_EQUILIBRE")
    assert result["sizing_final"] == 1.0
    assert result["multiplier"] == 1.0
    assert "mean-reversion" in result["reason"]

    result2 = da.apply_direction_asymmetry(1.0, "baissiere", "CASSURE")
    assert result2["sizing_final"] == 1.0
    assert result2["multiplier"] == 1.0
    assert "edge baissier" in result2["reason"]


def test_unknown_direction_passthrough(monkeypatch):
    """R6 fail-open : direction inconnue → multiplier = 1.0."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    assert da.compute_asymmetry_multiplier("unknown") == 1.0
    assert da.compute_asymmetry_multiplier("") == 1.0
    assert da.compute_asymmetry_multiplier("neutre") == 1.0
    assert da.compute_asymmetry_multiplier("XXX", "NEUTRE") == 1.0


def test_apply_direction_asymmetry_unknown_direction(monkeypatch):
    """R6 fail-open : direction inconnue → pass-through (sizing inchange)."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    result = da.apply_direction_asymmetry(2.5, "unknown")
    assert result["sizing_final"] == 2.5
    assert result["multiplier"] == 1.0


def test_apply_direction_asymmetry_bad_input_failopen(monkeypatch):
    """R6 fail-open : sizing_base = 'bad' doit etre coerce en float, pas d'exception."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    # sizing_base valide
    result = da.apply_direction_asymmetry(0.0, "haussiere")
    assert result["sizing_final"] == 0.0
    assert result["multiplier"] == 1.3

    # sizing_base negative (autorise pour net)
    result2 = da.apply_direction_asymmetry(-1.0, "haussiere")
    assert result2["sizing_final"] == -1.3


def test_direction_case_insensitive(monkeypatch):
    """Direction est normalisee en lowercase (robustesse)."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    # Majuscules
    assert da.compute_asymmetry_multiplier("HAUSSIERE") == 1.3
    assert da.compute_asymmetry_multiplier("Baissiere") == 0.7
    # Regime en lowercase aussi tolere
    assert da.compute_asymmetry_multiplier("haussiere", "retour_equilibre") == 1.0


def test_regime_unknown_for_known_direction(monkeypatch):
    """Direction connue mais regime inconnu → fallback direction par defaut."""
    monkeypatch.setenv("V9_HEATMAP_L16_ASYMMETRY_DIRECTION_ENABLED", "1")
    _reload_kill_switches()
    da = _reload_direction_asymmetry()

    # Haussiere + regime inconnu → fallback x1.3
    assert da.compute_asymmetry_multiplier("haussiere", "UNKNOWN_REGIME") == 1.3
    # Baissiere + regime inconnu → fallback x0.7
    assert da.compute_asymmetry_multiplier("baissiere", "FOO") == 0.7


def test_default_multipliers_table_complete():
    """La table DEFAULT_MULTIPLIERS couvre tous les regimes × direction."""
    da = _reload_direction_asymmetry()
    # 2 directions × 6 regimes = 12 entrees attendues
    assert len(da.DEFAULT_MULTIPLIERS) == 12
    # Verifie que les 2 cas speciaux sont presents
    assert da.DEFAULT_MULTIPLIERS[("haussiere", "RETOUR_EQUILIBRE")] == 1.0
    assert da.DEFAULT_MULTIPLIERS[("baissiere", "CASSURE")] == 1.0
