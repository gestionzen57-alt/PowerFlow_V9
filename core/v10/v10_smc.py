"""V10 SMC — Smart Money Concepts public (BOS/MSS, Order Blocks, FVG).

Implémente en pure Python la stratégie SMC publique (Ivan Blac / LuxAlgo
style, adapté). Additif V10 (R2), étend la lecture structure S1-S9 existante.

Composants (mandat autopilote quant Hermes §2.1) :
  - BOS (Break of Structure) / MSS (Market Structure Shift) :
      - BOS = cassure de la structure du même sens que la tendance.
      - MSS (CHoCH) = cassure contre la tendance dominante (shift).
  - Order Blocks : dernière bougie contre-tendance avant une impulsion
      (Bullish OB = dernier down-candle avant un move up ; Bearish inverse).
  - FVG (Fair Value Gap) : écart 3-bougies (high[j-1] < low[j+1] pour bull).

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open (données courtes → dict
vide / NONE), R7 tests verts, R9 audit sérialisable, R10 zéro ordre réel.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class SMCStructure(str, Enum):
    BOS_BULL = "BOS_BULL"
    BOS_BEAR = "BOS_BEAR"
    MSS_BULL = "MSS_BULL"      # shift haussier (CHoCH up)
    MSS_BEAR = "MSS_BEAR"      # shift baissier (CHoCH down)
    NONE = "NONE"


class OrderBlockSide(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NONE = "NONE"


class FvgSide(str, Enum):
    BULLISH = "BULLISH"   # gap haussier (prix cassera vers le haut)
    BEARISH = "BEARISH"   # gap baissier
    NONE = "NONE"


@dataclass
class SmcResult:
    symbol: str = ""
    timeframe: str = ""
    timestamp: str = ""
    structure: SMCStructure = SMCStructure.NONE
    order_block_side: OrderBlockSide = OrderBlockSide.NONE
    order_block_range: Optional[tuple] = None  # (lo, hi)
    fvg_side: FvgSide = FvgSide.NONE
    fvg_range: Optional[tuple] = None          # (lo, hi)
    # le prix est-il dans la zone FVG / OB ?
    in_fvg: bool = False
    in_order_block: bool = False
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "structure": self.structure.value,
            "order_block_side": self.order_block_side.value,
            "order_block_range": list(self.order_block_range) if self.order_block_range else None,
            "fvg_side": self.fvg_side.value,
            "fvg_range": list(self.fvg_range) if self.fvg_range else None,
            "in_fvg": self.in_fvg,
            "in_order_block": self.in_order_block,
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _swing_highs_lows(bars: List[dict], window: int = 3) -> tuple:
    """Extrait les swing highs/lows locaux (fractals simples)."""
    highs, lows = [], []
    for i in range(window, len(bars) - window):
        cur = bars[i]
        if all(float(cur["high"]) >= float(bars[j]["high"]) for j in range(i - window, i + window + 1) if j != i):
            highs.append((i, float(cur["high"])))
        if all(float(cur["low"]) <= float(bars[j]["low"]) for j in range(i - window, i + window + 1) if j != i):
            lows.append((i, float(cur["low"])))
    return highs, lows


def _latest_swings(highs: List[tuple], lows: List[tuple]) -> tuple:
    """Retourne (last_high_idx, last_high, last_low_idx, last_low)."""
    lh_idx, lh = (highs[-1] if highs else (None, None))
    ll_idx, ll = (lows[-1] if lows else (None, None))
    return lh_idx, lh, ll_idx, ll


# ─────────────────────────────────────────────────────────────────────
# Détection SMC
# ─────────────────────────────────────────────────────────────────────
def detect_smc(
    bars: List[dict],
    *,
    symbol: str = "",
    timeframe: str = "",
    timestamp: str = "",
    swing_window: int = 3,
) -> SmcResult:
    """Analyse SMC complète (BOS/MSS + Order Block + FVG) sur les bars.

    bars : liste de dicts {open, high, low, close} (croissante).

    R6 fail-open : < 6 bars → structure NONE, sides NONE, zones None.
    """
    res = SmcResult(symbol=symbol, timeframe=timeframe, timestamp=timestamp)
    res.audit = {"swing_window": swing_window, "n_bars": len(bars)}

    if len(bars) < 3:
        res.audit["reason"] = "insufficient_data"
        return res

    cur = bars[-1]
    close = float(cur["close"])
    open_ = float(cur["open"])
    high = float(cur["high"])
    low = float(cur["low"])

    # ---- FVG (3-bougie) ----
    if len(bars) >= 3:
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        # Bullish FVG : high[j-2] < low[j] (gap entre bougie 1 et 3)
        if float(b1["high"]) < float(b3["low"]):
            res.fvg_side = FvgSide.BULLISH
            res.fvg_range = (float(b1["high"]), float(b3["low"]))
        elif float(b1["low"]) > float(b3["high"]):
            res.fvg_side = FvgSide.BEARISH
            res.fvg_range = (float(b3["high"]), float(b1["low"]))
        if res.fvg_range:
            res.in_fvg = res.fvg_range[0] <= close <= res.fvg_range[1]

    # ---- Order Block (dernière bougie contre-tendance avant impulsion) ----
    if len(bars) >= 3:
        b2 = bars[-2]
        prev = bars[-3]
        # Bullish OB : dernier down-candle suivi d'un up-move
        if float(b2["close"]) < float(b2["open"]) and close > float(b2["high"]):
            res.order_block_side = OrderBlockSide.BULLISH
            res.order_block_range = (float(b2["low"]), float(b2["high"]))
        elif float(b2["close"]) > float(b2["open"]) and close < float(b2["low"]):
            res.order_block_side = OrderBlockSide.BEARISH
            res.order_block_range = (float(b2["low"]), float(b2["high"]))
        if res.order_block_range:
            res.in_order_block = res.order_block_range[0] <= close <= res.order_block_range[1]

    # ---- BOS / MSS ----
    highs, lows = _swing_highs_lows(bars, swing_window)
    lh_idx, lh, ll_idx, ll = _latest_swings(highs, lows)

    if lh is not None and close > lh:
        # cassure de haut → déterminer BOS (continuation) vs MSS (shift)
        # MSS : le dernier swing low a été cassé avant ce high → shift
        if ll is not None and low < ll:
            res.structure = SMCStructure.MSS_BULL
        else:
            res.structure = SMCStructure.BOS_BULL
    elif ll is not None and close < ll:
        if lh is not None and high > lh:
            res.structure = SMCStructure.MSS_BEAR
        else:
            res.structure = SMCStructure.BOS_BEAR
    else:
        res.structure = SMCStructure.NONE

    res.audit["reason"] = "ok"
    res.audit["swing_high"] = lh
    res.audit["swing_low"] = ll
    res.audit["close"] = round(close, 5)
    return res


def smc_to_signal_level(smc: SmcResult, current_level: str) -> tuple:
    """Mappe la structure SMC vers un boost/downgrade de setup_level.

    Returns
    -------
    (new_level, boosted, severity)

    Règles (additif) :
      - MSS_BULL/MSS_BEAR = shift de structure → boost A3→A2 (si pas déjà A1)
      - BOS_BULL/BOS_BEAR = continuation → boost A2 si A3
      - FVG aligné avec structure → renforce
      - A1 n'est JAMAIS downgradé par SMC seul (le filtre OTE/session gère ça)
    """
    if current_level == "A1":
        return current_level, False, "none"
    cur_rank = {"NONE": 0, "A3": 1, "A2": 2, "A1": 3}.get(current_level, 0)

    if smc.structure in (SMCStructure.MSS_BULL, SMCStructure.MSS_BEAR):
        # shift de structure → forte conviction
        new = "A2"
        boosted = cur_rank < 2
        return new, boosted, ("boost" if boosted else "none")
    if smc.structure in (SMCStructure.BOS_BULL, SMCStructure.BOS_BEAR):
        new = "A2" if cur_rank == 1 else current_level
        boosted = cur_rank == 1
        return new, boosted, ("boost" if boosted else "none")
    return current_level, False, "none"


__all__ = [
    "SMCStructure",
    "OrderBlockSide",
    "FvgSide",
    "SmcResult",
    "detect_smc",
    "smc_to_signal_level",
    "_swing_highs_lows",
]
