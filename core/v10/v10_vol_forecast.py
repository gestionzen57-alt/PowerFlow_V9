"""V10 Vol Forecast — GARCH/EWMA volatility forecast (Sprint 4 autopilote quant).

Prévision de volatilité via le paquet `arch` (GARCH) avec fallback EWMA
(pure stdlib) si arch indisponible. Utilisé pour :
  - dimensionner les SL/TP (aligned with v10_atr_manager).
  - détecter les régimes VOLATILE/NEWS_LOCK (complement v10_regime_hmm).

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open (données courtes →
vol=vol historique échantillon, pas d'exception), R7, R9 audit, R10.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class VolForecast:
    symbol: str = ""
    timestamp: str = ""
    forecast_vol: float = 0.0        # volatilité annualisée prédite (sigma)
    forecast_vol_pct: float = 0.0   # vol en % du dernier prix
    method: str = "ewma"            # "garch" | "ewma" | "sample"
    n_samples: int = 0
    last_price: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "forecast_vol": round(self.forecast_vol, 6),
            "forecast_vol_pct": round(self.forecast_vol_pct, 6),
            "method": self.method,
            "n_samples": self.n_samples,
            "last_price": round(self.last_price, 6),
            "audit": dict(self.audit),
        }


def _log_returns(closes: List[float]) -> np.ndarray:
    arr = np.asarray(closes, dtype=float)
    arr = np.where(arr > 0, arr, 1e-9)
    return np.diff(np.log(arr))


def _arch_available() -> bool:
    try:
        import arch  # noqa: F401
        return True
    except Exception:
        return False


def _ewma_vol(returns: np.ndarray, span: int = 20) -> float:
    """Vol EWMA (approche simple) sur les returns."""
    if len(returns) == 0:
        return 0.0
    alpha = 2.0 / (span + 1)
    var = float(np.var(returns))
    # EWMA de la variance
    for r in returns:
        var = alpha * (r ** 2) + (1 - alpha) * var
    return math.sqrt(var)


def forecast_vol(
    closes: List[float],
    *,
    symbol: str = "",
    timestamp: str = "",
    method: str = "auto",
    garch_p: int = 1,
    garch_q: int = 1,
    span: int = 20,
) -> VolForecast:
    """Prévoit la volatilité (par pas de bougie) depuis les closes.

    method: "auto" → GARCH si arch dispo + assez de données, sinon EWMA ;
            "ewma" → force EWMA ; "garch" → force GARCH (R6 fallback EWMA).
    """
    res = VolForecast(symbol=symbol, timestamp=timestamp)
    if len(closes) < 10:
        res.audit["reason"] = "insufficient_data"
        return res

    returns = _log_returns(closes)
    res.n_samples = int(len(returns))
    res.last_price = float(closes[-1])

    use_garch = method in ("auto", "garch") and _arch_available() and len(returns) >= 30
    if method == "garch" and not _arch_available():
        log.warning("arch indisponible → fallback EWMA (R6)")
        use_garch = False

    if use_garch:
        try:
            from arch import arch_model
            model = arch_model(returns * 100.0, vol="Garch", p=garch_p, q=garch_q)
            fit = model.fit(disp="off", show_warning=False)
            forecast = fit.forecast(horizon=1)
            vol_pct = float(np.sqrt(forecast.variance.iloc[-1, 0])) / 100.0  # /100 car returns×100
            res.forecast_vol = vol_pct
            res.method = "garch"
            res.audit["model"] = "GARCH"
            res.audit["garch_p"] = garch_p
            res.audit["garch_q"] = garch_q
            res.audit["reason"] = "ok"
        except Exception as exc:
            log.warning("GARCH fit failed → fallback EWMA (R6): %s", exc)
            vol = _ewma_vol(returns, span)
            res.forecast_vol = vol
            res.method = "ewma"
            res.audit["reason"] = f"garch_fallback_ewma:{type(exc).__name__}"
    else:
        vol = _ewma_vol(returns, span)
        res.forecast_vol = vol
        res.method = "ewma"
        res.audit["reason"] = "ok" if len(returns) >= 10 else "short"

    if res.last_price > 0:
        res.forecast_vol_pct = res.forecast_vol  # vol par bougie en fraction
    return res


def sl_tp_from_vol(
    forecast: VolForecast,
    *,
    rr: float = 2.0,
    sl_mult: float = 1.0,
) -> Dict:
    """Calcule un SL/TP raisonnable à partir de la vol prévue.

    SL = sl_mult × forecast_vol (en prix), TP = SL × rr.
    R6 : vol 0 → dict {sl:0, tp:0, valid:False}.
    """
    if forecast.forecast_vol <= 0:
        return {"sl": 0.0, "tp": 0.0, "valid": False, "reason": "zero_vol"}
    sl = forecast.forecast_vol * sl_mult
    return {
        "sl": round(sl, 6),
        "tp": round(sl * rr, 6),
        "rr": rr,
        "sl_mult": sl_mult,
        "valid": True,
        "unit": "price",
    }


def sl_tp_combined_atr_vol(
    atr_pips: float,
    vol_forecast: VolForecast,
    *,
    rr: float = 2.0,
    atr_weight: float = 0.5,
    vol_weight: float = 0.5,
    sl_mult: float = 1.0,
) -> Dict:
    """
    Combine ATR-based et Vol-forecast-based SL/TP.

    Args:
        atr_pips: ATR en pips (ex: 15 pips)
        vol_forecast: VolForecast object avec forecast_vol_pct
        rr: Risk:Reward ratio (TP/SL)
        atr_weight: poids ATR dans le SL final [0,1]
        vol_weight: poids vol forecast dans le SL final [0,1]
        sl_mult: multiplicateur final sur le SL combiné

    Returns:
        dict avec sl_pips, tp_pips, rr, valid, method, breakdown
    """
    # Normaliser poids
    total = atr_weight + vol_weight
    if total == 0:
        atr_weight, vol_weight = 0.5, 0.5
    else:
        atr_weight, vol_weight = atr_weight / total, vol_weight / total

    # SL basé ATR
    sl_atr = atr_pips * sl_mult

    # SL basé vol forecast (vol en % du prix → pips)
    vol_pips = 0.0
    if vol_forecast.last_price > 0 and vol_forecast.forecast_vol_pct > 0:
        vol_pips = vol_forecast.last_price * vol_forecast.forecast_vol_pct * 10000.0  # en pips
    sl_vol = vol_pips * sl_mult

    # Combine
    sl_combined = (atr_weight * sl_atr) + (vol_weight * sl_vol)
    sl_combined = max(1.0, round(sl_combined, 1))  # min 1 pip
    tp_combined = round(sl_combined * rr, 1)

    return {
        "sl_pips": sl_combined,
        "tp_pips": tp_combined,
        "rr": rr,
        "valid": sl_combined > 0,
        "method": "combined_atr_vol",
        "breakdown": {
            "sl_atr_pips": round(sl_atr, 1),
            "sl_vol_pips": round(sl_vol, 1),
            "atr_weight": atr_weight,
            "vol_weight": vol_weight,
            "vol_method": vol_forecast.method,
        },
    }


__all__ = [
    "VolForecast",
    "forecast_vol",
    "sl_tp_from_vol",
    "sl_tp_combined_atr_vol",
    "_ewma_vol",
    "_log_returns",
]
