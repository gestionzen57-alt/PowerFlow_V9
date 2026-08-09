"""
v10_regime_switcher.py — CYCLE 12 : Regime Switcher

C12-OPT3 : Détecte le régime de marché en temps réel
            (trending / ranging / volatile / crisis) via ADX + ATR + spread.

Doctrine : R2 additif pur | R6 fail-open | R9 audit
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any


# ── Seuils ────────────────────────────────────────────────────────────────────
ADX_TRENDING: float = 25.0
ADX_STRONG_TREND: float = 40.0
ATR_VOLATILE_MULT: float = 2.0    # ATR > 2x moyenne => volatile
SPREAD_CRISIS_MULT: float = 3.0   # Spread > 3x normale => crise

REGIME_PRIORITY = ["crisis", "volatile", "trending", "ranging"]


@dataclass
class RegimeResult:
    regime: str = "unknown"
    adx: float = 0.0
    atr_ratio: float = 1.0
    spread_ratio: float = 1.0
    confidence: float = 0.0
    signals: list = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime,
            "adx": self.adx,
            "atr_ratio": self.atr_ratio,
            "spread_ratio": self.spread_ratio,
            "confidence": self.confidence,
            "signals": self.signals,
        }


def detect_regime(
    adx: float = 0.0,
    atr: float = 0.0,
    atr_baseline: float = 0.0,
    spread: float = 0.0,
    spread_baseline: float = 0.0,
) -> RegimeResult:
    """
    Détecte le régime de marché courant.

    Returns:
        RegimeResult avec régime : 'trending' | 'ranging' | 'volatile' | 'crisis'
    """
    result = RegimeResult(adx=adx)
    try:
        votes: dict[str, float] = {r: 0.0 for r in REGIME_PRIORITY}

        # ATR ratio
        if atr_baseline > 0:
            result.atr_ratio = atr / atr_baseline
        if result.atr_ratio > ATR_VOLATILE_MULT:
            votes["volatile"] += 2.0
            result.signals.append(f"ATR_HIGH={result.atr_ratio:.2f}x")

        # Spread ratio
        if spread_baseline > 0:
            result.spread_ratio = spread / spread_baseline
        if result.spread_ratio > SPREAD_CRISIS_MULT:
            votes["crisis"] += 3.0
            result.signals.append(f"SPREAD_CRISIS={result.spread_ratio:.2f}x")

        # ADX
        if adx >= ADX_STRONG_TREND:
            votes["trending"] += 3.0
            result.signals.append(f"ADX_STRONG={adx:.1f}")
        elif adx >= ADX_TRENDING:
            votes["trending"] += 1.5
            result.signals.append(f"ADX_TREND={adx:.1f}")
        else:
            votes["ranging"] += 1.5
            result.signals.append(f"ADX_RANGE={adx:.1f}")

        # Régime dominant par priorité
        for regime in REGIME_PRIORITY:
            if votes[regime] > 0:
                result.regime = regime
                result.confidence = round(votes[regime] / sum(votes.values()), 3) if sum(votes.values()) > 0 else 0.5
                break
        else:
            result.regime = "ranging"
            result.confidence = 0.5

    except Exception as e:  # R6 fail-open
        warnings.warn(f"[C12] RegimeSwitcher error (fail-open): {e}")
        result.regime = "unknown"

    return result
