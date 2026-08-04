"""V10 Delta Flow — analyse delta volume (buy vs sell ticks) et absorption.

Calculs depuis MT5 ticks si dispo, sinon proxy via tick_volume.

Calculs :
  - delta_bar      = volume_buy_ticks - volume_sell_ticks par barre
  - delta_cum(N)   = somme sur N barres glissantes (5, 20)
  - absorption     = volume fort (>VSA_SMA*1.5) + petit mouvement
                     (<ATR*0.3) → absorption détectée
  - imbalance      = delta / total_volume ∈ [-1, +1]
  - stacked_imb    : 3 barres consécutives même signe imbalance > 0.6

API : compute_delta(symbol, tf, n=50, bars) → DeltaState
  - delta_last, delta_cum_5, delta_cum_20
  - imbalance_ratio, absorption_detected, stacked_imbalance
  - direction_delta : BUY / SELL / NEUTRAL (seuil ±0.3)
  - source : 'mt5_ticks' / 'tick_volume_proxy'

Doctrine : R2 additif (0 import core/v9/), R6 fail-open, R9 audit, R10.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
DEFAULT_DELTA_CONFIG = {
    "absorption_volume_mult": 1.5,    # volume > VSA_SMA * mult
    "absorption_movement_atr_mult": 0.3,
    "stacked_min_consecutive": 3,
    "stacked_imbalance_min": 0.6,
    "direction_threshold": 0.30,
}


class DeltaDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class DeltaSource(str, Enum):
    MT5_TICKS = "mt5_ticks"
    TICK_VOLUME_PROXY = "tick_volume_proxy"
    MISSING = "missing"


# ─────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────
@dataclass
class DeltaState:
    symbol: str = ""
    timeframe: str = ""
    timestamp: str = ""

    delta_last: float = 0.0
    delta_cum_5: float = 0.0
    delta_cum_20: float = 0.0

    imbalance_ratio: float = 0.0
    absorption_detected: bool = False
    stacked_imbalance: bool = False

    direction_delta: DeltaDirection = DeltaDirection.UNKNOWN
    source: DeltaSource = DeltaSource.MISSING

    n_bars_used: int = 0
    n_ticks_used: int = 0
    seed: Optional[int] = None
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "delta_last": round(self.delta_last, 4),
            "delta_cum_5": round(self.delta_cum_5, 4),
            "delta_cum_20": round(self.delta_cum_20, 4),
            "imbalance_ratio": round(self.imbalance_ratio, 4),
            "absorption_detected": self.absorption_detected,
            "stacked_imbalance": self.stacked_imbalance,
            "direction_delta": self.direction_delta.value,
            "source": self.source.value,
            "audit": {
                "n_bars_used": self.n_bars_used,
                "n_ticks_used": self.n_ticks_used,
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers de calcul pur
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
    s = trs[-period:]
    return sum(s) / len(s)


def _body_size(bar: dict) -> float:
    h = float(bar.get("high", 0))
    l = float(bar.get("low", 0))
    o = float(bar.get("open", 0))
    c = float(bar.get("close", 0))
    return abs(c - o)


def _sma(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return 0.0
    s = values[-period:]
    return sum(s) / len(s) if s else 0.0


# ─────────────────────────────────────────────────────────────────────
# Proxy split buy/sell depuis tick_volume
# ─────────────────────────────────────────────────────────────────────
def _split_buy_sell_proxy(bar: dict, prev_bar: Optional[dict]) -> Tuple[float, float]:
    """Split buy/sell ticks à partir d'un bar OHLCV.

    Heuristique simple : si close > open → majorité buy, sinon majorité sell.
    Proportion = abs(close-open) / (high-low), bornée 0.5..1.0.
    Returns (buy_volume, sell_volume).
    """
    h = float(bar.get("high", 0))
    l = float(bar.get("low", 0))
    o = float(bar.get("open", 0))
    c = float(bar.get("close", 0))
    total = float(bar.get("tick_volume", 0))
    if total <= 0 or h <= 0 or l <= 0 or h == l:
        # Fallback : 50/50
        return total * 0.5, total * 0.5
    is_bullish = c >= o
    # body_ratio ∈ [0, 1] : à quel point le corps couvre le range total
    body_ratio = abs(c - o) / (h - l) if h > l else 0.5
    # Borne sécurité pour pathologiques
    body_ratio = max(0.0, min(1.0, body_ratio))
    # Si bullish : buy_ratio = 0.5 + body_ratio/2 (entre 0.5 et 1.0)
    #   Si bearish : sell_ratio = 0.5 + body_ratio/2
    dominant_ratio = 0.5 + body_ratio * 0.5
    if is_bullish:
        buy_v = total * dominant_ratio
        sell_v = total * (1.0 - dominant_ratio)
    else:
        sell_v = total * dominant_ratio
        buy_v = total * (1.0 - dominant_ratio)
    return buy_v, sell_v


# ─────────────────────────────────────────────────────────────────────
# MT5 ticks (lazy)
# ─────────────────────────────────────────────────────────────────────
def _try_mt5_ticks(symbol: str, n_ticks: int = 5000) -> Optional[List[dict]]:
    """Lecture ticks MT5 si dispo. R6 fail-open → None."""
    try:
        from .v10_mt5_bridge import is_mt5_available, initialize as mt5_init, shutdown as mt5_shutdown
        if not is_mt5_available():
            return None
        if not mt5_init(auto=True):
            return None
        try:
            import MetaTrader5 as mt5  # type: ignore
            from datetime import datetime, timezone, timedelta
            to_dt = datetime.now(timezone.utc)
            from_dt = to_dt - timedelta(hours=1)
            ticks = mt5.copy_ticks_from(symbol, from_dt, n_ticks, mt5.COPY_TICKS_ALL)
            return list(ticks) if ticks else []
        finally:
            try:
                mt5_shutdown()
            except Exception:
                pass
    except (ImportError, Exception) as e:
        log.debug(f"_try_mt5_ticks fallback: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────
# Calcul delta cumulé depuis ticks
# ─────────────────────────────────────────────────────────────────────
def _delta_from_ticks(ticks: List[dict]) -> List[float]:
    """Agrège les ticks en delta cumulé par seconde (proxy bar)."""
    if not ticks:
        return []
    # tick['flags'] & 0x02 (FLAG_TICK_BUY) → buy, sinon sell
    buckets: Dict[int, Tuple[float, float]] = {}
    for tk in ticks:
        sec = int(getattr(tk, "time", 0))
        flags = int(getattr(tk, "flags", 0))
        vol = float(getattr(tk, "volume", 0)) or 1.0
        is_buy = bool(flags & 0x02)
        b, s = buckets.get(sec, (0.0, 0.0))
        if is_buy:
            b += vol
        else:
            s += vol
        buckets[sec] = (b, s)
    # Deltas par timestamp croissant
    deltas = [b - s for _, (b, s) in sorted(buckets.items())]
    return deltas


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def compute_delta(
    symbol: str,
    timeframe: str,
    bars: List[dict],
    *,
    timestamp: Optional[str] = None,
    overrides: Optional[Dict] = None,
    seed: Optional[int] = None,
) -> DeltaState:
    """Calcule delta, imbalance, absorption pour (symbol, tf, bars).

    Parameters
    ----------
    symbol : ex "EURUSD"
    timeframe : ex "M15"
    bars : OHLCV.
    timestamp : ISO 8601 UTC.

    Returns
    -------
    DeltaState avec tous les indicateurs + audit.
    """
    cfg = dict(DEFAULT_DELTA_CONFIG)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if k in cfg})

    st = DeltaState(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp or "",
        seed=seed,
    )

    # R6 fail-open : pas de bars → MISSING
    if not bars or len(bars) < 5:
        st.source = DeltaSource.MISSING
        st.audit["reason"] = "insufficient_bars"
        return st

    n_bars = min(50, len(bars))
    bars_window = bars[-n_bars:]
    st.n_bars_used = len(bars_window)

    # 1. Tente MT5 ticks
    ticks = _try_mt5_ticks(symbol)
    if ticks and len(ticks) > 100:
        deltas = _delta_from_ticks(ticks)
        st.source = DeltaSource.MT5_TICKS
        st.n_ticks_used = len(ticks)
    else:
        # 2. Proxy via tick_volume
        st.source = DeltaSource.TICK_VOLUME_PROXY
        deltas = []
        for i in range(1, len(bars_window)):
            buy_v, sell_v = _split_buy_sell_proxy(bars_window[i], bars_window[i - 1])
            deltas.append(buy_v - sell_v)

    if not deltas:
        st.source = DeltaSource.MISSING
        st.audit["reason"] = "no_deltas_computed"
        return st

    # 3. Indicateurs
    last_delta = float(deltas[-1])
    st.delta_last = last_delta

    cum_5 = sum(deltas[-5:]) if len(deltas) >= 5 else sum(deltas)
    cum_20 = sum(deltas[-20:]) if len(deltas) >= 20 else sum(deltas)
    st.delta_cum_5 = cum_5
    st.delta_cum_20 = cum_20

    # Imbalance = delta / total_volume cumulé
    # Total = somme abs(deltas) sur 5 ou symétrique
    if len(deltas) >= 5:
        recent_deltas = deltas[-5:]
        total_vol = sum(abs(d) for d in recent_deltas)
        if total_vol > 0:
            st.imbalance_ratio = cum_5 / total_vol

    # Direction delta
    if st.imbalance_ratio >= cfg["direction_threshold"]:
        st.direction_delta = DeltaDirection.BUY
    elif st.imbalance_ratio <= -cfg["direction_threshold"]:
        st.direction_delta = DeltaDirection.SELL
    else:
        st.direction_delta = DeltaDirection.NEUTRAL

    # 4. Absorption : volume fort + petit mouvement
    if bars_window:
        last_bar = bars_window[-1]
        volume = float(last_bar.get("tick_volume", 0))
        vsa_sma = _sma(
            [float(b.get("tick_volume", 0)) for b in bars_window[-20:]], 20,
        )
        atr_val = _atr(bars_window, period=14)
        body = _body_size(last_bar)
        if (
            vsa_sma > 0
            and atr_val > 0
            and volume > vsa_sma * cfg["absorption_volume_mult"]
            and body < atr_val * cfg["absorption_movement_atr_mult"]
        ):
            st.absorption_detected = True

    # 5. Stacked imbalance : 3 barres consécutives même signe imbalance > 0.6
    # Approximation : 3 deltas consécutifs du même signe, magnitude suffisante
    if len(deltas) >= 3:
        last_three = deltas[-3:]
        same_sign = (
            (all(d > 0 for d in last_three) or all(d < 0 for d in last_three))
            and all(abs(d) > 0 for d in last_three)
        )
        # Vérifier magnitude (ratio vs max local)
        max_mag = max(abs(d) for d in last_three) + 1e-9
        avg_ratio = (
            sum(abs(d) for d in last_three) / (3 * max_mag)
        )
        if same_sign and avg_ratio > cfg["stacked_imbalance_min"]:
            st.stacked_imbalance = True

    st.audit["config_used"] = cfg
    st.audit["n_ticks_used"] = st.n_ticks_used
    return st


# ─────────────────────────────────────────────────────────────────────
# Intégration — bonus/malus signal
# ─────────────────────────────────────────────────────────────────────
def delta_bonus_malus(
    signal_direction: str,   # "BULLISH" / "BEARISH"
    delta: DeltaState,
) -> float:
    """Calcule le bonus/malus delta pour le composite_score.

    Règles :
      - direction_delta aligné signal → +0.08
      - absorption_detected contre direction → -0.12
      - stacked_imbalance aligné → +0.04 (en plus)
      - sinon → 0.0
    """
    bonus = 0.0
    is_bullish = signal_direction == "BULLISH"
    aligned = (
        (is_bullish and delta.direction_delta == DeltaDirection.BUY)
        or (not is_bullish and delta.direction_delta == DeltaDirection.SELL)
    )
    if aligned:
        bonus += 0.08
        if delta.stacked_imbalance:
            bonus += 0.04
    # Absorption contre direction
    if delta.absorption_detected:
        # On interprète absorption baissière (mouvement faible + volume buy)
        # comme une absorption vendeuse si le bar est baissier
        # Si le bar est haussier mais que signal est bearish → absorption vendeuse
        # Heuristique simple : si imbalance contre direction → malus
        if is_bullish and delta.imbalance_ratio < 0:
            bonus -= 0.12
        elif not is_bullish and delta.imbalance_ratio > 0:
            bonus -= 0.12
    return bonus


__all__ = [
    "DeltaState",
    "DeltaDirection",
    "DeltaSource",
    "DEFAULT_DELTA_CONFIG",
    "compute_delta",
    "delta_bonus_malus",
    "_split_buy_sell_proxy",
    "_delta_from_ticks",
]
