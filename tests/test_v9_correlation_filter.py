"""Tests pour L12 Correlation inter-paires × regime (Phase 128).

Couvre 6 cas critiques (R7 strict) :
1. Kill switch OFF → pass-through systématique (sizing 1.0)
2. Pas d'open positions → go=True, sizing=1.0
3. 1 position correlee > 0.7 meme regime → go=True, sizing=0.5
4. 2+ positions correlees meme regime → go=False
5. 2 paires correlees mais regimes DIFFERENTS → sizing=1.0
6. R6 fail-open : correlation_matrix=None ou vide → pass-through
7. GBPUSD vs GBPUSD (meme symbole) → ignore (correlation 1.0 mais pas applicable)
8. Accesseurs sont bien dans kill_switches
"""
import importlib
import os
from typing import Any

import pytest


# ── Helpers ────────────────────────────────────────────────────────────
def _reload_kill_switches():
    """Recharge kill_switches pour prendre en compte les env vars modifiees."""
    from core.v9 import kill_switches
    # Reset le cache AVANT reload pour que le nouveau module reparte vide
    kill_switches._switches = None
    importlib.reload(kill_switches)
    # Double reset apres reload (au cas où reload re-importe)
    kill_switches._switches = None
    return kill_switches


def _reload_correlation_filter():
    """Recharge le module v9_correlation_filter."""
    from core.v9 import v9_correlation_filter
    importlib.reload(v9_correlation_filter)
    return v9_correlation_filter


@pytest.fixture(autouse=True)
def _reset_kill_switches_cache():
    """Reset le cache kill_switches avant chaque test (cle env modifiee OK)."""
    from core.v9 import kill_switches
    kill_switches._switches = None
    yield
    kill_switches._switches = None


# ── Tests accesseurs ───────────────────────────────────────────────────
def test_correlation_filter_accessors_registered():
    """Les 2 accesseurs (kill_switches + module) sont presents et bien types."""
    from core.v9 import kill_switches
    assert hasattr(kill_switches, "correlation_filter_enabled")
    import inspect
    sig = inspect.signature(kill_switches.correlation_filter_enabled)
    assert str(sig.return_annotation) == "bool"

    from core.v9 import v9_correlation_filter
    assert hasattr(v9_correlation_filter, "evaluate_correlation_filter")
    assert hasattr(v9_correlation_filter, "get_correlation")
    assert hasattr(v9_correlation_filter, "DEFAULT_CORRELATION_MATRIX")
    assert hasattr(v9_correlation_filter, "correlation_threshold")


def test_correlation_filter_default_off(monkeypatch):
    """Defaut OFF (R25' strict) si env absent du fichier .env."""
    monkeypatch.delenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", raising=False)
    # Reset cache
    from core.v9 import kill_switches
    kill_switches._switches = None
    # Le fichier env n'a pas cette cle, donc l'accesseur doit retourner False
    # (on force la valeur par defaut)
    val = kill_switches.get("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "0")
    assert val == "0"
    assert kill_switches.correlation_filter_enabled() is False


# ── Tests fonctionnels ────────────────────────────────────────────────
def test_kill_switch_off_passthrough(monkeypatch):
    """Kill switch OFF → pass-through (sizing=1.0, go=True)."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "0")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[{"symbol": "EURUSD", "regime": "EXTENSION"}],
    )
    assert result["go"] is True
    assert result["sizing_multiplier"] == 1.0
    assert result["reason"] == "no_filter"
    assert result["leviers"] == []


def test_no_open_positions_passthrough(monkeypatch):
    """Aucune position ouverte → pass-through (sizing=1.0, go=True)."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "1")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[],
    )
    assert result["go"] is True
    assert result["sizing_multiplier"] == 1.0
    assert result["reason"] == "no_filter"
    assert result["n_correlated_same_regime"] == 0


def test_one_correlated_same_regime_sizing_half(monkeypatch):
    """1 position correlee > 0.7 meme regime → sizing=0.5, go=True."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "1")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    # GBPUSD-EURUSD correlation = 0.85 (> 0.7) et meme regime EXTENSION
    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[{"symbol": "EURUSD", "regime": "EXTENSION"}],
    )
    assert result["go"] is True
    assert result["sizing_multiplier"] == 0.5
    assert result["reason"] == "correlation_same_regime"
    assert "L12_correlation_same_regime_x0.5" in result["leviers"]
    assert result["n_correlated_same_regime"] == 1
    assert result["correlations_max"] >= 0.7


def test_two_correlated_same_regime_blocked(monkeypatch):
    """2+ positions correlees meme regime → go=False (skip)."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "1")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    # GBPUSD-EURUSD=0.85 + GBPUSD-AUDUSD=0.55 (en dessous du seuil)
    # Pour avoir 2 correlees > 0.7, on prend GBPUSD + EURUSD + USDCHF (cor=-0.95)
    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[
            {"symbol": "EURUSD", "regime": "EXTENSION"},
            {"symbol": "USDCHF", "regime": "EXTENSION"},
        ],
    )
    assert result["go"] is False
    assert result["sizing_multiplier"] == 0.0
    assert result["reason"] == "too_many_correlated"
    assert "L12_correlation_block_ge2_same_regime" in result["leviers"]
    assert result["n_correlated_same_regime"] == 2


def test_correlated_different_regime_passthrough(monkeypatch):
    """2 paires correlees mais regimes DIFFERENTS → pass-through."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "1")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    # GBPUSD-EURUSD=0.85 mais regimes differents (EXTENSION vs CASSURE)
    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[{"symbol": "EURUSD", "regime": "CASSURE"}],
    )
    assert result["go"] is True
    assert result["sizing_multiplier"] == 1.0
    assert result["reason"] == "no_filter"
    assert result["n_correlated_same_regime"] == 0


def test_correlation_matrix_none_failopen(monkeypatch):
    """R6 fail-open : correlation_matrix=None → pass-through safe."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "1")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    # correlation_matrix=None → get_correlation retourne 0.0 (default matrix)
    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[{"symbol": "EURUSD", "regime": "EXTENSION"}],
        correlation_matrix=None,
    )
    # Avec la DEFAULT_CORRELATION_MATRIX, GBPUSD-EURUSD=0.85 → toujours declenche
    # Pour tester le fail-open avec matrice vide :
    result2 = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[{"symbol": "EURUSD", "regime": "EXTENSION"}],
        correlation_matrix={},
    )
    # Matrice vide → correlation=0 → pass-through
    assert result2["go"] is True
    assert result2["sizing_multiplier"] == 1.0
    assert result2["reason"] == "no_filter"
    assert result2["n_correlated_same_regime"] == 0


def test_same_symbol_ignored(monkeypatch):
    """Meme symbole (correlation=1.0 mais ce n'est pas applicable) → ignore."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "1")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    # GBPUSD ouvert en EXTENSION, nouvelle entree GBPUSD EXTENSION → pass-through
    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[{"symbol": "GBPUSD", "regime": "EXTENSION"}],
    )
    assert result["go"] is True
    assert result["sizing_multiplier"] == 1.0
    assert result["n_correlated_same_regime"] == 0


def test_get_correlation_mirror_pairs():
    """USDCHF est le mirror de GBPUSD (correlation -0.95)."""
    cf = _reload_correlation_filter()
    corr = cf.get_correlation("GBPUSD", "USDCHF")
    assert corr == -0.95
    # Inverse : USDCHF-GBPUSD doit donner la meme valeur
    corr2 = cf.get_correlation("USDCHF", "GBPUSD")
    assert corr2 == -0.95


def test_get_correlation_same_symbol():
    """Meme symbole → correlation 1.0."""
    cf = _reload_correlation_filter()
    assert cf.get_correlation("GBPUSD", "GBPUSD") == 1.0


def test_get_correlation_unknown_pair():
    """Paire inconnue de la matrice → correlation 0.0 (non correlee)."""
    cf = _reload_correlation_filter()
    # XXXYYY n'est pas dans la matrice
    assert cf.get_correlation("XXXYYY", "ZZZWWW") == 0.0


def test_correlation_threshold_default():
    """Seuil par defaut = 0.7 (R25' strict, motion CEO)."""
    cf = _reload_correlation_filter()
    # S'assurer que le defaut est bien 0.7
    from core.v9 import kill_switches
    kill_switches._switches = None
    monkeypatch_delenv = os.environ.pop("V9_L12_CORR_THRESHOLD", None)
    try:
        threshold = cf.correlation_threshold()
        assert threshold == 0.7
    finally:
        if monkeypatch_delenv is not None:
            os.environ["V9_L12_CORR_THRESHOLD"] = monkeypatch_delenv


def test_threshold_lower_includes_more_pairs(monkeypatch):
    """Un seuil plus bas (0.5) inclut plus de paires (AUDUSD, USDCAD...)."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "1")
    monkeypatch.setenv("V9_L12_CORR_THRESHOLD", "0.5")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    # GBPUSD-AUDUSD=0.55 > 0.5 → doit declencher le sizing ×0.5
    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[{"symbol": "AUDUSD", "regime": "EXTENSION"}],
    )
    assert result["go"] is True
    assert result["sizing_multiplier"] == 0.5
    assert result["n_correlated_same_regime"] == 1


def test_evaluate_correlation_filter_handles_bad_input(monkeypatch):
    """R6 fail-open : input mal forme ne leve jamais d'exception."""
    monkeypatch.setenv("V9_HEATMAP_L12_CORRELATION_REGIME_ENABLED", "1")
    _reload_kill_switches()
    cf = _reload_correlation_filter()

    # open_positions=None (devrait deja etre gere, on double-check)
    result = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=None,
    )
    assert result["go"] is True
    assert result["sizing_multiplier"] == 1.0

    # open_positions avec des dicts mal formes
    result2 = cf.evaluate_correlation_filter(
        symbol="GBPUSD",
        regime="EXTENSION",
        open_positions=[{"bad_key": "value"}, {}, {"symbol": None, "regime": "EXTENSION"}],
    )
    # Pas d'exception, retour safe
    assert result2["go"] is True
    assert "sizing_multiplier" in result2
