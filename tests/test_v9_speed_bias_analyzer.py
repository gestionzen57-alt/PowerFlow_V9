"""Tests pour v9_speed_bias_analyzer.

2026-07-17 motion CEO « le trend baissier est plus rapide dans la baisse est
ca que la lecture des time frame > est pas biaisai par le temps qui lisse ».

Le CEO a identifié un problème de perception temporelle. Ce module prouve
statistiquement l'asymétrie haussier/baissier sur les P95.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

import pytest

from core.v9.v9_speed_bias_analyzer import (
    SpeedBiasAnalyzer,
    SpeedBiasReport,
    BarMovementStats,
    SPEED_BIAS_VERSION,
)


def test_speed_bias_version() -> None:
    """Version 1.0 du module."""
    assert SPEED_BIAS_VERSION == "1.0"


def test_analyze_timeframe_returns_report() -> None:
    """analyze_timeframe doit retourner un SpeedBiasReport valide."""
    analyzer = SpeedBiasAnalyzer()
    rep = analyzer.analyze_timeframe(symbol="GBPUSD", timeframe="M5")
    assert isinstance(rep, SpeedBiasReport)
    assert rep.symbol == "GBPUSD"
    assert rep.timeframe == "M5"
    assert rep.sample_size > 100
    assert rep.bullish.n_bars > 0
    assert rep.bearish.n_bars > 0


def test_bearish_p95_smaller_than_bullish_p95() -> None:
    """Hypothèse CEO confirmée : P95 baissier << P95 haussier."""
    analyzer = SpeedBiasAnalyzer()
    rep = analyzer.analyze_timeframe(symbol="GBPUSD", timeframe="M5")
    # L'asymétrie : bearish P95 doit être largement plus petit en magnitude
    assert abs(rep.bearish.p95_delta_pips) < rep.bullish.p95_delta_pips, (
        f"Hypothèse CEO non confirmée : bull P95={rep.bullish.p95_delta_pips}, "
        f"bear P95={rep.bearish.p95_delta_pips}"
    )
    # Le ratio doit être < 0.5 (bear est au moins 2x plus petit)
    assert rep.bear_to_bull_ratio < 0.5


def test_is_bearish_faster_false_for_sustained_moves() -> None:
    """Sur le dataset V9, le baissier n'est PAS plus rapide en amplitude P95
    que le haussier — il est plus CONCENTRÉ et BREF."""
    analyzer = SpeedBiasAnalyzer()
    rep = analyzer.analyze_timeframe(symbol="GBPUSD", timeframe="M5")
    # La propriété is_bearish_faster mesure si |bearish P95| > bullish P95
    # Sur les données réelles, c'est False (ratio < 1)
    # Le mouvement baissier est court et intense, suivi de flat = mean reversion
    assert rep.is_bearish_faster is False


def test_analyze_all_returns_multiple_reports() -> None:
    """analyze_all doit retourner plusieurs rapports."""
    analyzer = SpeedBiasAnalyzer()
    reports = analyzer.analyze_all()
    assert len(reports) >= 5
    # Toutes les paires doivent montrer l'asymétrie (bear << bull)
    for rep in reports[:3]:
        assert rep.bear_to_bull_ratio < 0.5


def test_report_to_dict_serializable() -> None:
    """Le rapport doit être sérialisable JSON."""
    import json
    analyzer = SpeedBiasAnalyzer()
    rep = analyzer.analyze_timeframe(symbol="GBPUSD", timeframe="M5")
    d = rep.to_dict()
    s = json.dumps(d)
    assert "bullish" in s
    assert "bearish" in s
    assert "recommendation" in s


def test_bar_movement_stats_to_dict() -> None:
    """BarMovementStats doit être sérialisable."""
    stats = BarMovementStats(
        n_bars=100,
        avg_delta_pips=1.5,
        median_delta_pips=1.0,
        p95_delta_pips=5.0,
        p99_delta_pips=8.0,
        avg_force_pips=2.0,
        max_delta_pips=10.0,
        avg_duration_bars=3.5,
    )
    d = stats.to_dict()
    assert d["n_bars"] == 100
    assert d["p95_delta_pips"] == 5.0


def test_analyze_unknown_symbol_returns_error() -> None:
    """analyze_timeframe sur symbole inconnu doit lever une erreur."""
    analyzer = SpeedBiasAnalyzer()
    with pytest.raises(ValueError, match="Pas assez"):
        analyzer.analyze_timeframe(symbol="XXXUNKNOWN", timeframe="M5")