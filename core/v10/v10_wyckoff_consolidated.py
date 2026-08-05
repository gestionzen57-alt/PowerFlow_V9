"""V10 Wyckoff Consolidated — lecture unique VSA × compression/extension (Sprint 4).

Consolide les lectures Wyckoff déjà implémentées dans V10 en une seule
lecture directionnelle (additif R2, consomme `v10_vsa` + `v10_compression_extension`
sans les modifier).

Sortie : un état Wyckoff directionnel unique par (session × TF) :
  - MARKUP / MARKDOWN     (tendance directionnelle)
  - ACCUMULATION          (range étroit + volume → absorption haussière)
  - DISTRIBUTION          (range étroit + volume → distribution baissière)
  - NEUTRAL               (pas de signal, R6)

Composants consommés :
  - `v10_vsa.compute_vsa` → VSAEngineState (état VSA par bougie).
  - `v10_compression_extension.compute_vsa_signal` → VSASignalReport
    (signal multi-TF M30/H1/H4).

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7 tests verts, R9 audit,
R10 zéro ordre réel.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class WyckoffState(str, Enum):
    MARKUP = "MARKUP"
    MARKDOWN = "MARKDOWN"
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    NEUTRAL = "NEUTRAL"

    def bias(self) -> int:
        return {
            WyckoffState.MARKUP: +1,
            WyckoffState.ACCUMULATION: +1,
            WyckoffState.MARKDOWN: -1,
            WyckoffState.DISTRIBUTION: -1,
            WyckoffState.NEUTRAL: 0,
        }[self]


@dataclass
class WyckoffConsolidated:
    symbol: str = ""
    timeframe: str = ""
    timestamp: str = ""
    state: WyckoffState = WyckoffState.NEUTRAL
    confidence: float = 0.0  # [0,1]
    sources: Dict = field(default_factory=dict)  # {source: {state, confidence}}
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "state": self.state.value,
            "confidence": round(self.confidence, 3),
            "sources": dict(self.sources),
            "audit": dict(self.audit),
        }


def _vsa_bias(state_val) -> int:
    """bias d'un VSAState (enum ou string)."""
    if state_val is None:
        return 0
    name = state_val.value if hasattr(state_val, "value") else str(state_val)
    return {
        "MARKUP": +1, "ACCUMULATION": +1,
        "MARKDOWN": -1, "DISTRIBUTION": -1,
        "NEUTRAL": 0, "NEUTRE": 0,
    }.get(name.upper(), 0)


def consolidate_wyckoff(
    symbol: str,
    timeframe: str,
    timestamp: str,
    *,
    vsa_state: Optional[object] = None,        # VSAEngineState ou state brut
    vsa_confidence: float = 0.0,
    ce_signal: Optional[object] = None,        # VSASignalReport
    weights: Optional[Dict[str, float]] = None,  # {"vsa": 0.5, "ce": 0.5}
) -> WyckoffConsolidated:
    """Consolide VSA + compression-extension en un état Wyckoff unique.

    R6 fail-open : sources absentes → NEUTRAL, conf 0.0.
    """
    w = dict(weights or {"vsa": 0.5, "ce": 0.5})
    res = WyckoffConsolidated(
        symbol=symbol, timeframe=timeframe, timestamp=timestamp)
    res.audit = {"weights": dict(w)}

    bias_scores: List[float] = []
    sources = {}

    # 1. VSA (par bougie)
    if vsa_state is not None:
        v_state = getattr(vsa_state, "state", vsa_state)
        v_bias = _vsa_bias(v_state)
        v_conf = vsa_confidence
        if v_bias != 0 or v_conf > 0:
            bias_scores.append(w["vsa"] * v_bias)
        sources["vsa"] = {
            "state": _name_of(v_state),
            "bias": v_bias,
            "confidence": round(v_conf, 3),
        }

    # 2. Compression-extension (signal multi-TF)
    if ce_signal is not None:
        ce_bias = 0
        ce_conf = 0.0
        # VSASignalReport porte signal ∈ {BULLISH, BEARISH, NEUTRAL}
        sig = getattr(ce_signal, "signal", None)
        sig_name = sig.value if hasattr(sig, "value") else str(sig)
        if sig_name in ("BULLISH", "MARKUP"):
            ce_bias = +1
            ce_conf = 0.8
        elif sig_name in ("BEARISH", "MARKDOWN"):
            ce_bias = -1
            ce_conf = 0.8
        if ce_bias != 0:
            bias_scores.append(w["ce"] * ce_bias)
        sources["ce"] = {"state": sig_name, "bias": ce_bias,
                         "confidence": ce_conf}

    res.sources = sources

    if not bias_scores:
        res.audit["reason"] = "no_signal"
        return res

    total_bias = sum(bias_scores)
    res.audit["total_bias"] = round(total_bias, 3)

    if total_bias >= 0.4:
        res.state = WyckoffState.MARKUP
    elif total_bias <= -0.4:
        res.state = WyckoffState.MARKDOWN
    elif total_bias >= 0.2:
        res.state = WyckoffState.ACCUMULATION
    elif total_bias <= -0.2:
        res.state = WyckoffState.DISTRIBUTION
    else:
        res.state = WyckoffState.NEUTRAL

    res.confidence = round(min(1.0, abs(total_bias)), 3)
    res.audit["reason"] = "ok"
    return res


def _name_of(state_val) -> str:
    if state_val is None:
        return "NEUTRAL"
    return state_val.value if hasattr(state_val, "value") else str(state_val)


__all__ = [
    "WyckoffState",
    "WyckoffConsolidated",
    "consolidate_wyckoff",
]
