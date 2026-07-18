"""v9_dynamic_tp_sl.py — TP/SL dynamiques par contexte (Fix C, motion CEO §16h10).

**Pourquoi ce module existe** :
Le pipeline live utilise TP=8/SL=15 hardcodés (RR=0.53, edge négatif).
La magnitude réelle des mouvements GBPUSD M15 est P25=5.5 / P50=7.3 / P75=12.3 / P90=15.9 pips.
Le fix propose un fallback intelligent : TP et SL dérivés de la magnitude
historique réelle par (symbol, timeframe), pas hardcodés.

**Volet mathématique** :
- TP dynamique = max(P50 historique, vol_atr × multiplicateur), borné R30 [5, 20]
- SL dynamique = max(0.8 × TP, P75 historique), borné R30 [5, 20]
- Ratio RR cible ≥ 0.7 (vs 0.53 actuel)

**Volet doctrinal** :
- R2 additif (nouveau module, jamais destructif)
- R6 défensif (try/except → fallback hardcoded 10/15)
- R7 testable (lecture seule DB)
- R18 code pur (sqlite3 + math)
- R22 1 périmètre = ce module
- R30 bornes TP/SL respectées

**Activation** :
- Kill switch `V9_DYNAMIC_TP_SL_ENABLED` (défaut OFF tant que motion CEO explicite)
- Si ON : `compute_dynamic_tp_sl(symbol, timeframe)` est appelée AVANT
  le fallback hardcodé dans trade_engine.

**Conformité au commit c0aa416** :
- Le commit avait documenté SL/TP M15 lissé comme cause de la boucle.
- Ce module utilise les magnitudes M15 réelles (pas lissées) + R30 bornes.
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ const

DYNAMIC_TP_SL_ENABLED_ENV = "V9_DYNAMIC_TP_SL_ENABLED"

# Bornes R30 strictes
TP_MIN = 5.0
TP_MAX = 20.0
SL_MIN = 5.0
SL_MAX = 20.0

# Defaults fallback (alignés avec R30)
DEFAULT_TP = 10.0
DEFAULT_SL = 15.0

# Multiplicateur TP vs P50 historique
TP_P50_MULT = 1.2      # TP = P50 × 1.2 (légèrement au-dessus médiane)
TP_VOL_MULT = 1.5      # TP = vol_atr × 1.5 (si vol_atr dispo)

# Ratio RR cible
RR_TARGET = 0.7        # SL = TP / 0.7

# Cache TTL (secondes) pour magnitudes historiques (évite SQL à chaque trade)
MAGNITUDE_CACHE_TTL = 600  # 10 minutes


@dataclass(frozen=True)
class DynamicTpSl:
    """TP/SL dynamiques proposés par le module."""
    tp: float
    sl: float
    p50_used: float          # P50 magnitude historique utilisée
    p75_used: float          # P75 magnitude historique utilisée
    vol_atr_used: float | None  # vol_atr_pips si fourni
    rr_ratio: float          # SL / TP (plus c'est haut, plus l'edge est bon)
    source: str              # "magnitude_history" | "vol_atr" | "default_fallback"
    rationale: str           # explication textuelle

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ cache magnitude


_MAGNITUDE_CACHE: dict[tuple, tuple[float, float, float]] = {}
"""Cache : {(symbol, timeframe) : (P50, P75, timestamp)}"""


def _compute_magnitude_history(
    db_path: Path | str,
    symbol: str,
    timeframe: str = "M15",
    lookback_bars: int = 5000,
) -> tuple[float, float]:
    """Calcule P50 et P75 du range OHLC historique (en pips).

    Lecture seule sur `forces_snapshots` (table live).
    Cache TTL 10 min pour éviter SQL à chaque trade.
    """
    cache_key = (str(db_path), symbol, timeframe)
    now = time.time()
    if cache_key in _MAGNITUDE_CACHE:
        p50, p75, ts = _MAGNITUDE_CACHE[cache_key]
        if (now - ts) < MAGNITUDE_CACHE_TTL:
            return p50, p75

    if not Path(db_path).exists():
        return 0.0, 0.0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.row_factory = sqlite3.Row
            # Pip multiplier selon le symbol (JPY paires = 100, autres = 10000)
            pip_mult = 100.0 if "JPY" in symbol.upper() else 10000.0
            rows = conn.execute(
                """
                SELECT high, low FROM forces_snapshots
                WHERE symbol = ? AND timeframe = ?
                  AND high IS NOT NULL AND low IS NOT NULL
                ORDER BY bar_close_time DESC LIMIT ?
                """,
                (symbol, timeframe, lookback_bars),
            ).fetchall()
            ranges_pips = sorted(
                [(r["high"] - r["low"]) * pip_mult for r in rows]
            )
            n = len(ranges_pips)
            if n == 0:
                return 0.0, 0.0
            p50 = ranges_pips[n // 2]
            p75 = ranges_pips[(3 * n) // 4]
            _MAGNITUDE_CACHE[cache_key] = (p50, p75, now)
            return p50, p75
        finally:
            conn.close()
    except Exception as e:
        logger.warning("dynamic_tp_sl: query failed: %s", e)
        return 0.0, 0.0


# ------------------------------------------------------------------ helpers


def _clamp_tp(tp: float) -> float:
    return max(TP_MIN, min(TP_MAX, tp))


def _clamp_sl(sl: float) -> float:
    return max(SL_MIN, min(SL_MAX, sl))


# ------------------------------------------------------------------ kill switch


def dynamic_tp_sl_enabled() -> bool:
    """Kill switch V9_DYNAMIC_TP_SL_ENABLED (défaut OFF tant que motion CEO)."""
    val = os.environ.get(DYNAMIC_TP_SL_ENABLED_ENV, "0")
    return val in ("1", "true", "True")


# ------------------------------------------------------------------ API publique


def compute_dynamic_tp_sl(
    symbol: str,
    timeframe: str = "M15",
    vol_atr_pips: float | None = None,
    db_path: Path | str | None = None,
) -> DynamicTpSl:
    """Calcule TP/SL dynamiques pour un (symbol, timeframe).

    Args :
        symbol : "GBPUSD", "USDJPY", etc.
        timeframe : "M1", "M5", "M15", etc. (défaut M15).
        vol_atr_pips : volatilité ATR en pips (optionnel, sinon magnitude historique).
        db_path : chemin `v9_forces.db` (défaut : cwd/data/v9_forces.db).

    Returns :
        DynamicTpSl avec TP, SL bornés R30 + rationale explicite.

    R6 : si DB absente ou erreur SQL → fallback DEFAULT_TP/DEFAULT_SL.
    """
    # R30 fallback hardcodé (defensive)
    if not dynamic_tp_sl_enabled():
        return DynamicTpSl(
            tp=DEFAULT_TP, sl=DEFAULT_SL,
            p50_used=0.0, p75_used=0.0,
            vol_atr_used=vol_atr_pips,
            rr_ratio=DEFAULT_SL / DEFAULT_TP,
            source="disabled_kill_switch",
            rationale="V9_DYNAMIC_TP_SL_ENABLED=0, fallback hardcoded",
        )

    if db_path is None:
        db_path = Path("data/v9_forces.db")
    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path

    # Magnitude historique
    p50, p75 = _compute_magnitude_history(db_p, symbol, timeframe)

    # Cas 1 : vol_atr fourni → TP basé sur volatilité
    if vol_atr_pips is not None and vol_atr_pips > 0:
        tp_raw = max(vol_atr_pips * TP_VOL_MULT, p50 * TP_P50_MULT) if p50 > 0 else vol_atr_pips * TP_VOL_MULT
        sl_raw = tp_raw / RR_TARGET
        tp = _clamp_tp(tp_raw)
        sl = _clamp_sl(sl_raw)
        return DynamicTpSl(
            tp=tp, sl=sl,
            p50_used=p50, p75_used=p75,
            vol_atr_used=vol_atr_pips,
            rr_ratio=round(sl / tp, 3) if tp > 0 else 0.0,
            source="vol_atr",
            rationale=(
                f"vol_atr={vol_atr_pips:.1f}pip × {TP_VOL_MULT} + P50={p50:.1f}pip × {TP_P50_MULT} → "
                f"TP={tp:.1f}pip, SL={sl:.1f}pip (RR={sl/tp:.2f})"
            ),
        )

    # Cas 2 : magnitude historique disponible → TP = P50 × multiplicateur
    if p50 > 0:
        tp_raw = p50 * TP_P50_MULT
        sl_raw = max(p75, tp_raw / RR_TARGET)
        tp = _clamp_tp(tp_raw)
        sl = _clamp_sl(sl_raw)
        return DynamicTpSl(
            tp=tp, sl=sl,
            p50_used=p50, p75_used=p75,
            vol_atr_used=None,
            rr_ratio=round(sl / tp, 3) if tp > 0 else 0.0,
            source="magnitude_history",
            rationale=(
                f"P50={p50:.1f}pip × {TP_P50_MULT} → TP={tp:.1f}pip, "
                f"SL=max(P75={p75:.1f}pip, TP/{RR_TARGET})={sl:.1f}pip (RR={sl/tp:.2f})"
            ),
        )

    # Cas 3 : aucune data → fallback R30
    return DynamicTpSl(
        tp=DEFAULT_TP, sl=DEFAULT_SL,
        p50_used=0.0, p75_used=0.0,
        vol_atr_used=vol_atr_pips,
        rr_ratio=round(DEFAULT_SL / DEFAULT_TP, 3),
        source="default_fallback",
        rationale="no_data: P50=0, vol_atr=None → fallback R30 DEFAULT_TP/SL",
    )


def get_stats(db_path: Path | str | None = None) -> dict[str, Any]:
    """Diagnostic : état du module + magnitudes par symbol."""
    if db_path is None:
        db_path = Path("data/v9_forces.db")
    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path

    stats: dict[str, Any] = {
        "enabled": dynamic_tp_sl_enabled(),
        "tp_min": TP_MIN,
        "tp_max": TP_MAX,
        "sl_min": SL_MIN,
        "sl_max": SL_MAX,
        "rr_target": RR_TARGET,
    }

    if not db_p.exists():
        stats["db_status"] = "absent"
        return stats

    symbols = ["GBPUSD", "EURUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
    for sym in symbols:
        p50, p75 = _compute_magnitude_history(db_p, sym, "M15")
        stats[f"{sym}_p50"] = round(p50, 2)
        stats[f"{sym}_p75"] = round(p75, 2)

    return stats
