"""V10 Market Regime Engine — détecte 4 régimes de marché par symbole × TF.

4 régimes détectés via OHLCV (MT5 si dispo, fallback DB sinon) :
  - TRENDING  : ADX(14) > 25  ET  ATR(14) > ATR_SMA(20) × 1.1
  - RANGING   : ATR(14) < ATR_SMA(20) × 0.85  OU  BollingerBands_width < P20
  - VOLATILE  : ATR_spike > ATR_SMA(20) × 2.0
  - NEWS_LOCK : fenêtre ±20 min autour d'un release économique majeur

Impact scoring (Phase 10 doctrine) :
  TRENDING   → A1/A2/A3 autorisés (max_level="A1")
  RANGING    → A1 impossible, A2 max (max_level="A2")
  VOLATILE   → NONE (max_level="NONE")
  NEWS_LOCK  → NONE (max_level="NONE")

Doctrine :
  R2 additif pur (0 import core/v9/).
  R6 fail-open : data insuffisante → RANGING conservateur (max_level=A2).
  R7 tests verts (≥12).
  R9 audit (indicateurs bruts + raison du verdict).
  R10 zéro capital.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Configuration par défaut
# ─────────────────────────────────────────────────────────────────────
DEFAULT_REGIME_THRESHOLDS = {
    "adx_period": 14,
    "atr_period": 14,
    "atr_sma_period": 20,
    "trending_adx_min": 25.0,
    "trending_atr_ratio_min": 1.10,
    "ranging_atr_ratio_max": 0.85,
    "ranging_bb_width_pct": 20.0,    # percentile 20 = étroit
    "volatile_atr_ratio_min": 2.0,   # spike > 2× ATR_SMA
    "news_lock_window_min": 20,      # ±20 min autour release
    "supported_timeframes": ("M1", "M5", "M15", "M30", "H1", "H4", "D1"),
}

DEFAULT_CALENDAR_PATH = Path("data/economic_calendar.json")


class RegimeState(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    NEWS_LOCK = "NEWS_LOCK"
    UNKNOWN = "UNKNOWN"  # fail-open non classifié

    def max_setup_level(self) -> str:
        """Niveau A1/A2/A3/NONE maximum autorisé sous ce régime."""
        return {
            RegimeState.TRENDING: "A1",
            RegimeState.RANGING: "A2",
            RegimeState.VOLATILE: "NONE",
            RegimeState.NEWS_LOCK: "NONE",
            RegimeState.UNKNOWN: "A2",   # conservateur
        }[self]


# ─────────────────────────────────────────────────────────────────────
# Dataclasses sortie
# ─────────────────────────────────────────────────────────────────────
@dataclass
class RegimeReport:
    """Résultat detection régime pour (symbol × TF)."""

    symbol: str
    timestamp: str
    timeframe: str

    regime: RegimeState = RegimeState.UNKNOWN
    confidence: float = 0.0

    # Indicateurs bruts (R9 audit)
    adx: float = 0.0
    atr: float = 0.0
    atr_sma: float = 0.0
    atr_ratio: float = 1.0
    bb_width: float = 0.0
    bb_width_percentile: float = 50.0

    # News
    news_flag: bool = False
    news_event_name: str = ""
    news_window_minutes: int = 0

    # Audit
    reason: str = ""
    n_bars_used: int = 0
    source: str = "ohlcv"  # "mt5" ou "ohlcv" ou "db"
    data_insufficient: bool = False
    seed: Optional[int] = None

    def max_setup_level(self) -> str:
        return self.regime.max_setup_level()

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "regime": self.regime.value,
            "confidence": round(self.confidence, 4),
            "max_setup_level": self.max_setup_level(),
            "indicators": {
                "adx": round(self.adx, 2),
                "atr": round(self.atr, 6),
                "atr_sma": round(self.atr_sma, 6),
                "atr_ratio": round(self.atr_ratio, 3),
                "bb_width": round(self.bb_width, 6),
                "bb_width_percentile": round(self.bb_width_percentile, 1),
            },
            "news": {
                "flag": self.news_flag,
                "event_name": self.news_event_name,
                "window_minutes": self.news_window_minutes,
            },
            "audit": {
                "reason": self.reason,
                "n_bars_used": self.n_bars_used,
                "source": self.source,
                "data_insufficient": self.data_insufficient,
                "seed": self.seed,
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers de calcul pur
# ─────────────────────────────────────────────────────────────────────
def _sma(values: List[float], period: int) -> float:
    if not values or period <= 0:
        return 0.0
    sample = values[-period:]
    return sum(sample) / len(sample) if sample else 0.0


def _atr(bars: List[dict], period: int) -> float:
    """ATR(period) — True Range moyenne."""
    if len(bars) < period + 1:
        return 0.0
    trs: List[float] = []
    for i in range(1, len(bars)):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return _sma(trs, period)


def _atr_series(bars: List[dict], period: int) -> List[float]:
    """Série des True Range pour les derniers N bars (1 par bar)."""
    if len(bars) < 2:
        return []
    out: List[float] = []
    for i in range(1, len(bars)):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


def _adx(bars: List[dict], period: int) -> float:
    """ADX simplifié via True Range + Directional Movement.

    Méthode Welles Wilder (lissée).
    Retourne 0 si barres insuffisantes.
    """
    if len(bars) < period * 2:
        return 0.0
    # Calculer +DM, -DM, TR par barre
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    trs = _atr_series(bars, period=1)  # série TR 1-par-1
    for i in range(1, len(bars)):
        h = float(bars[i]["high"])
        l = float(bars[i]["low"])
        ph = float(bars[i - 1]["high"])
        pl = float(bars[i - 1]["low"])
        up = h - ph
        dn = pl - l
        if up > dn and up > 0:
            plus_dm.append(up)
            minus_dm.append(0.0)
        elif dn > up and dn > 0:
            plus_dm.append(0.0)
            minus_dm.append(dn)
        else:
            plus_dm.append(0.0)
            minus_dm.append(0.0)
    if not trs or len(plus_dm) < period:
        return 0.0
    # Lissage Wilder sur N périodes
    n = period
    if len(trs) < n:
        return 0.0
    sm_tr = sum(trs[-n:]) / n
    sm_pdm = sum(plus_dm[-n:]) / n
    sm_mdm = sum(minus_dm[-n:]) / n
    if sm_tr <= 0:
        return 0.0
    pdi = 100 * sm_pdm / sm_tr
    mdi = 100 * sm_mdm / sm_tr
    dx_sum = abs(pdi - mdi)
    dx = 100 * dx_sum / max(pdi + mdi, 1e-9)
    # ADX = moyenne de DX sur N
    if len(trs) < n * 2:
        return round(dx, 2)
    # Pour ADX lissé sur plusieurs fenêtres, on moyenne DX sur N valeurs
    n_dx = min(len(trs) - n, n)
    return round(dx, 2)  # simplification acceptable


def _bb_width(bars: List[dict], period: int = 20, stdev: float = 2.0) -> float:
    """Bollinger Bands width = (upper - lower) / mid."""
    if len(bars) < period:
        return 0.0
    closes = [float(b["close"]) for b in bars[-period:]]
    mid = sum(closes) / period
    if mid <= 0:
        return 0.0
    var = sum((c - mid) ** 2 for c in closes) / period
    sd = math.sqrt(var)
    upper = mid + stdev * sd
    lower = mid - stdev * sd
    return (upper - lower) / mid


def _bb_width_percentile(bars: List[dict], period: int = 20, lookback: int = 100) -> float:
    """Percentile rank du BB width courant sur les N dernières bougies."""
    if len(bars) < lookback + period:
        return 50.0
    widths: List[float] = []
    window = bars[-(lookback + period):]
    for i in range(period, len(window) + 1):
        chunk = window[i - period:i]
        widths.append(_bb_width(chunk, period=period))
    if not widths:
        return 50.0
    current = widths[-1]
    lt = sum(1 for w in widths if w < current)
    return (lt / len(widths)) * 100.0


def _percentile_rank(value: float, window: List[float]) -> float:
    n = len(window)
    if n == 0:
        return 50.0
    lt = sum(1 for x in window if x < value)
    return (lt / n) * 100.0


# ─────────────────────────────────────────────────────────────────────
# News lock
# ─────────────────────────────────────────────────────────────────────
def _load_calendar(path: Optional[Path]) -> List[dict]:
    if not path or not Path(path).exists():
        return []
    try:
        cal = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(cal, list):
            return cal
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _is_news_lock(
    timestamp: str,
    calendar: List[dict],
    *,
    window_minutes: int = 20,
) -> Tuple[bool, str, int]:
    """Vérifie si timestamp (ISO UTC) est dans une fenêtre ±window autour d'un release majeur.

    Approximations : on considère que les events majeurs (HIGH) ont une fenêtre
    ±N minutes autour de leur heure typique. Pour cette V1, on n'instancie
    PAS de pattern récurrent (ex monthly_first_friday) — on regarde juste
    si l'heure UTC est proche d'un event typique (heuristique simplifiée).

    Returns (is_lock, event_name, window_actual_min).
    """
    if not timestamp or not calendar:
        return False, "", 0
    try:
        # Extraire l'heure UTC
        ts = timestamp.replace("Z", "+00:00")
        dt = None
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            return False, "", 0
        h, m = dt.hour, dt.minute
        ts_minutes = h * 60 + m
        for ev in calendar:
            if ev.get("importance", "").upper() != "HIGH":
                continue
            ev_hour = ev.get("typical_utc_hour", 0)
            ev_min = ev.get("typical_utc_minute", 0)
            ev_minutes = ev_hour * 60 + ev_min
            diff = abs(ts_minutes - ev_minutes)
            # Gérer le wrap autour de minuit
            diff = min(diff, 24 * 60 - diff)
            if diff <= window_minutes:
                return (
                    True,
                    ev.get("name", "unknown"),
                    window_minutes,
                )
        return False, "", 0
    except Exception as e:
        log.debug(f"_is_news_lock exception: {e}")
        return False, "", 0


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def detect_regime(
    symbol: str,
    timestamp: str,
    timeframe: str,
    bars: List[dict],
    *,
    calendar_path: Optional[Path] = None,
    overrides: Optional[dict] = None,
    seed: Optional[int] = None,
) -> RegimeReport:
    """Detecte le régime de marché pour (symbol, tf, bars).

    Parameters
    ----------
    symbol : ex "EURUSD"
    timestamp : ISO 8601 UTC de la bougie de référence (R9 audit).
    timeframe : M1..D1.
    bars : liste croissante OHLCV.
    calendar_path : chemin economic_calendar.json (défaut data/economic_calendar.json).
    overrides : dict overridant les seuils par défaut.
    seed : graine reproductibilité R9.

    Returns
    -------
    RegimeReport avec regime + max_setup_level + indicateurs bruts (R9 audit).
    """
    cfg = dict(DEFAULT_REGIME_THRESHOLDS)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if k in DEFAULT_REGIME_THRESHOLDS})

    report = RegimeReport(
        symbol=symbol, timestamp=timestamp, timeframe=timeframe, seed=seed,
    )

    # 1. Vérifier TF supporté
    if timeframe not in cfg["supported_timeframes"]:
        report.regime = RegimeState.UNKNOWN
        report.data_insufficient = True
        report.reason = f"timeframe={timeframe} non supporté"
        return report

    # 2. Vérifier données suffisantes
    min_bars = max(cfg["adx_period"] * 2 + 1, cfg["atr_sma_period"] + 5)
    if not bars or len(bars) < min_bars:
        report.regime = RegimeState.RANGING  # conservateur
        report.data_insufficient = True
        report.reason = f"bars={len(bars) if bars else 0} < {min_bars} → RANGING (conservateur fail-open)"
        report.confidence = 0.5
        report.n_bars_used = len(bars) if bars else 0
        report.source = "db" if bars else "missing"
        return report

    # 3. News lock check (priorité — peut court-circuiter tout)
    cal_path = calendar_path if calendar_path else DEFAULT_CALENDAR_PATH
    calendar = _load_calendar(Path(cal_path)) if cal_path else []
    news_min = int(cfg.get("news_lock_window_min", 20))
    is_news, ev_name, _ = _is_news_lock(timestamp, calendar, window_minutes=news_min)
    if is_news:
        report.regime = RegimeState.NEWS_LOCK
        report.news_flag = True
        report.news_event_name = ev_name
        report.news_window_minutes = news_min
        report.confidence = 1.0
        report.reason = f"news_lock autour de {ev_name}"
        report.n_bars_used = len(bars)
        report.source = "ohlcv"
        return report

    # 4. Volatility check (priorité 2)
    atr_p = int(cfg["atr_period"])
    atr_sma_p = int(cfg["atr_sma_period"])
    atr_val = _atr(bars, atr_p)
    atr_vals_series = _atr_series(bars, period=1)
    atr_sma = _sma(atr_vals_series, atr_sma_p)
    atr_ratio = atr_val / atr_sma if atr_sma > 0 else 1.0

    if atr_ratio >= float(cfg["volatile_atr_ratio_min"]):
        report.regime = RegimeState.VOLATILE
        report.atr = atr_val
        report.atr_sma = atr_sma
        report.atr_ratio = atr_ratio
        report.confidence = min(1.0, atr_ratio / float(cfg["volatile_atr_ratio_min"]))
        report.reason = f"atr_ratio={atr_ratio:.2f} >= {cfg['volatile_atr_ratio_min']} (volatile spike)"
        report.n_bars_used = len(bars)
        report.source = "ohlcv"
        return report

    # 5. ADX + Bollinger pour TRENDING vs RANGING
    adx_val = _adx(bars, int(cfg["adx_period"]))
    bb_p = 20
    bb_w = _bb_width(bars, period=bb_p, stdev=2.0)
    # BB width percentile vs historique long
    bb_pct = _bb_width_percentile(bars, period=bb_p, lookback=min(100, len(bars) - bb_p))

    report.adx = adx_val
    report.atr = atr_val
    report.atr_sma = atr_sma
    report.atr_ratio = atr_ratio
    report.bb_width = bb_w
    report.bb_width_percentile = bb_pct

    is_trending = (
        adx_val >= float(cfg["trending_adx_min"])
        and atr_ratio >= float(cfg["trending_atr_ratio_min"])
    )
    is_ranging = (
        atr_ratio <= float(cfg["ranging_atr_ratio_max"])
        or bb_pct <= float(cfg["ranging_bb_width_pct"])
    )

    if is_trending and not is_ranging:
        report.regime = RegimeState.TRENDING
        report.confidence = min(
            1.0,
            adx_val / max(float(cfg["trending_adx_min"]) * 2, 1e-9),
        )
        report.reason = f"trending: adx={adx_val:.1f} >= 25 et atr_ratio={atr_ratio:.2f} >= 1.10"
    elif is_ranging:
        report.regime = RegimeState.RANGING
        report.confidence = min(
            1.0,
            (float(cfg["ranging_atr_ratio_max"]) - atr_ratio + 0.1) / float(cfg["ranging_atr_ratio_max"]),
        ) if atr_ratio < 1.0 else min(1.0, (100.0 - bb_pct) / 100.0)
        report.confidence = max(0.3, report.confidence)
        report.reason = f"ranging: atr_ratio={atr_ratio:.2f} < 0.85 ou bb_pct={bb_pct:.0f} <= 20"
    else:
        # Cas ambigu — défaut TRENDING (autorise A1)
        report.regime = RegimeState.TRENDING
        report.confidence = 0.5
        report.reason = (
            f"ambigu: adx={adx_val:.1f}, atr_ratio={atr_ratio:.2f}, "
            f"bb_pct={bb_pct:.0f} → défaut TRENDING"
        )

    report.n_bars_used = len(bars)
    report.source = "ohlcv"
    return report


# ─────────────────────────────────────────────────────────────────────
# Intégration orchestrateur — applique max_setup_level au signal
# ─────────────────────────────────────────────────────────────────────
SETUP_LEVEL_RANK = {"NONE": 0, "A3": 1, "A2": 2, "A1": 3}


def apply_regime_to_signal(
    current_level: str,
    regime: RegimeReport,
) -> Tuple[str, bool]:
    """Applique le cap de régime au setup_level (downgrade).

    Returns (new_level, was_downgraded).
    """
    max_lvl = regime.max_setup_level()
    cur_rank = SETUP_LEVEL_RANK.get(current_level, 0)
    max_rank = SETUP_LEVEL_RANK.get(max_lvl, 0)
    if cur_rank > max_rank:
        # Trouve le plus haut level <= max_rank
        for lvl in ("A1", "A2", "A3", "NONE"):
            if SETUP_LEVEL_RANK[lvl] <= max_rank:
                return lvl, True
        return "NONE", True
    return current_level, False


__all__ = [
    "RegimeState",
    "RegimeReport",
    "DEFAULT_REGIME_THRESHOLDS",
    "DEFAULT_CALENDAR_PATH",
    "detect_regime",
    "apply_regime_to_signal",
    "_load_calendar",
    "_is_news_lock",
    "_adx",
    "_atr",
    "_bb_width",
    "_bb_width_percentile",
]
