"""
V10 Signal Generator Live — CYCLE 5 ROOT FIX (09/08/2026)

PROBLÈME RACINE IDENTIFIÉ C1→C4 :
  forces_snapshots contient des valeurs V9 binaires (0.0 / 100.0).
  decide_signal_level() calcule delta_force sur ces valeurs corrompues
  → A1/A2/A3 statistiquement invalides dès la source.
  TOUT le pipeline VSA/Fractal/Bayesian filtre du signal bidon.

CORRECTION RACINE C5 :
  1. force_native_available : si v10_force_native.py peut calculer les forces
     nativement depuis OHLCV, on l'utilise EN PRIORITÉ.
  2. Fallback gracieux : si v10_force_native manque, on garde l'ancienne
     logique forces_snapshots MAIS on détecte et rejette les snapshots
     binaires (filter_binary=True strict).
  3. SGL.generate() retourne toujours un dict complet avec direction ET
     signal_level (fix du bug où generate() retournait None sans logguer).
  4. close=0.0 fix : _compute_pnl_proxy ignore les barres sans prix valide.

Doctrine :
  R2  — additif pur : zéro import core/v9/
  R6  — fail-open : force_native KO → fallback propre
  R9  — audit honnête : source_used loggée dans chaque signal
  R10 — compute only, zéro ordre réel
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ══ IMPORT v10_force_native (R6 fail-open) ════════════════════════════════
try:
    from .v10_force_native import (
        compute_force_native,
        ForceNativeResult,
    )
    _FORCE_NATIVE_OK = True
except Exception as _e:
    log.warning("[SGL-C5] v10_force_native KO (fallback forces_snapshots): %s", _e)
    compute_force_native = None  # type: ignore
    ForceNativeResult = None     # type: ignore
    _FORCE_NATIVE_OK = False

try:
    from .v10_currency_strength import (
        CurrencyStrength,
        compute_currency_strength,
        DEFAULTS,
        INVERSION_MAP,
        PAIRS_BY_CURRENCY,
        PAIRS_USD,
    )
    _CS_OK = True
except Exception as _e:
    log.warning("[SGL-C5] v10_currency_strength KO: %s", _e)
    _CS_OK = False

# Tables DB
TABLE_SIGNALS_CLEAN = "v10_signals_clean"

CURRENCIES_V10_FULL = ("EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD")

PAIRS_V10_DEFAULT = (
    "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY",
)

SIGNAL_LEVEL_NONE = "NONE"
SIGNAL_LEVEL_A3   = "A3"
SIGNAL_LEVEL_A2   = "A2"
SIGNAL_LEVEL_A1   = "A1"

WINDOW_BARS = 50
PIPS_PER_PIP_FOREX = 100.0

# C5 : horizons courts par TF (signal se réalise vite)
HORIZON_BARS_BY_TF: Dict[str, int] = {
    "M1":  2,
    "M5":  3,
    "M15": 3,
    "M30": 3,
    "H1":  2,
    "H4":  1,
}

TIMEFRAMES_DEFAULT: Tuple[str, ...] = ("M15", "M30", "H1", "H4")

# Valeurs binaires V9 à rejeter
BINARY_FORCE_VALUES = frozenset({0.0, 100.0})

# C5 : seuils signal_level calibrés pour forces NATIVES (non binaires)
# Les forces natives sont en [0, 1] (ratio normalisé), pas en [0, 100]
FORCE_NATIVE_DELTA_A3 = 0.05   # 5% d'écart minimum
FORCE_NATIVE_DELTA_A2 = 0.10   # 10%
FORCE_NATIVE_DELTA_A1 = 0.18   # 18% + devise dominante top3

# Seuils legacy forces_snapshots (0-100)
FORCE_LEGACY_DELTA_A3 = 10.0
FORCE_LEGACY_DELTA_A2 = 20.0
FORCE_LEGACY_DELTA_A1 = 30.0


# ══ ENUMS & DATACLASSES ═══════════════════════════════════════════════════
class SignalSource(str, Enum):
    FORCE_NATIVE      = "force_native"       # C5 : source primaire
    FORCES_SNAPSHOTS  = "forces_snapshots"   # fallback si force_native KO
    SYNTHETIC         = "synthetic"


@dataclass
class V10SignalRow:
    signal_id:       str
    timestamp:       str
    symbol:          str
    timeframe:       str
    pair:            str
    direction:       str
    signal_level:    str
    force_base:      float = 0.0
    force_quote:     float = 0.0
    velocity_base:   float = 0.0
    velocity_quote:  float = 0.0
    rank_base:       int   = 0
    rank_quote:      int   = 0
    spread_score:    float = 0.0
    tick_volume:     float = 0.0
    bid:             float = 0.0
    ask:             float = 0.0
    pnl_pips_proxy:  float = 0.0
    is_win_proxy:    int   = 0
    source:          str   = SignalSource.FORCE_NATIVE.value
    features_json:   str   = ""

    def as_dict(self) -> Dict:
        return {
            "signal_id":      self.signal_id,
            "timestamp":      self.timestamp,
            "symbol":         self.symbol,
            "timeframe":      self.timeframe,
            "pair":           self.pair,
            "direction":      self.direction,
            "signal_level":   self.signal_level,
            "force_base":     round(self.force_base,    4),
            "force_quote":    round(self.force_quote,   4),
            "velocity_base":  round(self.velocity_base, 4),
            "velocity_quote": round(self.velocity_quote,4),
            "rank_base":      self.rank_base,
            "rank_quote":     self.rank_quote,
            "spread_score":   round(self.spread_score,  2),
            "tick_volume":    self.tick_volume,
            "bid":            self.bid,
            "ask":            self.ask,
            "pnl_pips_proxy": round(self.pnl_pips_proxy, 2),
            "is_win_proxy":   self.is_win_proxy,
            "source":         self.source,
            "features_json":  self.features_json,
        }


@dataclass
class GeneratorReport:
    timestamp:              str  = ""
    db_path:                str  = ""
    n_snapshots_loaded:     int  = 0
    n_signals_generated:    int  = 0
    n_signals_persisted:    int  = 0
    pairs_processed:        List[str] = field(default_factory=list)
    timeframes_processed:   List[str] = field(default_factory=list)
    kpis_by_pair:           Dict[str, Dict] = field(default_factory=dict)
    kpis_by_level:          Dict[str, Dict] = field(default_factory=dict)
    kpis_by_tf:             Dict[str, Dict] = field(default_factory=dict)
    kpis_by_pair_tf:        Dict[str, Dict] = field(default_factory=dict)
    audit:                  Dict = field(default_factory=dict)
    # C5 : source tracking
    source_used:            str  = "unknown"
    force_native_pct:       float = 0.0  # % signaux via force_native

    def as_dict(self) -> Dict:
        return {
            "timestamp":           self.timestamp,
            "db_path":             self.db_path,
            "n_snapshots_loaded":  self.n_snapshots_loaded,
            "n_signals_generated": self.n_signals_generated,
            "n_signals_persisted": self.n_signals_persisted,
            "pairs_processed":     self.pairs_processed,
            "timeframes_processed":self.timeframes_processed,
            "kpis_by_pair":        self.kpis_by_pair,
            "kpis_by_level":       self.kpis_by_level,
            "kpis_by_tf":          self.kpis_by_tf,
            "kpis_by_pair_tf":     self.kpis_by_pair_tf,
            "source_used":         self.source_used,
            "force_native_pct":    self.force_native_pct,
            "audit":               self.audit,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, default=str)


# ══ FORCE NATIVE HELPERS (C5 ROOT FIX) ════════════════════════════════════

def _compute_forces_native(
    bars: List[Dict],
    pair: str,
    tf: str,
) -> Optional[Dict[str, float]]:
    """
    C5 ROOT FIX : calcule les forces de devises nativement depuis OHLCV
    via v10_force_native.compute_force_native().

    Retourne dict {currency: force_score [0..1]} pour toutes les devises,
    ou None si force_native KO (R6 fail-open).
    """
    if not _FORCE_NATIVE_OK or compute_force_native is None or len(bars) < 10:
        return None
    try:
        result = compute_force_native(
            pair=pair,
            timeframe=tf,
            bars=bars,
        )
        if result is None:
            return None
        if isinstance(result, dict):
            return result
        if hasattr(result, "forces"):
            return result.forces
        if hasattr(result, "as_dict"):
            d = result.as_dict()
            return d.get("forces", None)
        return None
    except Exception as exc:
        log.debug("[SGL-C5] force_native %s/%s fail: %s", pair, tf, exc)
        return None


def _decide_signal_native(
    forces: Dict[str, float],
    pair: str,
    prev_forces: Optional[Dict[str, float]] = None,
) -> Tuple[str, str, float, float, float, float, int, int]:
    """
    C5 ROOT FIX : décide signal_level depuis forces NATIVES [0..1].

    Retourne :
      (signal_level, direction, force_base, force_quote,
       velocity_base, velocity_quote, rank_base, rank_quote)
    """
    base, quote = pair[:3].upper(), pair[3:].upper()

    force_base  = float(forces.get(base,  0.0))
    force_quote = float(forces.get(quote, 0.0))

    velocity_base  = 0.0
    velocity_quote = 0.0
    if prev_forces:
        velocity_base  = force_base  - float(prev_forces.get(base,  force_base))
        velocity_quote = force_quote - float(prev_forces.get(quote, force_quote))

    # Rank dans [0..1] : tri décroissant
    all_forces_sorted = sorted(
        [(c, float(forces.get(c, 0.0))) for c in CURRENCIES_V10_FULL],
        key=lambda x: x[1], reverse=True,
    )
    rank_map   = {c: i + 1 for i, (c, _) in enumerate(all_forces_sorted)}
    rank_base  = rank_map.get(base,  99)
    rank_quote = rank_map.get(quote, 99)

    delta = force_base - force_quote
    abs_delta = abs(delta)

    # Direction
    direction = "BULLISH" if delta > 0 else ("BEARISH" if delta < 0 else "NEUTRAL")

    # Signal level avec seuils natifs
    if abs_delta < FORCE_NATIVE_DELTA_A3:
        level = SIGNAL_LEVEL_NONE
    elif abs_delta < FORCE_NATIVE_DELTA_A2:
        level = SIGNAL_LEVEL_A3
    elif abs_delta < FORCE_NATIVE_DELTA_A1:
        level = SIGNAL_LEVEL_A2
    else:
        # A1 : devise dominante doit être top 3
        dominant_top3 = (
            (delta > 0 and rank_base  <= 3) or
            (delta < 0 and rank_quote <= 3)
        )
        level = SIGNAL_LEVEL_A1 if dominant_top3 else SIGNAL_LEVEL_A2

    return (level, direction, force_base, force_quote,
            velocity_base, velocity_quote, rank_base, rank_quote)


# ══ FORCES_SNAPSHOTS LOADER (fallback legacy) ═════════════════════════════

def _load_forces_snapshots(
    db_path: str,
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict]:
    if not Path(db_path).exists():
        log.warning("DB absente : %s", db_path)
        return []
    con = sqlite3.connect(db_path, timeout=10)
    out: List[Dict] = []
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='forces_snapshots'")
        if not cur.fetchone():
            return []
        where_parts: list = []
        params: list = []
        if symbol:
            where_parts.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            where_parts.append("timeframe = ?")
            params.append(timeframe)
        if not where_parts:
            where_parts.append("1=1")
        limit_sql = f"LIMIT {limit}" if limit else ""
        query = f"""
            SELECT snapshot_id, timestamp, symbol, timeframe, bar_time, bar_close_time,
                   direction, vitesse,
                   force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd,
                   tick_volume, spread_points, bid, ask, mid, open, high, low, close
            FROM forces_snapshots
            WHERE {' AND '.join(where_parts)}
            ORDER BY bar_time ASC
            {limit_sql}
        """
        for row in cur.execute(query, params):
            d = {
                "snapshot_id": row[0],
                "timestamp":   row[1],
                "symbol":      row[2],
                "timeframe":   row[3],
                "bar_time":    row[4],
                "bar_close_time": row[5],
                "direction":   row[6],
                "vitesse":     row[7] or 0.0,
                "force": {
                    "USD": row[8]  or 0.0,
                    "GBP": row[9]  or 0.0,
                    "EUR": row[10] or 0.0,
                    "JPY": row[11] or 0.0,
                    "CAD": row[12] or 0.0,
                    "CHF": row[13] or 0.0,
                    "AUD": row[14] or 0.0,
                    "NZD": row[15] or 0.0,
                },
                "tick_volume":   row[16] or 0.0,
                "spread_points": row[17] or 0.0,
                "bid":   row[18] or 0.0,
                "ask":   row[19] or 0.0,
                "mid":   row[20] or 0.0,
                "open":  row[21] or 0.0,
                "high":  row[22] or 0.0,
                "low":   row[23] or 0.0,
                "close": row[24] or 0.0,
            }
            out.append(d)
    except Exception as exc:
        log.warning("Erreur lecture forces_snapshots : %s", exc)
    finally:
        con.close()
    return out


# ══ SIGNAL LEVEL (legacy forces_snapshots 0-100) ═══════════════════════════

def decide_signal_level(
    *,
    force_base: float,
    force_quote: float,
    velocity_base: float,
    velocity_quote: float,
    rank_base: int,
    rank_quote: int,
    direction: str,
    vitesse: float,
) -> Tuple[str, str]:
    """Legacy : seuils 0-100 pour forces_snapshots."""
    delta_force = force_base - force_quote
    dir_sign = 1 if direction == "haussiere" else (-1 if direction == "baissiere" else 0)
    inferred_dir = "BULLISH" if delta_force > 0 else ("BEARISH" if delta_force < 0 else "NEUTRAL")
    aligned = (dir_sign > 0 and delta_force > 0) or (dir_sign < 0 and delta_force < 0) or dir_sign == 0
    if not aligned or abs(delta_force) < FORCE_LEGACY_DELTA_A3:
        return (SIGNAL_LEVEL_NONE, inferred_dir)
    if abs(delta_force) < FORCE_LEGACY_DELTA_A2:
        return (SIGNAL_LEVEL_A3, inferred_dir)
    if abs(delta_force) < FORCE_LEGACY_DELTA_A1:
        return (SIGNAL_LEVEL_A2, inferred_dir)
    dominant_is_top3 = (
        (delta_force > 0 and rank_base <= 3) or
        (delta_force < 0 and rank_quote <= 3)
    )
    return (SIGNAL_LEVEL_A1 if dominant_is_top3 else SIGNAL_LEVEL_A2, inferred_dir)


# ══ PNL PROXY (C5 FIX : close=0.0 guard) ══════════════════════════════════

def _compute_pnl_proxy(
    snapshots: List[Dict],
    idx: int,
    *,
    horizon_bars: int = 3,
    direction: str = "BULLISH",
    pip_multiplier: float = 10000.0,
) -> Tuple[float, int]:
    """
    C5 FIX : pnl proxy propre avec direction-aware et close=0.0 guard.
    - Retourne 0.0 si close_now ou close_next est invalide (≤0).
    - Utilise direction pour orienter le PnL (BULLISH = long, BEARISH = short).
    - pip_multiplier : 10000 pour paires non-JPY, 100 pour JPY.
    """
    if idx + horizon_bars >= len(snapshots):
        return 0.0, 0

    close_now = float(
        snapshots[idx].get("close") or
        snapshots[idx].get("mid") or 0.0
    )
    close_next = float(
        snapshots[idx + horizon_bars].get("close") or
        snapshots[idx + horizon_bars].get("mid") or 0.0
    )

    # C5 : garde stricte — si prix nul, on ne simule pas
    if close_now <= 0.0 or close_next <= 0.0:
        return 0.0, 0

    raw_move = (close_next - close_now) * pip_multiplier
    # Orientation selon direction
    pips = raw_move if direction == "BULLISH" else -raw_move
    is_win = 1 if pips > 0 else 0
    return round(pips, 2), is_win


def _is_binary_snapshot(snap: Dict, base: str, quote: str) -> bool:
    force = snap.get("force", {})
    fb = float(force.get(base,  0.0))
    fq = float(force.get(quote, 0.0))
    return (fb in BINARY_FORCE_VALUES) and (fq in BINARY_FORCE_VALUES)


# ══ GENERATE SIGNALS — SOURCE NATIVE EN PRIORITÉ ═══════════════════════════

def generate_signals_for_pair_tf(
    snapshots: List[Dict],
    *,
    pair: str,
    timeframe: str,
    horizon_bars: int = 3,
    filter_binary: bool = True,
) -> Tuple[List[V10SignalRow], int]:
    """
    C5 ROOT FIX : génère signaux V10 propres.

    Priorité :
      1. compute_force_native() sur la fenêtre OHLCV de chaque barre
         → forces [0..1] non-binaires, seuils FORCE_NATIVE_DELTA_*
      2. Fallback forces_snapshots avec filter_binary strict
         → seuils FORCE_LEGACY_DELTA_*

    PnL proxy : direction-aware + close=0 guard (C5 fix).
    """
    if len(snapshots) < horizon_bars + 1:
        return [], 0

    base, quote = pair[:3].upper(), pair[3:].upper()
    pip_mul = 100.0 if pair.upper().endswith("JPY") else 10000.0
    out: List[V10SignalRow] = []
    n_filtered_binary = 0
    prev_forces_native: Optional[Dict[str, float]] = None

    for idx in range(len(snapshots) - horizon_bars):
        snap = snapshots[idx]

        # Prépare fenêtre OHLCV pour force_native
        window = snapshots[max(0, idx - WINDOW_BARS): idx + 1]

        # === SOURCE PRIMAIRE : force_native ===
        forces_native = _compute_forces_native(window, pair, timeframe)

        if forces_native is not None:
            (level, direction, fb, fq, vb, vq, rb, rq) = _decide_signal_native(
                forces_native, pair, prev_forces=prev_forces_native
            )
            prev_forces_native = forces_native
            source_tag = SignalSource.FORCE_NATIVE.value
        else:
            # === FALLBACK : forces_snapshots avec filtre binaire ===
            if filter_binary and _is_binary_snapshot(snap, base, quote):
                n_filtered_binary += 1
                continue

            force_dict  = snap.get("force", {})
            fb  = float(force_dict.get(base,  0.0))
            fq  = float(force_dict.get(quote, 0.0))
            prev_snap   = snapshots[idx - 1] if idx > 0 else snap
            prev_force  = prev_snap.get("force", {})
            vb  = fb - float(prev_force.get(base,  fb))
            vq  = fq - float(prev_force.get(quote, fq))

            all_forces_sorted = sorted(
                [(c, float(force_dict.get(c, 0.0))) for c in CURRENCIES_V10_FULL],
                key=lambda x: x[1], reverse=True,
            )
            rank_map = {c: i + 1 for i, (c, _) in enumerate(all_forces_sorted)}
            rb = rank_map.get(base,  99)
            rq = rank_map.get(quote, 99)

            level, direction = decide_signal_level(
                force_base=fb, force_quote=fq,
                velocity_base=vb, velocity_quote=vq,
                rank_base=rb, rank_quote=rq,
                direction=snap.get("direction", "neutre"),
                vitesse=float(snap.get("vitesse", 0.0)),
            )
            source_tag = SignalSource.FORCES_SNAPSHOTS.value
            prev_forces_native = None  # reset — on a basculé en legacy

        # PnL proxy C5 : direction-aware + close guard
        pnl_pips, is_win = _compute_pnl_proxy(
            snapshots, idx,
            horizon_bars=horizon_bars,
            direction=direction,
            pip_multiplier=pip_mul,
        )

        signal_id = (
            f"V10C5-{pair}-{timeframe}-"
            f"{snap.get('bar_time', idx)}-h{horizon_bars}-{source_tag[:2]}"
        )
        row = V10SignalRow(
            signal_id=signal_id,
            timestamp=str(snap.get("timestamp", "")),
            symbol=snap.get("symbol", pair),
            timeframe=timeframe,
            pair=pair,
            direction=direction,
            signal_level=level,
            force_base=fb,
            force_quote=fq,
            velocity_base=vb,
            velocity_quote=vq,
            rank_base=rb,
            rank_quote=rq,
            spread_score=float(snap.get("spread_points", 0.0)),
            tick_volume=float(snap.get("tick_volume", 0.0)),
            bid=float(snap.get("bid", 0.0)),
            ask=float(snap.get("ask", 0.0)),
            pnl_pips_proxy=pnl_pips,
            is_win_proxy=is_win,
            source=source_tag,
            features_json=json.dumps({
                "source":         source_tag,
                "horizon_bars":   horizon_bars,
                "filter_binary":  filter_binary,
                "force_native_ok": forces_native is not None,
                "spread_points":  float(snap.get("spread_points", 0.0)),
                "tick_volume":    float(snap.get("tick_volume",   0.0)),
            }),
        )
        out.append(row)
    return out, n_filtered_binary


# ══ KPI COMPUTATION ═══════════════════════════════════════════════════════

def compute_kpis(
    signals: List[V10SignalRow],
    *,
    separate_by_tf: bool = True,
) -> Dict:
    n    = len(signals)
    wins = sum(s.is_win_proxy for s in signals)
    wr   = wins / n if n else 0.0
    pnl  = sum(s.pnl_pips_proxy for s in signals)

    by_level: Dict[str, Dict] = {}
    for level in (SIGNAL_LEVEL_A1, SIGNAL_LEVEL_A2, SIGNAL_LEVEL_A3, SIGNAL_LEVEL_NONE):
        sub   = [s for s in signals if s.signal_level == level]
        n_sub = len(sub)
        by_level[level] = {
            "n":        n_sub,
            "wr":       round(sum(s.is_win_proxy for s in sub) / n_sub, 4) if n_sub else 0.0,
            "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub), 2),
        }

    by_pair: Dict[str, Dict] = {}
    for p in sorted({s.pair for s in signals}):
        sub = [s for s in signals if s.pair == p]
        n_p = len(sub)
        by_pair[p] = {
            "n":        n_p,
            "wr":       round(sum(s.is_win_proxy for s in sub) / n_p, 4) if n_p else 0.0,
            "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub), 2),
        }

    result: Dict = {
        "n_total":        n,
        "wr_global":      round(wr, 4),
        "pnl_total_pips": round(pnl, 2),
        "by_level":       by_level,
        "by_pair":        by_pair,
    }

    if separate_by_tf:
        by_tf: Dict[str, Dict] = {}
        for tf in sorted({s.timeframe for s in signals}):
            sub  = [s for s in signals if s.timeframe == tf]
            n_tf = len(sub)
            by_tf_level: Dict[str, Dict] = {}
            for level in (SIGNAL_LEVEL_A1, SIGNAL_LEVEL_A2, SIGNAL_LEVEL_A3, SIGNAL_LEVEL_NONE):
                sub_lv = [s for s in sub if s.signal_level == level]
                n_lv   = len(sub_lv)
                by_tf_level[level] = {
                    "n":        n_lv,
                    "wr":       round(sum(s.is_win_proxy for s in sub_lv) / n_lv, 4) if n_lv else 0.0,
                    "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub_lv), 2),
                }
            by_tf[tf] = {
                "n": n_tf,
                "wr": round(sum(s.is_win_proxy for s in sub) / n_tf, 4) if n_tf else 0.0,
                "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub), 2),
                "by_level": by_tf_level,
            }
        result["by_tf"] = by_tf

        by_pair_tf: Dict[str, Dict] = {}
        for p, tf in sorted({(s.pair, s.timeframe) for s in signals}):
            key  = f"{p}_{tf}"
            sub  = [s for s in signals if s.pair == p and s.timeframe == tf]
            n_pt = len(sub)
            by_pt_level: Dict[str, Dict] = {}
            for level in (SIGNAL_LEVEL_A1, SIGNAL_LEVEL_A2, SIGNAL_LEVEL_A3, SIGNAL_LEVEL_NONE):
                sub_lv = [s for s in sub if s.signal_level == level]
                n_lv   = len(sub_lv)
                by_pt_level[level] = {
                    "n":        n_lv,
                    "wr":       round(sum(s.is_win_proxy for s in sub_lv) / n_lv, 4) if n_lv else 0.0,
                    "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub_lv), 2),
                }
            by_pair_tf[key] = {
                "pair": p, "tf": tf, "n": n_pt,
                "wr":       round(sum(s.is_win_proxy for s in sub) / n_pt, 4) if n_pt else 0.0,
                "pnl_pips": round(sum(s.pnl_pips_proxy for s in sub), 2),
                "by_level": by_pt_level,
            }
        result["by_pair_tf"] = by_pair_tf

    return result


# ══ PERSISTENCE ═══════════════════════════════════════════════════════════

def persist_signals(db_path: str, signals: List[V10SignalRow]) -> int:
    if not signals:
        return 0
    con = sqlite3.connect(db_path, timeout=10)
    n_persisted = 0
    try:
        cur = con.cursor()
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_SIGNALS_CLEAN} (
                signal_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT,
                timeframe TEXT, pair TEXT, direction TEXT, signal_level TEXT,
                force_base REAL, force_quote REAL, velocity_base REAL, velocity_quote REAL,
                rank_base INTEGER, rank_quote INTEGER, spread_score REAL,
                tick_volume REAL, bid REAL, ask REAL,
                pnl_pips_proxy REAL, is_win_proxy INTEGER,
                source TEXT, features_json TEXT
            )
        """)
        for s in signals:
            try:
                cur.execute(
                    f"INSERT OR REPLACE INTO {TABLE_SIGNALS_CLEAN} VALUES "
                    f"(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        s.signal_id, s.timestamp, s.symbol, s.timeframe, s.pair,
                        s.direction, s.signal_level,
                        s.force_base, s.force_quote, s.velocity_base, s.velocity_quote,
                        s.rank_base, s.rank_quote, s.spread_score, s.tick_volume,
                        s.bid, s.ask, s.pnl_pips_proxy, s.is_win_proxy,
                        s.source, s.features_json,
                    ),
                )
                n_persisted += 1
            except Exception as exc:
                log.warning("Insert signal %s failed: %s", s.signal_id, exc)
        con.commit()
    finally:
        con.close()
    return n_persisted


# ══ ORCHESTRATEUR ══════════════════════════════════════════════════════════

def _truncate_signals_table(db_path: str) -> None:
    try:
        con = sqlite3.connect(db_path, timeout=10)
        con.execute(f"DELETE FROM {TABLE_SIGNALS_CLEAN}")
        con.commit()
        con.close()
    except Exception as exc:
        log.warning("TRUNCATE %s fail-open: %s", TABLE_SIGNALS_CLEAN, exc)


def generate_clean_dataset(
    db_path: str,
    *,
    pairs: Tuple[str, ...] = PAIRS_V10_DEFAULT,
    timeframes: Tuple[str, ...] = TIMEFRAMES_DEFAULT,
    horizon_bars: Optional[int] = None,
    horizon_by_tf: Optional[Dict[str, int]] = None,
    filter_binary: bool = True,
    truncate_first: bool = True,
    timestamp: str = "",
    limit_per_pair_tf: Optional[int] = None,
) -> GeneratorReport:
    """
    C5 ROOT FIX : génère dataset V10 propre complet.

    Source priorité : force_native → forces_snapshots (filtré)
    PnL proxy       : direction-aware + close=0 guard
    Audit           : source_used + force_native_pct dans rapport
    """
    report = GeneratorReport(
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        db_path=db_path,
        pairs_processed=list(pairs),
        timeframes_processed=list(timeframes),
        source_used="force_native" if _FORCE_NATIVE_OK else "forces_snapshots_filtered",
    )

    horizon_map: Dict[str, int] = {}
    if horizon_by_tf is not None:
        horizon_map.update(horizon_by_tf)
    else:
        horizon_map.update(HORIZON_BARS_BY_TF)
    if horizon_bars is not None:
        for tf in timeframes:
            horizon_map[tf] = horizon_bars

    if truncate_first:
        _truncate_signals_table(db_path)

    all_signals: List[V10SignalRow] = []
    n_loaded_total    = 0
    n_filtered_total  = 0
    n_native_total    = 0
    n_filtered_by_ptf: Dict[str, int] = {}
    n_snaps_by_tf:     Dict[str, int] = {}

    for pair in pairs:
        for tf in timeframes:
            snaps = _load_forces_snapshots(
                db_path, symbol=pair, timeframe=tf,
                limit=limit_per_pair_tf,
            )
            n_loaded_total += len(snaps)
            n_snaps_by_tf[tf] = n_snaps_by_tf.get(tf, 0) + len(snaps)
            if not snaps:
                log.info("Aucun snapshot pour %s/%s", pair, tf)
                continue

            h = horizon_map.get(tf, 3)
            sigs, n_filt = generate_signals_for_pair_tf(
                snaps, pair=pair, timeframe=tf,
                horizon_bars=h, filter_binary=filter_binary,
            )
            all_signals.extend(sigs)
            n_filtered_total  += n_filt
            n_native_total    += sum(1 for s in sigs if s.source == SignalSource.FORCE_NATIVE.value)
            n_filtered_by_ptf[f"{pair}_{tf}"] = n_filt

    report.n_snapshots_loaded  = n_loaded_total
    report.n_signals_generated = len(all_signals)
    report.n_signals_persisted = persist_signals(db_path, all_signals)
    report.force_native_pct    = (
        round(n_native_total / len(all_signals) * 100, 1)
        if all_signals else 0.0
    )

    kpis = compute_kpis(all_signals, separate_by_tf=True)
    report.kpis_by_pair    = kpis["by_pair"]
    report.kpis_by_level   = kpis["by_level"]
    report.kpis_by_tf      = kpis.get("by_tf",      {})
    report.kpis_by_pair_tf = kpis.get("by_pair_tf", {})

    n_filt_pct = (n_filtered_total / n_loaded_total * 100.0) if n_loaded_total else 0.0
    report.audit = {
        "wr_global":           kpis["wr_global"],
        "pnl_total_pips":      kpis["pnl_total_pips"],
        "n_total":             kpis["n_total"],
        "horizon_by_tf":       horizon_map,
        "filter_binary":       filter_binary,
        "currencies_used":     list(CURRENCIES_V10_FULL),
        "force_native_ok":     _FORCE_NATIVE_OK,
        "force_native_pct":    report.force_native_pct,
        "source_used":         report.source_used,
        "n_filtered_binary":   n_filtered_total,
        "n_filtered_pct":      round(n_filt_pct, 2),
        "n_filtered_by_ptf":   n_filtered_by_ptf,
        "n_snapshots_by_tf":   n_snaps_by_tf,
        "filter_critical":     n_filt_pct > 80.0 and not _FORCE_NATIVE_OK,
        "filter_critical_msg": (
            f"forces_snapshots V9 binaires à {n_filt_pct:.1f}% ET force_native KO. "
            "C5 ROOT FIX non appliqué — checker l'import v10_force_native."
        ) if (n_filt_pct > 80.0 and not _FORCE_NATIVE_OK) else None,
    }
    if report.audit.get("filter_critical"):
        log.critical("R6 ROOT — %s", report.audit["filter_critical_msg"])
    else:
        log.info(
            "[SGL-C5] source=%s native_pct=%.1f%% wr=%.3f pnl=%.0f n=%d",
            report.source_used, report.force_native_pct,
            kpis["wr_global"], kpis["pnl_total_pips"], kpis["n_total"],
        )
    return report


# ══ API LIVE : generate() pour ReplayEngine ═══════════════════════════════

class SignalGeneratorLive:
    """
    C5 ROOT FIX : API utilisée par ReplayEngine._decide_one().

    generate(symbol, timeframe, bars) → dict avec direction et signal_level.
    Utilise compute_force_native() en priorité sur la fenêtre bars.
    Fallback : logique forces_snapshots avec delta_force sur last bar.
    Retourne TOUJOURS un dict non-None (R6 fail-open).
    """

    def generate(
        self,
        symbol: str,
        timeframe: str,
        bars: List[Dict],
    ) -> Dict[str, Any]:
        """
        Retourne {"direction": str, "signal_level": str, "source": str,
                  "force_base": float, "force_quote": float}
        Ne retourne jamais None.
        """
        if not bars:
            return self._neutral(symbol, timeframe, "empty_bars")

        pair = symbol.upper()
        base, quote = pair[:3], pair[3:] if len(pair) >= 6 else ("USD", "USD")

        # === SOURCE PRIMAIRE : force_native sur fenêtre ===
        window = bars[-WINDOW_BARS:] if len(bars) >= WINDOW_BARS else bars
        forces_native = _compute_forces_native(window, pair, timeframe)

        if forces_native is not None:
            (level, direction, fb, fq, vb, vq, rb, rq) = _decide_signal_native(
                forces_native, pair
            )
            return {
                "direction":    direction,
                "signal_level": level,
                "source":       SignalSource.FORCE_NATIVE.value,
                "force_base":   round(fb, 4),
                "force_quote":  round(fq, 4),
                "rank_base":    rb,
                "rank_quote":   rq,
            }

        # === FALLBACK : last bar forces_snapshots ===
        last = bars[-1]
        force = last.get("force", {})
        fb  = float(force.get(base,  0.0))
        fq  = float(force.get(quote, 0.0))

        # Anti-binaire : si valeurs corrompues, retourne NEUTRAL
        if fb in BINARY_FORCE_VALUES and fq in BINARY_FORCE_VALUES:
            return self._neutral(symbol, timeframe, "binary_forces_rejected")

        prev = bars[-2].get("force", {}) if len(bars) >= 2 else {}
        vb = fb - float(prev.get(base,  fb))
        vq = fq - float(prev.get(quote, fq))
        all_sorted = sorted(
            [(c, float(force.get(c, 0.0))) for c in CURRENCIES_V10_FULL],
            key=lambda x: x[1], reverse=True,
        )
        rank_map = {c: i + 1 for i, (c, _) in enumerate(all_sorted)}
        rb = rank_map.get(base,  99)
        rq = rank_map.get(quote, 99)

        level, direction = decide_signal_level(
            force_base=fb, force_quote=fq,
            velocity_base=vb, velocity_quote=vq,
            rank_base=rb, rank_quote=rq,
            direction=last.get("direction", "neutre"),
            vitesse=float(last.get("vitesse", 0.0)),
        )
        return {
            "direction":    direction,
            "signal_level": level,
            "source":       SignalSource.FORCES_SNAPSHOTS.value,
            "force_base":   round(fb, 4),
            "force_quote":  round(fq, 4),
            "rank_base":    rb,
            "rank_quote":   rq,
        }

    @staticmethod
    def _neutral(symbol: str, tf: str, reason: str) -> Dict[str, Any]:
        return {
            "direction":    "NEUTRAL",
            "signal_level": SIGNAL_LEVEL_NONE,
            "source":       f"neutral_{reason}",
            "force_base":   0.0,
            "force_quote":  0.0,
            "rank_base":    99,
            "rank_quote":   99,
        }


# ══ EXPORTS ═══════════════════════════════════════════════════════════════
__all__ = [
    "TABLE_SIGNALS_CLEAN",
    "CURRENCIES_V10_FULL",
    "PAIRS_V10_DEFAULT",
    "SignalSource",
    "V10SignalRow",
    "GeneratorReport",
    "SignalGeneratorLive",
    "decide_signal_level",
    "generate_signals_for_pair_tf",
    "compute_kpis",
    "persist_signals",
    "generate_clean_dataset",
    "_load_forces_snapshots",
    "_FORCE_NATIVE_OK",
]
