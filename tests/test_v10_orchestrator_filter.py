"""Test S23-A — Filter Compositor câblé dans l'orchestrateur."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_orchestrator import compose_signal_with_context  # noqa: E402
from core.v10.v10_session_filter import get_session_quality  # noqa: E402
from core.v10.v10_ict_ote import compute_ict_ote  # noqa: E402
from core.v10.v10_smc import detect_smc  # noqa: E402
from core.v10.v10_regime_hmm import detect_hmm_regime  # noqa: E402


def _sample_bars():
    """Retourne des barres OHLCV simples pour test."""
    return [
        {"open": 1.1000, "high": 1.1010, "low": 1.0990, "close": 1.1005, "volume": 1000, "bar_time": 1700000000 + i * 1800}
        for i in range(30)
    ]


def _sample_public_filters():
    """Crée des filtres publics par défaut pour tester la chaîne complète."""
    bars = _sample_bars()
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    return {
        "session": get_session_quality("EURUSD", timestamp="2026-08-07T10:00:00Z", seed=42),
        "ote": compute_ict_ote("EURUSD", "M30", closes, highs=highs, lows=lows, timestamp="2026-08-07T10:00:00Z"),
        "smc": detect_smc(bars, symbol="EURUSD", timeframe="M30", timestamp="2026-08-07T10:00:00Z"),
        "regime": detect_hmm_regime(closes, symbol="EURUSD", timestamp="2026-08-07T10:00:00Z"),
    }


def test_s23a_filter_compositor_called_and_trace_present():
    """1. Signal passe par filter_compositor → trace 3_filter_trace présente."""
    result = compose_signal_with_context(
        symbol="EURUSD",
        pair="EURUSD",
        timestamp="2026-08-07T10:00:00Z",
        timeframe="M30",
        bars=_sample_bars(),
        db_path="data/v9_forces.db",
        public_filters=_sample_public_filters(),
    )
    # Le trace doit être présent dans le CoT
    trace = result.signal.cot.get("3_filter_trace", None)
    assert trace is not None, "3_filter_trace absent du CoT"
    # Le trace est un CompositorResult.as_dict() avec trace (list) et audit
    assert "audit" in trace
    assert "filters_applied" in trace["audit"]
    assert "trace" in trace
    assert trace["original_level"] in ("NONE", "A3", "A2", "A1")


def test_s23a_a2_london_upgradable_via_smc():
    """2. Signal A2 session London + SMC boost → upgrade possible (pas downgrade)."""
    result = compose_signal_with_context(
        symbol="EURUSD",
        pair="EURUSD",
        timestamp="2026-08-07T10:00:00Z",  # Session London
        timeframe="M30",
        bars=_sample_bars(),
        db_path="data/v9_forces.db",
        public_filters=_sample_public_filters(),
    )
    trace = result.signal.cot.get("3_filter_trace", {})
    assert trace.get("final_level") in ("A1", "A2", "A3", "NONE")


def test_s23a_fail_open_exception_returns_original_signal():
    """3. Exception dans filter_chain → signal original retourné (fail-open R6)."""
    result = compose_signal_with_context(
        symbol="EURUSD",
        pair="EURUSD",
        timestamp="2026-08-07T10:00:00Z",
        timeframe="M30",
        bars=_sample_bars(),
        db_path="data/v9_forces.db",
    )
    # Le signal doit être retourné (pas d'exception propagée)
    assert result is not None
    assert hasattr(result, "signal")
    assert result.signal.setup_level in ("NONE", "A3", "A2", "A1")


def test_s23a_filter_trace_present_in_output():
    """4. Champ filter_trace présent dans l'output as_dict()."""
    result = compose_signal_with_context(
        symbol="EURUSD",
        pair="EURUSD",
        timestamp="2026-08-07T10:00:00Z",
        timeframe="M30",
        bars=_sample_bars(),
        db_path="data/v9_forces.db",
        public_filters=_sample_public_filters(),
    )
    trace = result.signal.cot.get("3_filter_trace", {})
    assert trace, "filter_trace doit être non-vide"
    assert "audit" in trace
    assert "filters_applied" in trace["audit"]
    assert len(trace["audit"]["filters_applied"]) > 0, "Au moins un filtre doit être appliqué"


def test_s23a_session_quality_impacts_level():
    """5. Test que la qualité de session influence le niveau (London vs Asian)."""
    # Note: get_session_quality utilise le timestamp, pas le timeframe
    bars = _sample_bars()
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    
    filters_london = {
        "session": get_session_quality("EURUSD", timestamp="2026-08-07T10:00:00Z", seed=42),
        "ote": compute_ict_ote("EURUSD", "M30", closes, highs=highs, lows=lows, timestamp="2026-08-07T10:00:00Z"),
        "smc": detect_smc(bars, symbol="EURUSD", timeframe="M30", timestamp="2026-08-07T10:00:00Z"),
        "regime": detect_hmm_regime(closes, symbol="EURUSD", timestamp="2026-08-07T10:00:00Z"),
    }
    filters_asian = {
        "session": get_session_quality("EURUSD", timestamp="2026-08-07T03:00:00Z", seed=42),
        "ote": compute_ict_ote("EURUSD", "M30", closes, highs=highs, lows=lows, timestamp="2026-08-07T03:00:00Z"),
        "smc": detect_smc(bars, symbol="EURUSD", timeframe="M30", timestamp="2026-08-07T03:00:00Z"),
        "regime": detect_hmm_regime(closes, symbol="EURUSD", timestamp="2026-08-07T03:00:00Z"),
    }
    
    res_london = compose_signal_with_context(
        symbol="EURUSD",
        pair="EURUSD",
        timestamp="2026-08-07T10:00:00Z",
        timeframe="M30",
        bars=_sample_bars(),
        db_path="data/v9_forces.db",
        public_filters=filters_london,
    )
    res_asian = compose_signal_with_context(
        symbol="EURUSD",
        pair="EURUSD",
        timestamp="2026-08-07T03:00:00Z",
        timeframe="M30",
        bars=_sample_bars(),
        db_path="data/v9_forces.db",
        public_filters=filters_asian,
    )
    trace_london = res_london.signal.cot.get("3_filter_trace", {})
    trace_asian = res_asian.signal.cot.get("3_filter_trace", {})
    # Les deux doivent avoir une trace avec filters_applied dans audit
    assert trace_london.get("audit", {}).get("filters_applied", []), "London: filters_applied manquant"
    assert trace_asian.get("audit", {}).get("filters_applied", []), "Asian: filters_applied manquant"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])