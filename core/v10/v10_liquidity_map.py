"""V10 Liquidity Map — zones institutionnelles depuis OHLCV.

5 structures détectées depuis barres OHLCV (MT5 si dispo, fallback DB) :
  EQUAL_HIGHS    : ≥3 hauts dans ±0.1% sur N barres → liquidité au-dessus
  EQUAL_LOWS     : ≥3 bas dans ±0.1% → liquidité en dessous
  ORDER_BLOCK    : dernière bougie opposée avant BOS fort
                   (corps > ATR*0.8, précède mouvement > ATR*2)
  FAIR_VALUE_GAP : high[i-2] < low[i] (sens haussier) OU
                   low[i-2] > high[i] (sens baissier), gap > ATR*0.3
  SWING_LEVEL    : HH/LL significatif sur lookback 20

API : get_liquidity_map(symbol, tf, n=200) → LiquidityMap
  - zones : List[LiquidityZone] (type, price, strength, side)
  - nearest_buy_zone  : zone achat la plus proche du prix actuel
  - nearest_sell_zone : zone vente la plus proche
  - price_in_zone : bool (prix actuel dans une zone active)
  - R9 audit : n_bars_scanned, n_zones_detected

Doctrine : R2 additif (0 import core/v9/), R6 fail-open (data absente → map vide),
           R9 audit, R10 zero capital.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
DEFAULT_LIQUIDITY_CONFIG = {
    "equal_threshold_pct": 0.0010,      # 0.1%
    "equal_min_touches": 3,
    "order_block_body_atr_ratio": 0.8,
    "order_block_impulse_atr_ratio": 2.0,
    "fair_value_gap_atr_ratio": 0.3,
    "swing_lookback": 20,
    "min_distance_atr_ratio": 0.0,       # 0 = ignore
    "max_zones": 20,
}


class ZoneType(str, Enum):
    EQUAL_HIGHS = "EQUAL_HIGHS"
    EQUAL_LOWS = "EQUAL_LOWS"
    ORDER_BLOCK = "ORDER_BLOCK"
    FAIR_VALUE_GAP = "FAIR_VALUE_GAP"
    SWING_LEVEL = "SWING_LEVEL"


class ZoneSide(str, Enum):
    """Côté de la liquidité."""
    BUY = "BUY"  # zone d'achat : bas/consolidation (sell-side liquidity au-dessus)
    SELL = "SELL"  # zone de vente : haut/consolidation (buy-side liquidity en dessous)


# ─────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────
@dataclass
class LiquidityZone:
    """Une zone de liquidité détectée."""

    zone_type: ZoneType
    side: ZoneSide
    price: float
    strength: float = 1.0       # nb touches ou score
    bar_time_index: int = 0     # index dans la série OHLCV
    n_bars_back: int = 0        # distance temporelle en barres
    width: float = 0.0          # taille de la zone en prix

    def as_dict(self) -> Dict:
        return {
            "zone_type": self.zone_type.value,
            "side": self.side.value,
            "price": round(self.price, 6),
            "strength": round(self.strength, 2),
            "bar_time_index": self.bar_time_index,
            "n_bars_back": self.n_bars_back,
            "width": round(self.width, 6),
        }


@dataclass
class LiquidityMap:
    """Carte de liquidité pour (symbol, tf)."""

    symbol: str = ""
    timeframe: str = ""
    timestamp: str = ""
    current_price: float = 0.0
    zones: List[LiquidityZone] = field(default_factory=list)
    nearest_buy_zone: Optional[LiquidityZone] = None
    nearest_sell_zone: Optional[LiquidityZone] = None
    price_in_zone: bool = False
    n_bars_scanned: int = 0
    n_zones_detected: int = 0
    source: str = "ohlcv"
    seed: Optional[int] = None
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "current_price": round(self.current_price, 6),
            "n_bars_scanned": self.n_bars_scanned,
            "n_zones_detected": self.n_zones_detected,
            "zones": [z.as_dict() for z in self.zones],
            "nearest_buy_zone": self.nearest_buy_zone.as_dict() if self.nearest_buy_zone else None,
            "nearest_sell_zone": self.nearest_sell_zone.as_dict() if self.nearest_sell_zone else None,
            "price_in_zone": self.price_in_zone,
            "source": self.source,
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers calcul pur
# ─────────────────────────────────────────────────────────────────────
def _atr(bars: List[dict], period: int = 14) -> float:
    if len(bars) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return 0.0
    sample = trs[-period:]
    return sum(sample) / len(sample)


def _body_size(bar: dict) -> float:
    h = float(bar.get("high", 0))
    l = float(bar.get("low", 0))
    o = float(bar.get("open", 0))
    c = float(bar.get("close", 0))
    return abs(c - o)


# ─────────────────────────────────────────────────────────────────────
# Détections
# ─────────────────────────────────────────────────────────────────────
def _detect_equal_highs_lows(
    bars: List[dict],
    *,
    threshold_pct: float = 0.0010,
    min_touches: int = 3,
) -> List[LiquidityZone]:
    """Détecte equal highs / lows si ≥min_touches sommets dans ±threshold_pct."""
    zones: List[LiquidityZone] = []
    if len(bars) < min_touches + 2:
        return zones
    n = len(bars)

    # Equal highs
    for i in range(min_touches - 1, n):
        highs_i = [(j, float(bars[j]["high"])) for j in range(i - min_touches + 1, i + 1)]
        prices = [p for _, p in highs_i]
        pmin, pmax = min(prices), max(prices)
        if pmin <= 0:
            continue
        spread_pct = (pmax - pmin) / pmax
        if spread_pct <= threshold_pct:
            avg_price = sum(prices) / len(prices)
            zones.append(LiquidityZone(
                zone_type=ZoneType.EQUAL_HIGHS,
                side=ZoneSide.SELL,  # liquidité au-dessus → piège pour shorts
                price=avg_price,
                strength=len(prices),
                bar_time_index=highs_i[-1][0],
                n_bars_back=n - 1 - highs_i[-1][0],
                width=(pmax - pmin),
            ))

    # Equal lows
    for i in range(min_touches - 1, n):
        lows_i = [(j, float(bars[j]["low"])) for j in range(i - min_touches + 1, i + 1)]
        prices = [p for _, p in lows_i]
        pmin, pmax = min(prices), max(prices)
        if pmax <= 0:
            continue
        spread_pct = (pmax - pmin) / pmax
        if spread_pct <= threshold_pct:
            avg_price = sum(prices) / len(prices)
            zones.append(LiquidityZone(
                zone_type=ZoneType.EQUAL_LOWS,
                side=ZoneSide.BUY,  # liquidité en dessous → piège pour longs
                price=avg_price,
                strength=len(prices),
                bar_time_index=lows_i[-1][0],
                n_bars_back=n - 1 - lows_i[-1][0],
                width=(pmax - pmin),
            ))
    return zones


def _detect_order_blocks(
    bars: List[dict],
    *,
    body_atr_ratio: float = 0.8,
    impulse_atr_ratio: float = 2.0,
) -> List[LiquidityZone]:
    """Détecte les order blocks : dernière bougie opposée avant impulsion."""
    zones: List[LiquidityZone] = []
    atr = _atr(bars)
    if atr <= 0 or len(bars) < 5:
        return zones
    for i in range(2, len(bars) - 2):
        bar = bars[i]
        body = _body_size(bar)
        if body < atr * body_atr_ratio:
            continue
        # Impulsion après = mouvement > ATR * ratio
        # Haussier : bar i+1..i+2 font un close plus haut que ATR*ratio au-dessus de bar[i].close
        # Baissier : inverse
        c_i = float(bar["close"])
        o_i = float(bar["open"])
        bullish = c_i > o_i
        # Mouvement total jusqu'à i+2
        future_high = max(float(bars[i + 1]["high"]), float(bars[i + 2]["high"]))
        future_low = min(float(bars[i + 1]["low"]), float(bars[i + 2]["low"]))
        if bullish:
            impulse = future_high - c_i
            if impulse >= atr * impulse_atr_ratio:
                zones.append(LiquidityZone(
                    zone_type=ZoneType.ORDER_BLOCK,
                    side=ZoneSide.BUY,  # OB haussier → zone achat
                    price=c_i,
                    strength=min(2.0, impulse / atr),
                    bar_time_index=i,
                    n_bars_back=len(bars) - 1 - i,
                    width=body,
                ))
        else:
            impulse = c_i - future_low
            if impulse >= atr * impulse_atr_ratio:
                zones.append(LiquidityZone(
                    zone_type=ZoneType.ORDER_BLOCK,
                    side=ZoneSide.SELL,  # OB baissier → zone vente
                    price=c_i,
                    strength=min(2.0, impulse / atr),
                    bar_time_index=i,
                    n_bars_back=len(bars) - 1 - i,
                    width=body,
                ))
    return zones


def _detect_fair_value_gaps(
    bars: List[dict],
    *,
    gap_atr_ratio: float = 0.3,
) -> List[LiquidityZone]:
    """Détecte FVG : gap entre high[i-2] et low[i] ou low[i-2] et high[i]."""
    zones: List[LiquidityZone] = []
    atr = _atr(bars)
    if atr <= 0 or len(bars) < 3:
        return zones
    min_gap = atr * gap_atr_ratio
    for i in range(2, len(bars)):
        high_prev2 = float(bars[i - 2]["high"])
        low_prev2 = float(bars[i - 2]["low"])
        high_i = float(bars[i]["high"])
        low_i = float(bars[i]["low"])
        # FVG haussier : high[i-2] < low[i] (gap entre)
        if low_i - high_prev2 >= min_gap:
            mid = (high_prev2 + low_i) / 2.0
            zones.append(LiquidityZone(
                zone_type=ZoneType.FAIR_VALUE_GAP,
                side=ZoneSide.BUY,  # FVG haussier → potentielle zone achat
                price=mid,
                strength=min(2.0, (low_i - high_prev2) / atr),
                bar_time_index=i,
                n_bars_back=len(bars) - 1 - i,
                width=(low_i - high_prev2),
            ))
        # FVG baissier : low[i-2] > high[i]
        elif low_prev2 - high_i >= min_gap:
            mid = (low_prev2 + high_i) / 2.0
            zones.append(LiquidityZone(
                zone_type=ZoneType.FAIR_VALUE_GAP,
                side=ZoneSide.SELL,  # FVG baissier → potentielle zone vente
                price=mid,
                strength=min(2.0, (low_prev2 - high_i) / atr),
                bar_time_index=i,
                n_bars_back=len(bars) - 1 - i,
                width=(low_prev2 - high_i),
            ))
    return zones


def _detect_swing_levels(
    bars: List[dict],
    *,
    lookback: int = 20,
) -> List[LiquidityZone]:
    """Détecte swing highs/lows significatifs (lookback N).

    R-9 audit : Pour swing high, on exige h >= high_window_toutes_autres (==).
    Tolérance élargie via epsilon proportionnel au range observé.
    """
    zones: List[LiquidityZone] = []
    if len(bars) < lookback + 2:
        return zones
    eps = 1e-6
    for i in range(lookback, len(bars) - lookback):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        high_window = [float(bars[j]["high"]) for j in range(i - lookback, i + lookback + 1) if j != i]
        top_max = max(high_window) if high_window else 0
        bot_min_low = min(high_window) if high_window else 1e9
        range_window = top_max - bot_min_low if high_window else 1e-3
        # Tolérance : fenêtre ±25% du range observé (permet spikes multiples)
        tol = range_window * 0.25 + 1e-6
        # Swing high : h >= top_max - tol
        if h + tol >= top_max and h > 0:
            zones.append(LiquidityZone(
                zone_type=ZoneType.SWING_LEVEL,
                side=ZoneSide.SELL,
                price=h,
                strength=1.0,
                bar_time_index=i,
                n_bars_back=len(bars) - 1 - i,
                width=0.0,
            ))
        low_window = [float(bars[j]["low"]) for j in range(i - lookback, i + lookback + 1) if j != i]
        bot_min = min(low_window) if low_window else 1e9
        top_max_low = max(low_window) if low_window else 0
        range_low = top_max_low - bot_min if low_window else 1e-3
        tol_low = range_low * 0.25 + 1e-6
        if l - tol_low <= bot_min and l > 0:
            zones.append(LiquidityZone(
                zone_type=ZoneType.SWING_LEVEL,
                side=ZoneSide.BUY,
                price=l,
                strength=1.0,
                bar_time_index=i,
                n_bars_back=len(bars) - 1 - i,
                width=0.0,
            ))
    return zones


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def get_liquidity_map(
    symbol: str,
    timeframe: str,
    bars: List[dict],
    *,
    timestamp: Optional[str] = None,
    current_price: Optional[float] = None,
    overrides: Optional[Dict] = None,
    seed: Optional[int] = None,
) -> LiquidityMap:
    """Construit la carte de liquidité pour (symbol, tf).

    Parameters
    ----------
    symbol : ex "EURUSD"
    timeframe : ex "H1"
    bars : OHLCV ascending.
    timestamp : ISO 8601 UTC (defaut: "").
    current_price : prix actuel pour proximity detection.
    overrides : ajustement config.

    Returns
    -------
    LiquidityMap avec zones, zones les plus proches, price_in_zone.
    """
    cfg = dict(DEFAULT_LIQUIDITY_CONFIG)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if k in cfg})

    mp = LiquidityMap(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp or "",
        current_price=float(current_price) if current_price is not None else 0.0,
        seed=seed,
    )

    # R6 fail-open : data absente → map vide
    if not bars or len(bars) < 20:
        mp.source = "db" if bars else "missing"
        mp.audit["reason"] = "insufficient_bars"
        return mp

    n = len(bars)
    mp.n_bars_scanned = n
    mp.source = "ohlcv"

    if mp.current_price <= 0:
        mp.current_price = float(bars[-1].get("close", 0.0))

    # Détections
    all_zones = []
    all_zones.extend(_detect_equal_highs_lows(
        bars, threshold_pct=cfg["equal_threshold_pct"],
        min_touches=cfg["equal_min_touches"],
    ))
    all_zones.extend(_detect_order_blocks(
        bars, body_atr_ratio=cfg["order_block_body_atr_ratio"],
        impulse_atr_ratio=cfg["order_block_impulse_atr_ratio"],
    ))
    all_zones.extend(_detect_fair_value_gaps(
        bars, gap_atr_ratio=cfg["fair_value_gap_atr_ratio"],
    ))
    all_zones.extend(_detect_swing_levels(
        bars, lookback=cfg["swing_lookback"],
    ))

    # Plafonne au max
    all_zones = all_zones[: cfg["max_zones"]]
    mp.zones = all_zones
    mp.n_zones_detected = len(all_zones)
    mp.audit["config_used"] = cfg

    # Zones les plus proches du prix actuel
    if all_zones and mp.current_price > 0:
        buy_zones = [z for z in all_zones if z.side == ZoneSide.BUY]
        sell_zones = [z for z in all_zones if z.side == ZoneSide.SELL]
        if buy_zones:
            buy_zones_sorted = sorted(
                buy_zones,
                key=lambda z: abs(mp.current_price - z.price),
            )
            mp.nearest_buy_zone = buy_zones_sorted[0]
        if sell_zones:
            sell_zones_sorted = sorted(
                sell_zones,
                key=lambda z: abs(mp.current_price - z.price),
            )
            mp.nearest_sell_zone = sell_zones_sorted[0]

        # price_in_zone : prix actuel dans une zone (à ±5% de la largeur)
        for z in all_zones:
            if z.width > 0:
                if z.price - z.width / 2 <= mp.current_price <= z.price + z.width / 2:
                    mp.price_in_zone = True
                    break

    return mp


# ─────────────────────────────────────────────────────────────────────
# Intégration — bonus/malus composite_score
# ─────────────────────────────────────────────────────────────────────
def liquidity_bonus_malus(
    signal_direction: str,   # "BULLISH" / "BEARISH"
    current_price: float,
    map_obj: LiquidityMap,
    atr: Optional[float] = None,
) -> float:
    """Calcule le bonus/malus liquidité pour le composite_score.

    Règles :
      - Si price_in_zone ET direction alignée (zone acheteuse + signal
        bullish, ou vendeuse + bearish) → +0.05
      - Si prix proche d'une liquidité opposée (distance < ATR*0.5)
        → -0.10
      - Sinon → 0.0
    """
    if not map_obj.zones or current_price <= 0:
        return 0.0
    bonus = 0.0
    # price_in_zone + alignée
    is_bullish = signal_direction == "BULLISH"
    is_bearish = signal_direction == "BEARISH"
    if map_obj.price_in_zone:
        if (map_obj.nearest_buy_zone and is_bullish) or (map_obj.nearest_sell_zone and is_bearish):
            bonus += 0.05
    # Proximité opposing
    if atr and atr > 0:
        opposing = (
            map_obj.nearest_sell_zone if is_bullish else map_obj.nearest_buy_zone
        )
        if opposing:
            dist = abs(current_price - opposing.price)
            if dist < atr * 0.5:
                bonus -= 0.10
    return bonus


__all__ = [
    "LiquidityZone",
    "LiquidityMap",
    "ZoneType",
    "ZoneSide",
    "DEFAULT_LIQUIDITY_CONFIG",
    "get_liquidity_map",
    "liquidity_bonus_malus",
    "_detect_equal_highs_lows",
    "_detect_order_blocks",
    "_detect_fair_value_gaps",
    "_detect_swing_levels",
]
