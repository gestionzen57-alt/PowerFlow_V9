"""
V10 PnL Simulator — CYCLE 5 ROOT FIX (09/08/2026)

Problème identifié dans _simulate_pnl() du replay_engine :
  - close=0.0 en fallback DB → tous les trades entrent à 0 → PnL factice
  - TP/SL trop courts sur M1/M5 (5p/3p) → quasi-aléatoire
  - Pas de spread intégré dans le calcul
  - Pas d'ATR-awareness : TP/SL fixés indépendamment de la volatilité

Fix C5 :
  F_PNL1 — Guard close=0 strict : refuse d'entrer si prix invalide
  F_PNL2 — TP/SL ATR-dynamiques : si ATR dispo dans bars, TP=2*ATR SL=1*ATR
  F_PNL3 — Spread cost déduit : spread_points * spread_factor retiré du PnL
  F_PNL4 — Fallback TP/SL par TF inchangé si ATR absent
  F_PNL5 — Direction-aware : long=close_next-close_now, short=inverse

Doctrine R10 : compute-only, zéro ordre réel.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# TP/SL par TF (pips) — fallback si ATR absent
TP_SL_BY_TF: Dict[str, Tuple[float, float]] = {
    "M1":  (8.0,   4.0),
    "M5":  (12.0,  6.0),
    "M15": (20.0,  10.0),
    "M30": (30.0,  15.0),
    "H1":  (50.0,  25.0),
    "H4":  (100.0, 50.0),
    "D1":  (200.0, 100.0),
}

# ATR multipliers C5
ATR_TP_MULT = 1.8   # TP = 1.8 * ATR
ATR_SL_MULT = 0.9   # SL = 0.9 * ATR

# Spread factor : coût du spread en fraction du spread_points
SPREAD_FACTOR = 1.0  # déduire 1x le spread_points du PnL

# Min pips pour valider une barre (close doit être > 0)
MIN_VALID_PRICE = 1e-6


def _compute_atr(bars: List[Dict], period: int = 14) -> float:
    """
    ATR simple depuis barres OHLCV.
    Retourne ATR en unités de prix (pas en pips).
    R6 fail-open : 0.0 si données insuffisantes.
    """
    if len(bars) < period + 1:
        return 0.0
    try:
        trs: List[float] = []
        for i in range(1, len(bars)):
            high  = float(bars[i].get("high",  0.0) or 0.0)
            low   = float(bars[i].get("low",   0.0) or 0.0)
            close_prev = float(bars[i - 1].get("close", 0.0) or 0.0)
            if high <= 0 or low <= 0 or close_prev <= 0:
                continue
            tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
            trs.append(tr)
        if len(trs) < period:
            return 0.0
        return sum(trs[-period:]) / period
    except Exception:
        return 0.0


def simulate_pnl(
    bars: List[Dict],
    entry_idx: int,
    action: str,
    pair: str,
    tf: str,
) -> float:
    """
    C5 ROOT FIX : simulation PnL propre.

    1. Guard close=0 : retourne 0.0 si prix d'entrée invalide
    2. ATR-aware TP/SL si ATR calculable depuis bars
    3. Spread cost intégré
    4. Direction-aware : long / short
    5. Parcours barres futures pour TP/SL hit
    """
    if entry_idx >= len(bars):
        return 0.0

    entry_bar = bars[entry_idx]
    entry_close = float(entry_bar.get("close") or 0.0)

    # F_PNL1 : guard prix invalide
    if entry_close < MIN_VALID_PRICE:
        log.debug("[PNL-C5] %s/%s entry_close invalide=%.6f → skip", pair, tf, entry_close)
        return 0.0

    is_jpy  = pair.upper().endswith("JPY")
    pip     = 0.01 if is_jpy else 0.0001

    # F_PNL2 : ATR-aware TP/SL
    window_bars = bars[max(0, entry_idx - 50): entry_idx + 1]
    atr_price   = _compute_atr(window_bars, period=14)

    if atr_price > MIN_VALID_PRICE:
        tp_price_dist = atr_price * ATR_TP_MULT
        sl_price_dist = atr_price * ATR_SL_MULT
        tp_p = tp_price_dist / pip
        sl_p = sl_price_dist / pip
    else:
        # F_PNL4 : fallback TP/SL par TF
        tp_p, sl_p = TP_SL_BY_TF.get(tf, (20.0, 10.0))
        tp_price_dist = tp_p * pip
        sl_price_dist = sl_p * pip

    sign = 1 if action == "BUY" else -1
    tp_price = entry_close + tp_price_dist * sign
    sl_price = entry_close - sl_price_dist * sign

    # F_PNL3 : spread cost
    spread_pts   = float(entry_bar.get("spread_points", 0.0) or 0.0)
    spread_cost  = (spread_pts * SPREAD_FACTOR) / pip if pip > 0 else 0.0

    # Parcours barres futures
    max_hold = max(3, min(15, int(tp_p / 5)))
    for j in range(entry_idx + 1, min(entry_idx + 1 + max_hold, len(bars))):
        high  = float(bars[j].get("high",  entry_close) or entry_close)
        low   = float(bars[j].get("low",   entry_close) or entry_close)

        if high < MIN_VALID_PRICE or low < MIN_VALID_PRICE:
            continue

        if action == "BUY":
            if high >= tp_price:
                return round(tp_p - spread_cost, 2)
            if low  <= sl_price:
                return round(-sl_p - spread_cost, 2)
        else:
            if low  <= tp_price:
                return round(tp_p - spread_cost, 2)
            if high >= sl_price:
                return round(-sl_p - spread_cost, 2)

    # Exit au close de la dernière barre de la fenêtre
    exit_idx   = min(entry_idx + max_hold, len(bars) - 1)
    exit_close = float(bars[exit_idx].get("close") or entry_close)
    if exit_close < MIN_VALID_PRICE:
        return 0.0

    raw_pnl = (exit_close - entry_close) * sign / pip
    return round(raw_pnl - spread_cost, 2)


__all__ = ["simulate_pnl", "TP_SL_BY_TF", "ATR_TP_MULT", "ATR_SL_MULT"]
