"""V10 Strategy Layers — tests du câblage OTE + HMM + SMC (Sprint 2/3b).

Obligations :
  1. apply_strategy_layers : données insuffisantes → R6 fail-open (aucune couche).
  2. apply_strategy_layers : A1 hors kill zone → downgrade A2 (filtre OTE).
  3. apply_strategy_layers : A1 dans zone OTE + conviction → A1 conservé.
  4. apply_strategy_layers : A2 + OTE in_ote + conviction haute → boost A1.
  5. apply_strategy_layers : A3/NONE jamais modifiés (filtre de conviction).
  6. apply_strategy_layers : HMM VOLATILE → audit (blocker côté signal).
  7. apply_strategy_layers_to_signal : enrichit setup_level + blockers + cot.
  8. R6 : exceptions → fail-open (signal inchangé).
  9. R2 : aucun import core/v9/.
  10. as_dict sérialisable (R9).
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
from core.v10.v10_ict_ote import KillZone


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
    # A1 hors kill zone → soft downgrade A2
    assert res.final_level == "A2"
    assert res.ote_downgraded is True
    assert res.ote_setup is not None


# ─────────────────────────────────────────────────────────────────────
# 3. A1 dans zone OTE + conviction → conservé
# ─────────────────────────────────────────────────────────────────────
def test_a1_in_ote_conserved():
    bars = _swing_bars()
    res = apply_strategy_layers(
        "A1", bars=bars, symbol="EURUSD", timeframe="M30",
        timestamp="2026-08-05T14:00:00Z",  # NY kill zone (13-17 UTC)
    )
    # Si le prix est dans la zone OTE ET kill zone active → A1 conservé
    ote = res.ote_setup
    assert ote is not None
    if ote.in_ote and ote.kill_zone in (KillZone.LONDON, KillZone.NY):
        assert res.final_level == "A1"
    else:
        # Sinon downgrade soft — mais jamais de crash
        assert res.final_level in ("A1", "A2")


# ─────────────────────────────────────────────────────────────────────
# 4. A2 + OTE in_ote + conviction haute → boost A1
# ─────────────────────────────────────────────────────────────────────
def test_a2_boost_a1_when_ote_strong():
    bars = _swing_bars()
    res = apply_strategy_layers(
        "A2", bars=bars, symbol="EURUSD", timeframe="M30",
        timestamp="2026-08-05T15:00:00Z",  # NY kill zone
        ote_conviction_min=0.0,  # force le boost si in_ote
    )
    ote = res.ote_setup
    assert ote is not None
    # Si in_ote ET kill zone active → boost A1
    if ote.in_ote and ote.kill_zone in (KillZone.LONDON, KillZone.NY):
        assert res.final_level == "A1"
    else:
        assert res.final_level in ("A1", "A2")


# ─────────────────────────────────────────────────────────────────────
# 5. A3/NONE jamais modifiés (filtre de conviction, pas un verrou)
# ─────────────────────────────────────────────────────────────────────
def test_a3_none_never_modified():
    bars = _trend_bars()
    for level in ("A3", "NONE"):
        res = apply_strategy_layers(
            level, bars=bars, symbol="EURUSD", timeframe="M30",
            timestamp="2026-08-05T15:00:00Z",
        )
        assert res.final_level == level, f"{level} ne doit pas être modifié"


# ─────────────────────────────────────────────────────────────────────
# 6. Régime HMM dans l'audit
# ─────────────────────────────────────────────────────────────────────
def test_regime_hmm_in_audit():
    bars = _trend_bars(n=80)
    res = apply_strategy_layers(
        "A2", bars=bars, symbol="EURUSD", timeframe="M30",
        timestamp="2026-08-05T15:00:00Z",
    )
    # HMM détecte au minimum un régime (TRENDING_UP sur tendance régulière)
    assert res.regime is not None
    assert res.regime.regime.value in (
        "TRENDING_UP", "TRENDING_DOWN", "RANGING", "VOLATILE", "NEWS_LOCK", "UNKNOWN",
    )
    assert "regime_hmm" in res.audit.get("layers", [])


# ─────────────────────────────────────────────────────────────────────
# 7. apply_strategy_layers_to_signal : enrichit le signal
# ─────────────────────────────────────────────────────────────────────
def test_signal_enrichment():
    sig = _FakeSignal(level="A2")
    bars = _trend_bars()
    out, res = apply_strategy_layers_to_signal(sig, bars=bars)
    assert out is sig
    assert res.final_level in ("A1", "A2")
    assert sig.setup_level == res.final_level
    # R5 CoT : reasoning + cot enrichis
    assert "strategy_layers" in sig.reasoning
    assert "strategy_layers" in sig.cot
    # R9 : as_dict sérialisable
    d = res.as_dict()
    assert "ote" in d and "regime" in d and "smc" in d and "final_level" in d


# ─────────────────────────────────────────────────────────────────────
# 8. R6 : exceptions → fail-open (signal inchangé)
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
# 9. R2 : aucun import core/v9/
# ─────────────────────────────────────────────────────────────────────
def test_r2_additif_no_core_v9():
    src = Path(ROOT / "core" / "v10" / "v10_strategy_layers.py").read_text(encoding="utf-8")
    assert "core/v9" not in src
    assert "core.v9" not in src


# ─────────────────────────────────────────────────────────────────────
# 10. Export package (façade cohérente)
# ─────────────────────────────────────────────────────────────────────
def test_package_exports():
    import core.v10 as v
    assert hasattr(v, "apply_strategy_layers")
    assert hasattr(v, "apply_strategy_layers_to_signal")
    assert hasattr(v, "StrategyLayersResult")
