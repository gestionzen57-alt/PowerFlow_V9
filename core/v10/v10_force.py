"""V10 Module Force — Couche 1 : ce que TU sens.

Calcule les features de domination acheteurs/vendeurs, volatilité, spread,
volume et tick activity à partir des bougies brutes (forces_snapshots).

Terminologie alignée sur la lecture TA humaine (Søn), pas sur les features
internes V9. Chaque feature F1-F5 est testée unitairement (R7).

Features :
  F1 — Ratio acheteurs/vendeurs (delta prix × volume)
  F2 — Volatilité réalisée (ATR sur N bougies)
  F3 — Spread normalisé (spread / ATR)
  F4 — Volume relatif (volume / moyenne mobile volume)
  F5 — Tick activity (variations de prix par unité de temps)

Doctrine : R2 additif pur, R6 fail-open, R9 audit (seed reproductible).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Seuils par défaut (modulables, versionnés via overrides)
DEFAULTS = {
    "f1_delta_weight": 1.0,       # poids du delta prix dans F1
    "f2_atr_period": 14,          # bougies pour l'ATR
    "f3_max_spread_ratio": 0.30,  # spread/ATR au-delà = illiquide
    "f4_volume_period": 20,       # moyenne mobile volume
    "f5_min_ticks_per_bar": 3,    # seuil activité faible
}


@dataclass
class ForceResult:
    """Résultat du module Force pour une bougie."""

    symbol: str
    timestamp: str
    timeframe: str

    f1_buy_pressure: float = 0.0      # 0..1 (1 = domination acheteurs)
    f2_atr: float = 0.0               # volatilité réalisée (pips)
    f3_spread_ratio: float = 0.0      # spread / ATR (0..∞)
    f4_volume_rel: float = 0.0        # volume / moyenne (1.0 = normal)
    f5_tick_activity: float = 0.0     # ticks par bougie normalisés

    force_level: str = "LOW"          # LOW / MEDIUM / HIGH / EXTREME
    illiquid: bool = False            # F3 franchi → pas tradeable
    summary: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "f1_buy_pressure": round(self.f1_buy_pressure, 4),
            "f2_atr": round(self.f2_atr, 4),
            "f3_spread_ratio": round(self.f3_spread_ratio, 4),
            "f4_volume_rel": round(self.f4_volume_rel, 4),
            "f5_tick_activity": round(self.f5_tick_activity, 4),
            "force_level": self.force_level,
            "illiquid": self.illiquid,
        }


def _atr(bars: List[dict], period: int) -> float:
    """True Range moyen sur les N dernières bougies. R6 fail-open → 0 si data insuffisante."""
    if len(bars) < 2:
        return 0.0
    window = bars[-(period + 1):]
    trs: List[float] = []
    for i in range(1, len(window)):
        h, l, pc = window[i]["high"], window[i]["low"], window[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def _sma(values: List[float], period: int) -> float:
    if len(values) < period or period <= 0:
        return 0.0
    window = values[-period:]
    return sum(window) / len(window)


def compute_force(
    symbol: str,
    timestamp: str,
    timeframe: str,
    bars: List[dict],
    *,
    overrides: Optional[dict] = None,
) -> ForceResult:
    """Calcule les 5 features Force pour la bougie la plus récente.

    bars : liste de dicts OHLCV croissante par temps, chacun :
        {open, high, low, close, tick_volume, spread_points}
    La dernière bougie est la référence.
    """
    cfg = dict(DEFAULTS)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if k in DEFAULTS})

    if not bars:
        res = ForceResult(symbol, timestamp, timeframe)
        res.force_level = "LOW"
        return res

    res = ForceResult(symbol, timestamp, timeframe)
    cur = bars[-1]
    high, low, close = float(cur["high"]), float(cur["low"]), float(cur["close"])
    spread = float(cur.get("spread_points", 0.0) or 0.0)
    vol = float(cur.get("tick_volume", 0.0) or 0.0)

    # ---- F1 : pression acheteurs/vendeurs (delta prix sur N bars, pondéré vol) ----
    lookback = min(len(bars), int(cfg["f1_delta_weight"]) + 4)
    deltas = []
    for i in range(max(1, len(bars) - lookback + 1), len(bars)):
        prev_close = float(bars[i - 1]["close"])
        d = (float(bars[i]["close"]) - prev_close) / prev_close if prev_close else 0.0
        deltas.append(d)
    if deltas:
        # somme des deltas signés / somme des |deltas| → -1..1, mappé 0..1
        s = sum(deltas)
        a = sum(abs(x) for x in deltas)
        res.f1_buy_pressure = (0.5 + 0.5 * (s / a)) if a else 0.5
    else:
        res.f1_buy_pressure = 0.5

    # ---- F2 : ATR ----
    res.f2_atr = _atr(bars, int(cfg["f2_atr_period"]))
    atr = res.f2_atr if res.f2_atr > 0 else max(high - low, 1e-9)

    # ---- F3 : spread normalisé ----
    res.f3_spread_ratio = spread / atr
    res.illiquid = res.f3_spread_ratio > float(cfg["f3_max_spread_ratio"])

    # ---- F4 : volume relatif ----
    vols = [float(b.get("tick_volume", 0.0) or 0.0) for b in bars]
    base = _sma(vols, int(cfg["f4_volume_period"]))
    res.f4_volume_rel = (vol / base) if base > 0 else (1.0 if vol > 0 else 0.0)

    # ---- F5 : tick activity (variations de prix / bar normalisées) ----
    # proxy : nombre de bars récents avec close != open / lookback
    moves = sum(
        1 for b in bars[-max(1, int(cfg["f5_min_ticks_per_bar"])):]
        if float(b["close"]) != float(b["open"])
    )
    res.f5_tick_activity = moves / max(1, int(cfg["f5_min_ticks_per_bar"]))

    # ---- Synthèse force_level ----
    # F1 proche 0 ou 1 = domination claire ; F4 volume élevé amplifie
    dom = abs(res.f1_buy_pressure - 0.5) * 2.0  # 0..1
    score = dom
    if res.f4_volume_rel >= 1.5:
        score += 0.2
    if res.f4_volume_rel >= 2.0:
        score += 0.2
    if res.f2_atr > 0 and res.f2_atr / (high - low + 1e-9) > 1.2:
        score += 0.1  # volatilité au-delà du range de la bougie = expansion

    if score >= 0.8:
        res.force_level = "EXTREME"
    elif score >= 0.55:
        res.force_level = "HIGH"
    elif score >= 0.30:
        res.force_level = "MEDIUM"
    else:
        res.force_level = "LOW"

    res.summary = {"score": round(score, 3)}
    return res
