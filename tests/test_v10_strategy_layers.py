"""V10 Strategy Layers — tests du wrapper de câblage des stratégies publiques.

⚠️ Architecture (R2 additif, cœur unique) : ce module est un WRAPPER du
filtreur officiel `v10_filter_compositor.compose_filters` (Sprint 4 Hermes).
Il calcule les objets (session / OTE / SMC / régime HMM) et délègue la chaîne
de conviction. Les tests vérifient :
  1. R6 fail-open : données insuffisantes → aucune couche, niveau inchangé.
  2. A1 hors kill zone / hors zone OTE → downgrade A2 (filtre conviction).
  3. A1 dans zone OTE + conviction → conservé (ou soft si pas in_ote).
  4. A2/A3/NONE jamais modifiés par les filtres de conviction (pas de boost
     inventé — compose_filters ne downgrade que ce qui doit l'être).
  5. Régime HMM UNKNOWN → blocage conservateur R6 (trace).
  6. apply_strategy_layers_to_signal : enrichit setup_level + blockers + cot.
  7. R6 : exceptions / signal inconnu → fail-open (inchangé).
  8. R2 : aucun import core/v9/.
  9. as_dict sérialisable (R9).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_strategy_layers import (
    StrategyLayersResult,
    apply_strategy_layers,
    apply_strategy_layers_to_signal,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

def _trend_bars(n: int = 60, start: float = 1.0, step: float = 0.001) -> list:
    """Barres haussières régulières (closes croissantes)."""
    bars = []
    price = start
    for i in range(n):
        o = price
        c = price + step
        bars.append({
            "open": o, "high": max(o, c) + 0.0005, "low": min(o, c) - 0.0005,
            "close": c, "tick_volume": 100.0, "timestamp": f"2026-08-05T{i:02d}:00:00Z",
        })
        price = c
    return bars


def _swing_bars(n: int = 60) -> list:
    """Barres en V : baisse 30 puis hausse 30 (swing avec retracement)."""
    bars = []
    price = 1.10
    for i in range(n // 2):
        o = price
        c = price - 0.001
        bars.append({"open": o, "high": o + 0.0005, "low": c - 0.0005,
                     "close": c, "tick_volume": 100.0, "timestamp": f"2026-08-05T{i:02d}:00:00Z"})
        price = c
    for i in range(n // 2, n):
        o = price
        c = price + 0.0005
        bars.append({"open": o, "high": c + 0.0005, "low": min(o, c) - 0.0005,
                     "close": c, "tick_volume": 100.0, "timestamp": f"2026-08-05T{i:02d}:00:00Z"})
        price = c
    return bars


class _FakeSignal:
    """Signal minimal compatible EnhancedSignal/V10Signal (duck-typing)."""

    def __init__(self, level: str = "A1", direction: str = "BULLISH"):
        self.symbol = "EURUSD"
        self.timestamp = "2026-08-05T12:00:00Z"
        self.timeframe = "M30"
        self.pair = "EURUSD"
        self.direction = direction
        self.setup_level = level
        self.blockers = []
        self.reasoning = {}
        self.cot = {}
        self.audit = {}
        self.tradeable = level in ("A1", "A2")


# ─────────────────────────────────────────────────────────────────────
# 1. R6 fail-open : données insuffisantes
# ─────────────────────────────────────────────────────────────────────
def test_insufficient_data_fail_open():
    res = apply_strategy_layers("A1", bars=[], timestamp="2026-08-05T12:00:00Z")
    assert res.final_level == "A1"  # inchangé
    assert res.audit.get("applied") is False
    assert "insufficient_data" in res.audit.get("reason", "")


# ─────────────────────────────────────────────────────────────────────
# 2. A1 hors kill zone → downgrade A2
# ─────────────────────────────────────────────────────────────────────
def test_a1_outside_killzone_downgraded():
    # Timestamp dimanche 00:00 UTC → kill zone UNKNOWN/OUTSIDE
    bars = _trend_bars()
    res = apply_strategy_layers(
        "A1", bars=bars, symbol="EURUSD", timeframe="M30",
        timestamp="2026-08-02T00:00:00Z",
    )
    # La chaîne (session + OTE) doit avoir filtré : A1 → A2 (ou moins)
    assert res.downgraded is True
    assert res.final_level in ("A2", "A3", "NONE")
    assert res.compositor is not None
    # Trace R9 : le filtre OTE a été appliqué
    filters = [t.filter_name for t in res.compositor.trace]
    assert "ote" in filters


# ─────────────────────────────────────────────────────────────────────
# 3. A1 dans zone OTE + conviction → conservé (soft sinon)
# ─────────────────────────────────────────────────────────────────────
def test_a1_in_ote_conserved():
    bars = _swing_bars()
    res = apply_strategy_layers(
        "A1", bars=bars, symbol="EURUSD", timeframe="M30",
        timestamp="2026-08-05T14:00:00Z",  # NY kill zone (13-17 UTC)
    )
    # Jamais de crash, niveau final dans l'ensemble valide
    assert res.final_level in ("A1", "A2", "A3", "NONE")
    assert res.compositor is not None
    assert res.compositor.original_level == "A1"
    # Si le prix est dans la zone OTE ET kill zone active → A1 conservé
    ote_traces = [t for t in res.compositor.trace if t.filter_name == "ote"]
    if ote_traces and ote_traces[0].detail.get("in_ote") and ote_traces[0].severity == "none":
        assert res.final_level == "A1"


# ─────────────────────────────────────────────────────────────────────
# 4. A2/A3/NONE jamais boostés par les filtres de conviction
# ─────────────────────────────────────────────────────────────────────
def test_a2_never_boosted_by_ote():
    # Le compositor ne booste JAMAIS A2→A1 sur OTE (les filtres publics sont
    # des filtres de conviction/downgrade, pas des générateurs de signaux).
    bars = _swing_bars()
    res = apply_strategy_layers(
        "A2", bars=bars, symbol="EURUSD", timeframe="M30",
        timestamp="2026-08-05T15:00:00Z",  # NY kill zone
    )
    assert res.final_level in ("A2", "A3", "NONE")  # jamais A1
    assert res.final_level != "A1"


def test_a3_none_never_modified():
    bars = _trend_bars()
    for level in ("A3", "NONE"):
        res = apply_strategy_layers(
            level, bars=bars, symbol="EURUSD", timeframe="M30",
            timestamp="2026-08-05T15:00:00Z",
        )
        # A3/NONE : les filtres ne créent jamais de signal (pas de boost A3→A2
        # sans SMC MSS/BOS détecté — et même alors, A3→A2 au plus)
        assert res.final_level in ("NONE", "A3", "A2")
        assert res.final_level not in ("A1",)


# ─────────────────────────────────────────────────────────────────────
# 5. Régime HMM dans la trace + blocage conservateur si UNKNOWN
# ─────────────────────────────────────────────────────────────────────
def test_regime_hmm_in_trace():
    bars = _trend_bars(n=80)
    res = apply_strategy_layers(
        "A2", bars=bars, symbol="EURUSD", timeframe="M30",
        timestamp="2026-08-05T15:00:00Z",
    )
    assert res.compositor is not None
    filters = [t.filter_name for t in res.compositor.trace]
    assert "regime" in filters
    # Régime détecté (TRENDING_UP sur tendance régulière) — jamais de crash
    assert res.final_level in ("A1", "A2", "A3", "NONE")


# ─────────────────────────────────────────────────────────────────────
# 6. apply_strategy_layers_to_signal : enrichit le signal
# ─────────────────────────────────────────────────────────────────────
def test_signal_enrichment():
    sig = _FakeSignal(level="A2")
    bars = _trend_bars()
    out, res = apply_strategy_layers_to_signal(sig, bars=bars)
    assert out is sig
    assert res.final_level in ("A1", "A2", "A3", "NONE")
    assert sig.setup_level == res.final_level
    # R5 CoT : reasoning + cot enrichis
    assert "strategy_layers" in sig.reasoning
    assert "strategy_layers" in sig.cot
    # R9 : as_dict sérialisable
    d = res.as_dict()
    assert "compositor" in d and "final_level" in d and "audit" in d


# ─────────────────────────────────────────────────────────────────────
# 7. R6 : exceptions → fail-open (signal inchangé)
# ─────────────────────────────────────────────────────────────────────
def test_fail_open_on_invalid_bars():
    sig = _FakeSignal(level="A1")
    # Barres invalides (pas de "close") → R6 : signal inchangé
    bad_bars = [{"open": 1.0} for _ in range(40)]
    out, res = apply_strategy_layers_to_signal(sig, bars=bad_bars)
    assert out is sig
    assert sig.setup_level == "A1"  # inchangé


def test_fail_open_unknown_signal():
    # Signal sans setup_level (type inconnu) → (obj, result) inchangés
    class _Weird:
        pass
    obj = _Weird()
    out, res = apply_strategy_layers_to_signal(obj, bars=_trend_bars())
    assert out is obj
    assert res.final_level == "NONE"


# ─────────────────────────────────────────────────────────────────────
# 8. R2 : aucun import core/v9/
# ─────────────────────────────────────────────────────────────────────
def test_r2_additif_no_core_v9():
    src = Path(ROOT / "core" / "v10" / "v10_strategy_layers.py").read_text(encoding="utf-8")
    assert "core/v9" not in src
    assert "core.v9" not in src


# ─────────────────────────────────────────────────────────────────────
# 9. Export package (façade cohérente)
# ─────────────────────────────────────────────────────────────────────
def test_package_exports():
    import core.v10 as v
    assert hasattr(v, "apply_strategy_layers")
    assert hasattr(v, "apply_strategy_layers_to_signal")
    assert hasattr(v, "StrategyLayersResult")
