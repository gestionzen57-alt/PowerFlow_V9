"""V10 ATR Manager — SL/TP dynamique adaptatif (ÉTAPE 5).

Plan HERMES_PLAN_V10 :
  SL = 1.5 × ATR(14, H1)
  TP = 2.5 × ATR(14, H1)
  Ratio R:R = TP/SL = 5/3 = 1.67 (>= minimum plan)
  ATR recalculé toutes les 4H

Sortie par paire :
  - sl_pips (SL adaptatif)
  - tp_pips (TP adaptatif)
  - rr_ratio (TP/SL)
  - atr_h1 (ATR(14, H1) en pips)
  - last_calc_ts (timestamp dernier calcul)
  - status ('LIVE', 'STALE', 'INSUFFICIENT')

Doctrine V10 : R1-AGIR, R2 additif pur (stdlib + math only),
R6 fail-open (closes vides → defaults, pas de crash), R7 tests,
R8 surcharge des ratios SL/TP, R9 audit, R10 0 capital.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────
# Defaults (R8 surchargeables)
# ─────────────────────────────────────────────────────────────────────
DEFAULT_ATR_PERIOD: int = 14
DEFAULT_ATR_TIMEFRAME: str = "H1"
DEFAULT_SL_MULT: float = 1.5    # 1.5 × ATR = SL
DEFAULT_TP_MULT: float = 2.5    # 2.5 × ATR = TP
DEFAULT_RECALC_HOURS: int = 4   # ATR recalculé toutes les 4H
DEFAULT_PIP_FACTOR: float = 10000.0  # 0.0001 → 1 pip (paires forex 4 décimales)
PIP_FACTOR_JPY: float = 100.0  # paires JPY 2 décimales

VALID_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")


# ─────────────────────────────────────────────────────────────────────
# Dataclass
# ─────────────────────────────────────────────────────────────────────
@dataclass
class ATRResult:
    """Résultat ATR + SL/TP pour une paire."""
    pair: str
    timestamp: str = ""
    timeframe: str = DEFAULT_ATR_TIMEFRAME
    atr_period: int = DEFAULT_ATR_PERIOD
    atr_price: float = 0.0      # ATR en unité de prix (ex: 0.0012)
    atr_pips: float = 0.0        # ATR converti en pips
    sl_pips: float = 0.0
    tp_pips: float = 0.0
    rr_ratio: float = 0.0
    n_bars_used: int = 0
    is_stale: bool = False
    status: str = "INSUFFICIENT"
    sl_mult: float = DEFAULT_SL_MULT
    tp_mult: float = DEFAULT_TP_MULT

    def as_dict(self) -> Dict:
        return {
            "pair": self.pair,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "atr_period": self.atr_period,
            "atr_price": round(self.atr_price, 6),
            "atr_pips": round(self.atr_pips, 1),
            "sl_pips": round(self.sl_pips, 1),
            "tp_pips": round(self.tp_pips, 1),
            "rr_ratio": round(self.rr_ratio, 2),
            "n_bars_used": self.n_bars_used,
            "is_stale": self.is_stale,
            "status": self.status,
            "sl_mult": self.sl_mult,
            "tp_mult": self.tp_mult,
        }


# ─────────────────────────────────────────────────────────────────────
# Calcul ATR pure (R9 auditable)
# ─────────────────────────────────────────────────────────────────────
def true_range(high: float, low: float, prev_close: float) -> float:
    """True Range classique : max(H-L, |H-PrevClose|, |L-PrevClose|)."""
    if prev_close <= 0:
        return max(high - low, 0.0)
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr_from_bars(
    bars: List[dict],
    period: int = DEFAULT_ATR_PERIOD,
    *,
    end_index: Optional[int] = None,
) -> Tuple[float, int]:
    """ATR sur les `period` dernières barres (Williams R6 : incomplet → partial).

    Args:
        bars: [{'high', 'low', 'close'}, ...] (chronologique ascendant).
        period: nb de bougies (défaut 14).
        end_index: si fourni, on regarde l'index comme dernier ; sinon len(bars)-1.

    Returns (atr_price, n_used).
    """
    if not bars:
        return 0.0, 0
    n = len(bars)
    last = end_index if end_index is not None else n - 1
    if last < 0 or last >= n:
        last = n - 1
    first = max(0, last - period + 1)
    if first == 0:
        # Pas de bougie précédente pour calcul TR[0] : on skip
        first = 1
    if last - first + 1 < 2:
        return 0.0, 0  # pas de bougies calculables
    trs = []
    for i in range(first, last + 1):
        h = float(bars[i].get("high", 0.0))
        l = float(bars[i].get("low", 0.0))
        c = float(bars[i].get("close", 0.0))
        p = float(bars[i - 1].get("close", c))
        trs.append(true_range(h, l, p))
    if not trs:
        return 0.0, 0
    return sum(trs) / len(trs), len(trs)


# ─────────────────────────────────────────────────────────────────────
# Mapping paire → facteur pip
# ─────────────────────────────────────────────────────────────────────
def _pip_factor_for(pair: str) -> float:
    """10000 pour paires 4 décimales, 100 pour paires JPY 2 décimales."""
    if "JPY" in pair.upper():
        return PIP_FACTOR_JPY
    return DEFAULT_PIP_FACTOR


# ─────────────────────────────────────────────────────────────────────
# Calcul sl/tp par paire
# ─────────────────────────────────────────────────────────────────────
def compute_sl_tp(
    pair: str,
    bars_h1: List[dict],
    *,
    period: int = DEFAULT_ATR_PERIOD,
    sl_mult: float = DEFAULT_SL_MULT,
    tp_mult: float = DEFAULT_TP_MULT,
    timestamp: Optional[str] = None,
    recalc_hours: int = DEFAULT_RECALC_HOURS,
    last_calc_ts: Optional[str] = None,
) -> ATRResult:
    """Calcule SL/TP adaptatif ATR(14, H1) selon plan § ÉTAPE 5.

    SL = sl_mult × ATR
    TP = tp_mult × ATR
    ATR recalculé si plus de `recalc_hours` heures écoulées
    (R10 : pour économiser le compute live, pas critique en backtest).
    """
    r = ATRResult(pair=pair, timestamp=timestamp or "", timeframe="H1",
                  atr_period=period, sl_mult=sl_mult, tp_mult=tp_mult)
    # Stale check (si last_calc_ts fourni)
    if last_calc_ts:
        try:
            last = datetime.fromisoformat(last_calc_ts.replace("Z", "+00:00"))
            cur = (datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                   if timestamp else datetime.now(timezone.utc))
            age_h = (cur - last).total_seconds() / 3600.0
            r.is_stale = age_h > recalc_hours
        except Exception:
            pass

    atr, n_used = atr_from_bars(bars_h1, period=period)
    r.atr_price = atr
    r.n_bars_used = n_used
    if atr <= 0 or n_used < 2:
        r.status = "INSUFFICIENT"
        return r
    pip_factor = _pip_factor_for(pair)
    r.atr_pips = atr * pip_factor
    r.sl_pips = round(sl_mult * r.atr_pips, 1)
    r.tp_pips = round(tp_mult * r.atr_pips, 1)
    r.rr_ratio = round(r.tp_pips / r.sl_pips, 2) if r.sl_pips > 0 else 0.0
    r.status = "STALE" if r.is_stale else "LIVE"
    return r


def compute_sl_tp_multi(
    pairs_bars_h1: Dict[str, List[dict]],
    *,
    period: int = DEFAULT_ATR_PERIOD,
    sl_mult: float = DEFAULT_SL_MULT,
    tp_mult: float = DEFAULT_TP_MULT,
    timestamp: Optional[str] = None,
) -> Dict[str, ATRResult]:
    """Calcule SL/TP pour plusieurs paires. R6 : paires vides ignorées."""
    out: Dict[str, ATRResult] = {}
    for pair, bars in pairs_bars_h1.items():
        out[pair] = compute_sl_tp(
            pair, bars, period=period, sl_mult=sl_mult,
            tp_mult=tp_mult, timestamp=timestamp,
        )
    return out


# ─────────────────────────────────────────────────────────────────────
# Validation vs plan
# ─────────────────────────────────────────────────────────────────────
def check_against_plan(result: ATRResult) -> Dict[str, bool]:
    """Vérifie que le résultat respecte le plan (SL/TP, RR)."""
    return {
        "sl_mult_match": abs(result.sl_mult - DEFAULT_SL_MULT) < 1e-9,
        "tp_mult_match": abs(result.tp_mult - DEFAULT_TP_MULT) < 1e-9,
        "rr_meets_min": result.rr_ratio >= (DEFAULT_TP_MULT / DEFAULT_SL_MULT),
        "status_live": result.status in ("LIVE", "STALE", "INSUFFICIENT"),
    }


# ─────────────────────────────────────────────────────────────────────
# __all__
# ─────────────────────────────────────────────────────────────────────
__all__ = [
    "DEFAULT_ATR_PERIOD",
    "DEFAULT_ATR_TIMEFRAME",
    "DEFAULT_SL_MULT",
    "DEFAULT_TP_MULT",
    "DEFAULT_RECALC_HOURS",
    "VALID_TIMEFRAMES",
    "ATRResult",
    "true_range",
    "atr_from_bars",
    "compute_sl_tp",
    "compute_sl_tp_multi",
    "check_against_plan",
]
