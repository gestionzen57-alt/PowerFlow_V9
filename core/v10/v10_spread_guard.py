"""V10 Spread Guard — filtre spread pour les setups edge fund.

Mesure le spread courant par paire et applique des seuils.
Sources de données :
  - MT5 bridge (get_spread_series) si dispo.
  - Fallback : OHLCV proxy = high-low / close (approximation).

Seuils pip par paire (recalibrables via JSON config) :
  EURUSD / USDJPY / USDCHF : 1.5 pips
  GBPUSD / AUDUSD / NZDUSD : 2.0 pips
  USDCAD / EURGBP          : 1.8 pips
  Mineurs / Exotiques      : 3.5 pips

Logique de downgrade :
  - spread_ratio > 1.5 → A1 → A2, A2 → A3, A3 → NONE
  - spread_ratio > 2.5 → NONE direct
  - Rollover guard : 23:50-00:10 UTC → NONE

API : check_spread(symbol) → SpreadState
  - current_spread_pips, threshold, ratio, is_clean, guard_active
  - source : 'mt5_live' / 'ohlcv_proxy' / 'fallback'
  - R6 fail-open : spread indisponible → ratio=2.0 (conservateur)
  - R10 : aucune transmission d'ordre.

Doctrine : R1, R2 additif (0 import core/v9/), R6, R7, R9, R10.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, time
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
DEFAULT_SPREAD_THRESHOLDS_PIPS = {
    "EURUSD": 1.5, "USDJPY": 1.5, "USDCHF": 1.5,
    "GBPUSD": 2.0, "AUDUSD": 2.0, "NZDUSD": 2.0,
    "USDCAD": 1.8, "EURGBP": 1.8,
    "OTHER": 3.5,  # mineurs/exotiques
}

DEFAULT_DOWNGRADE_RATIO_MEDIUM = 1.5
DEFAULT_DOWNGRADE_RATIO_HARD = 2.5

ROLLOVER_GUARD_START = (23, 50)
ROLLOVER_GUARD_END = (0, 10)


class SpreadSource(str, Enum):
    MT5_LIVE = "mt5_live"
    OHLCV_PROXY = "ohlcv_proxy"
    FALLBACK = "fallback"
    UNKNOWN = "unknown"


# ─────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────
@dataclass
class SpreadState:
    """État du spread courant pour une paire."""

    symbol: str
    timestamp: str
    current_spread_pips: float = 0.0
    threshold_pips: float = 0.0
    ratio: float = 2.0      # par défaut conservateur
    is_clean: bool = False  # spread_ratio <= 1.5
    guard_active: bool = False
    rollover_active: bool = False
    source: SpreadSource = SpreadSource.UNKNOWN
    downgrade_level: str = "NONE"  # "NONE" / "A3" / "A2" / "NONE_HARD"
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "current_spread_pips": round(self.current_spread_pips, 2),
            "threshold_pips": round(self.threshold_pips, 2),
            "ratio": round(self.ratio, 3),
            "is_clean": self.is_clean,
            "guard_active": self.guard_active,
            "rollover_active": self.rollover_active,
            "source": self.source.value,
            "downgrade_level": self.downgrade_level,
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
def _threshold_for(symbol: str, custom: Optional[Dict[str, float]] = None) -> float:
    """Renvoie le seuil pip pour la paire."""
    table = dict(DEFAULT_SPREAD_THRESHOLDS_PIPS)
    if custom:
        table.update(custom)
    return float(table.get(symbol, table["OTHER"]))


def _spread_from_ohlcv_proxy(bars: List[dict], lookback: int = 5) -> float:
    """Calcule un proxy de spread depuis high-low / close (en pips).

    Approximation réaliste : spread ≈ moyenne(high - low) sur les
    N dernières bougies, divisée par le close moyen.
    Pour paires 4-decimal like EURUSD : 1 pip = 0.0001. Pour JPY : 0.01.
    Le ratio est en pips, calculé sur la magnitude d'1 pip par défaut.
    Convention : 1 pip = 0.0001 (ajuster si JPY via detection close*100).
    """
    if not bars or lookback < 1:
        return 0.0
    sample = bars[-lookback:]
    pip_size = _detect_pip_size(sample)
    spreads_pips = []
    for b in sample:
        h = float(b.get("high", 0))
        l = float(b.get("low", 0))
        if h > 0 and l > 0 and pip_size > 0:
            spreads_pips.append((h - l) / pip_size)
    if not spreads_pips:
        return 0.0
    return sum(spreads_pips) / len(spreads_pips)


def _detect_pip_size(bars: List[dict]) -> float:
    """Détection taille d'1 pip : 0.01 pour JPY, 0.0001 sinon."""
    if not bars:
        return 0.0001
    sample_close = float(bars[-1].get("close", 1.0))
    # JPY convention : close > 50 (USDJPY ≈ 150)
    if sample_close > 50:
        return 0.01
    return 0.0001


def _is_rollover(timestamp: str) -> bool:
    """Vérifie si timestamp est dans la fenêtre rollover 23:50-00:10 UTC.

    Returns True si HH:MM UTC ∈ [23:50, 23:59] ∪ [00:00, 00:10].
    """
    try:
        s = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        # Force UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        hh, mm = dt.hour, dt.minute
        if (hh == ROLLOVER_GUARD_START[0] and mm >= ROLLOVER_GUARD_START[1]):
            return True
        if (hh == 0 and mm <= ROLLOVER_GUARD_END[1]):
            return True
        return False
    except (ValueError, OSError):
        return False


def _downgrade_for(ratio: float, guard_active: bool = False) -> str:
    """Calcule le downgrade level selon ratio.

    Returns
    -------
    "NONE" si is_clean (ratio < 1.5)
    "DOWNGRADE" si medium (1.5 ≤ ratio ≤ 2.5)
    "NONE_HARD" si > 2.5 ou guard actif
    """
    if guard_active:
        return "NONE_HARD"
    if ratio > DEFAULT_DOWNGRADE_RATIO_HARD:
        return "NONE_HARD"
    if ratio >= DEFAULT_DOWNGRADE_RATIO_MEDIUM:
        return "DOWNGRADE"
    return "NONE"


# ─────────────────────────────────────────────────────────────────────
# Bridge MT5 — lazy load
# ─────────────────────────────────────────────────────────────────────
def _try_mt5_spread(symbol: str) -> Optional[float]:
    """Tente de lire le spread live depuis MT5 bridge. R6 fail-open.

    Returns spread en pips si dispo, None sinon.
    """
    try:
        from .v10_mt5_bridge import is_mt5_available, initialize as mt5_init, shutdown as mt5_shutdown
        if not is_mt5_available():
            return None
        if not mt5_init(auto=True):
            return None
        try:
            import MetaTrader5 as mt5  # type: ignore
            ti = mt5.symbol_info_tick(symbol)
            if ti is None:
                return None
            spread_points = ti.spread if hasattr(ti, "spread") else 0
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            point = getattr(info, "point", 0.0001)
            # 1 pip = 10 points en convention broker (réglable).
            # Approximation générique : 1 pip ≈ 10×point pour la plupart.
            pip_size = point * 10
            if pip_size <= 0:
                return None
            return float(spread_points) * point / pip_size
        finally:
            try:
                mt5_shutdown()
            except Exception:
                pass
    except (ImportError, Exception) as e:
        log.debug(f"_try_mt5_spread fallback: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def check_spread(
    symbol: str,
    *,
    timestamp: Optional[str] = None,
    bars: Optional[List[dict]] = None,
    mt5_spread_pips: Optional[float] = None,
    thresholds: Optional[Dict[str, float]] = None,
    seed: Optional[int] = None,
) -> SpreadState:
    """Vérifie le spread courant et retourne l'état permettant le downgrade.

    Parameters
    ----------
    symbol : ex "EURUSD"
    timestamp : ISO 8601 UTC pour rollover guard (défaut: now UTC).
    bars : OHLCV pour fallback proxy si MT5 indisponible.
    mt5_spread_pips : si fourni, court-circuite la lecture MT5.
    thresholds : override des seuils pip par paire.
    seed : graine reproductibilité R9.

    Returns
    -------
    SpreadState avec downgrade_level + audit.
    """
    state = SpreadState(symbol=symbol, timestamp=timestamp or "")
    threshold = _threshold_for(symbol, thresholds)
    state.threshold_pips = threshold

    # 1. Rollover guard
    ts_for_rollover = timestamp
    if not ts_for_rollover:
        ts_for_rollover = datetime.now(timezone.utc).isoformat()
    rollover = _is_rollover(ts_for_rollover)
    state.rollover_active = rollover

    # 2. Source spread
    spread_pips = None
    source = SpreadSource.UNKNOWN

    if mt5_spread_pips is not None:
        spread_pips = float(mt5_spread_pips)
        source = SpreadSource.MT5_LIVE
    else:
        m = _try_mt5_spread(symbol)
        if m is not None:
            spread_pips = m
            source = SpreadSource.MT5_LIVE
        elif bars:
            p = _spread_from_ohlcv_proxy(bars)
            if p > 0:
                spread_pips = p
                source = SpreadSource.OHLCV_PROXY

    if spread_pips is None:
        # R6 fail-open : conservateur ratio=2.0 → NONE_HARD
        state.source = SpreadSource.FALLBACK
        state.current_spread_pips = threshold * 2.0  # worst-case
        state.ratio = 2.0
        state.is_clean = False
        state.guard_active = True
        state.downgrade_level = _downgrade_for(2.0, guard_active=True)
        state.audit = {
            "reason": "no_spread_data",
            "fallback_ratio": 2.0,
            "seed": seed,
        }
        return state

    state.current_spread_pips = spread_pips
    state.source = source
    ratio = spread_pips / threshold if threshold > 0 else 2.0
    state.ratio = ratio
    state.is_clean = ratio <= DEFAULT_DOWNGRADE_RATIO_MEDIUM and not rollover
    state.guard_active = rollover
    state.downgrade_level = _downgrade_for(ratio, guard_active=rollover)
    state.audit = {
        "ratio": ratio,
        "threshold": threshold,
        "thresholds_default": DEFAULT_DOWNGRADE_RATIO_MEDIUM,
        "rollover_active": rollover,
        "seed": seed,
    }
    return state


# ─────────────────────────────────────────────────────────────────────
# Intégration orchestrateur — applique le downgrade au setup level
# ─────────────────────────────────────────────────────────────────────
SETUP_LEVEL_RANK_SG = {"NONE": 0, "A3": 1, "A2": 2, "A1": 3}


def apply_spread_to_signal(current_level: str, spread: SpreadState) -> tuple:
    """Applique le spread downgrade au setup_level.

    Returns
    -------
    (new_level, was_downgraded, downgrade_severity)
    """
    cur_rank = SETUP_LEVEL_RANK_SG.get(current_level, 0)
    # Guard rollover primer (>= HHard)
    if spread.guard_active:
        return "NONE", True, "hard"
    # Hard spread
    if spread.downgrade_level == "NONE_HARD":
        return "NONE", True, "hard"
    # Medium spread → -1 rank
    if spread.downgrade_level == "DOWNGRADE":
        # Baisse d'un cran
        for lvl in ("A1", "A2", "A3", "NONE"):
            if SETUP_LEVEL_RANK_SG[lvl] < cur_rank:
                return lvl, True, "medium"
        return current_level, False, "none"
    # No downgrade (spread.clean)
    return current_level, False, "none"


__all__ = [
    "SpreadState",
    "SpreadSource",
    "DEFAULT_SPREAD_THRESHOLDS_PIPS",
    "DEFAULT_DOWNGRADE_RATIO_MEDIUM",
    "DEFAULT_DOWNGRADE_RATIO_HARD",
    "ROLLOVER_GUARD_START",
    "ROLLOVER_GUARD_END",
    "check_spread",
    "apply_spread_to_signal",
    "_threshold_for",
    "_spread_from_ohlcv_proxy",
    "_detect_pip_size",
    "_is_rollover",
    "_try_mt5_spread",
]
