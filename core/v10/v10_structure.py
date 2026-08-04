"""V10 Module Structure — Couche 2 : ce que TU vois.

Détecte la structure de marché (support/résistance, trendlines, patterns,
zones, structure HH/HL, break of structure) depuis les bougies brutes.

Terminologie alignée sur la lecture TA humaine. Chaque feature S1-S9 est
testée unitairement (R7).

Features :
  S1 — Support/Résistance horizontaux (pivots hauts/bas)
  S2 — Trendline (régression linéaire sur swing points)
  S3 — Patterns chandelles (engulfing, hammer, doji)
  S4 — Order block (dernier mouvement contre cassure)
  S5 — Zones institutionnelles (clusters de prix)
  S6 — Liquidity pools (equal highs/lows)
  S7 — Structure de marché (HH/HL vs LH/LL = trend vs range)
  S8 — Break of structure (BOS) vs change of character (CHoCH)
  S9 — Premium/Discount (50% equilibrium)

Doctrine : R2 additif pur, R6 fail-open, R9 audit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULTS = {
    "pivot_lookback": 5,        # bougies de chaque côté pour pivot
    "s2_min_points": 3,         # points pour une trendline valide
    "structure_lookback": 10,   # bougies pour structure de marché
    "premium_discount_range": 20,  # lookback du range pour 50% equilibrium
}


@dataclass
class StructureResult:
    symbol: str
    timestamp: str
    timeframe: str

    s1_support: float = 0.0
    s1_resistance: float = 0.0
    s2_trend: str = "RANGE"        # UPTREND / DOWNTREND / RANGE
    s2_slope: float = 0.0
    s3_pattern: str = "NONE"       # ENGULFING_BULL/BEAR, HAMMER, SHOOTING_STAR, DOJI
    s4_order_block: str = "NONE"   # BULLISH / BEARISH / NONE
    s5_zone_proximity: str = "NONE"
    s6_liquidity: str = "NONE"
    s7_market_structure: str = "RANGE"  # UPTREND / DOWNTREND / RANGE
    s8_break: str = "NONE"         # BOS_BULL / BOS_BEAR / CHoCH / NONE
    s9_equilibrium: float = 0.5    # 0 = discount deep, 1 = premium high
    structure_type: str = "NONE"   # BREAK / REJECT / EXTENSION / RANGE

    summary: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "s1_support": round(self.s1_support, 5),
            "s1_resistance": round(self.s1_resistance, 5),
            "s2_trend": self.s2_trend,
            "s3_pattern": self.s3_pattern,
            "s4_order_block": self.s4_order_block,
            "s5_zone_proximity": self.s5_zone_proximity,
            "s6_liquidity": self.s6_liquidity,
            "s7_market_structure": self.s7_market_structure,
            "s8_break": self.s8_break,
            "s9_equilibrium": round(self.s9_equilibrium, 4),
            "structure_type": self.structure_type,
        }


def _pivot_levels(bars: List[dict], lookback: int) -> tuple:
    """Plus haut pivot haut et plus bas pivot bas sur lookback."""
    if len(bars) < lookback * 2 + 1:
        return 0.0, 0.0
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    piv_hi = max(highs[-(lookback * 2):])
    piv_lo = min(lows[-(lookback * 2):])
    return piv_hi, piv_lo


def _linear_slope(prices: List[float]) -> float:
    """Pente normalisée d'une régression linéaire sur les prix."""
    n = len(prices)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(prices) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, prices))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def _market_structure(bars: List[dict], lookback: int) -> str:
    """HH/HL = UPTREND, LH/LL = DOWNTREND, sinon RANGE."""
    closes = [float(b["close"]) for b in bars[-lookback:]]
    if len(closes) < 5:
        return "RANGE"
    slope = _linear_slope(closes)
    # HH/HL : chaque nouveau high > précédent et lows en hausse
    highs = [float(b["high"]) for b in bars[-lookback:]]
    lows = [float(b["low"]) for b in bars[-lookback:]]
    rising_highs = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i - 1])
    falling_lows = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i - 1])
    n = len(highs) - 1
    if rising_highs / n > 0.7 and falling_lows / n < 0.4:
        return "UPTREND"
    if falling_lows / n > 0.7 and rising_highs / n < 0.4:
        return "DOWNTREND"
    return "RANGE"


def _candle_pattern(cur: dict, prev: dict) -> str:
    o, c, h, l = float(cur["open"]), float(cur["close"]), float(cur["high"]), float(cur["low"])
    po, pc = float(prev["open"]), float(prev["close"])
    body = abs(c - o)
    rng = (h - l) or 1e-9
    # Engulfing
    if c > o and po > pc and o <= po and c >= pc:
        return "ENGULFING_BULL"
    if c < o and po < pc and o >= po and c <= pc:
        return "ENGULFING_BEAR"
    # Hammer / Shooting star (petit body, longue mèche)
    lower_w, upper_w = min(o, c) - l, h - max(o, c)
    if body < rng * 0.35 and lower_w > body * 2 and upper_w < body:
        return "HAMMER"
    if body < rng * 0.35 and upper_w > body * 2 and lower_w < body:
        return "SHOOTING_STAR"
    # Doji
    if body < rng * 0.1:
        return "DOJI"
    return "NONE"


def compute_structure(
    symbol: str,
    timestamp: str,
    timeframe: str,
    bars: List[dict],
    *,
    overrides: Optional[dict] = None,
) -> StructureResult:
    """Calcule les 9 features Structure pour la bougie la plus récente."""
    cfg = dict(DEFAULTS)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if k in DEFAULTS})

    res = StructureResult(symbol, timestamp, timeframe)
    if not bars:
        return res

    cur = bars[-1]
    close = float(cur["close"])

    # ---- S1 support/résistance ----
    res.s1_resistance, res.s1_support = _pivot_levels(bars, int(cfg["pivot_lookback"]))

    # ---- S2 trendline / S7 market structure ----
    closes = [float(b["close"]) for b in bars]
    slope = _linear_slope(closes[-int(cfg["structure_lookback"]):])
    res.s2_slope = slope
    if slope > 0:
        res.s2_trend = "UPTREND" if abs(slope) / (closes[-1] or 1) > 1e-5 else "RANGE"
    elif slope < 0:
        res.s2_trend = "DOWNTREND" if abs(slope) / (closes[-1] or 1) > 1e-5 else "RANGE"
    else:
        res.s2_trend = "RANGE"
    res.s7_market_structure = _market_structure(bars, int(cfg["structure_lookback"]))

    # ---- S3 pattern ----
    if len(bars) >= 2:
        res.s3_pattern = _candle_pattern(bars[-1], bars[-2])

    # ---- S4 order block ----
    # Dernier mouvement contre une cassure récente (simple heuristique)
    if len(bars) >= 3:
        prev1, prev2 = float(bars[-2]["close"]), float(bars[-3]["close"])
        if prev1 < prev2 and close > prev1:
            res.s4_order_block = "BULLISH"
        elif prev1 > prev2 and close < prev1:
            res.s4_order_block = "BEARISH"

    # ---- S5 zone proximité (à <0.5 ATR d'un pivot) ----
    if res.s1_resistance > 0:
        zone = res.s1_resistance - close
        atr = res.s1_resistance - res.s1_support or 1e-9
        if abs(zone) / atr < 0.05:
            res.s5_zone_proximity = "AT_RESISTANCE"
        elif close - res.s1_support > 0 and (close - res.s1_support) / atr < 0.05:
            res.s5_zone_proximity = "AT_SUPPORT"

    # ---- S6 liquidity (equal highs/lows = stop hunts) ----
    highs = [float(b["high"]) for b in bars[-6:]]
    lows = [float(b["low"]) for b in bars[-6:]]
    if len(highs) >= 3 and highs.count(max(highs)) >= 2:
        res.s6_liquidity = "EQUAL_HIGHS"
    if len(lows) >= 3 and lows.count(min(lows)) >= 2:
        res.s6_liquidity = "EQUAL_LOWS"

    # ---- S8 break of structure ----
    if len(bars) >= int(cfg["pivot_lookback"]) * 2:
        hi, lo = _pivot_levels(bars, int(cfg["pivot_lookback"]))
        if close > hi:
            res.s8_break = "BOS_BULL"
        elif close < lo:
            res.s8_break = "BOS_BEAR"
        elif res.s7_market_structure != "RANGE":
            res.s8_break = "CHoCH"

    # ---- S9 premium/discount (position dans le range récent) ----
    rng_hi, rng_lo = _pivot_levels(bars, int(cfg["premium_discount_range"]))
    if rng_hi > rng_lo:
        res.s9_equilibrium = (close - rng_lo) / (rng_hi - rng_lo)

    # ---- Structure type ----
    if res.s8_break in ("BOS_BULL", "BOS_BEAR"):
        res.structure_type = "BREAK"
    elif res.s5_zone_proximity in ("AT_RESISTANCE", "AT_SUPPORT") or res.s3_pattern in (
        "ENGULFING_BULL", "ENGULFING_BEAR", "HAMMER", "SHOOTING_STAR"
    ):
        res.structure_type = "REJECT"
    elif res.s7_market_structure != "RANGE":
        res.structure_type = "EXTENSION"
    else:
        res.structure_type = "RANGE"

    res.summary = {"structure_type": res.structure_type, "trend": res.s2_trend}
    return res
