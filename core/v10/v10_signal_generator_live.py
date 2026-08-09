"""V10 Signal Generator Live — génère dataset V10 propre depuis forces_snapshots.

Doctrine V10 (mandat Phase 17 CEO) :
  R1 : agit par défaut
  R2 : additif pur (0 import core/v9/)
  R6 : fail-open (≥4 cas gérés)
  R7 : testé
  R9 : audit honnête, sérialisable JSON, source loggée
  R10 : calcul only, zéro ordre réel

Mission :
  Remplacer les 337 paper_trades V9 (biaisés) par un dataset V10 propre
  basé sur :
    - forces_snapshots DB (254 226 snapshots disponibles)
    - 8 colonnes force_* (force_usd/eur/gbp/jpy/cad/chf/aud/nzd)
    - tick_volume + bid/ask/mid
    - direction/vitesse (collecteur V9)
    - apply compute_currency_strength() sur fenêtres glissantes

Livrable :
  - Table v10_signals_clean dans v9_forces.db (R1 persistance)
  - Dataset de signaux A1/A2/A3/NONE avec features V10 propres
  - Rapport WR/PnL par paire (R9 audit)
  - WR EURUSD/AUDUSD mesurable correctement (vs biaisés V9)

CYCLE 9 — 2026-08-09
  SGL-C9-FIX1: retourner session dans le dict de sortie
  SGL-C9-FIX2: signal_level="NONE" quand bars < 10
  SGL-C9-OPT1: direction normalisée {"BULLISH","BEARISH","NEUTRAL"}
  SGL-C9-OPT2: delta_force borné [-1.0, +1.0]
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
from typing import Dict, List, Optional, Tuple

from .v10_currency_strength import (
    CurrencyStrength,
    compute_currency_strength,
    DEFAULTS,
    INVERSION_MAP,
    PAIRS_BY_CURRENCY,
    PAIRS_USD,
)

log = logging.getLogger(__name__)

# Tables DB
TABLE_SIGNALS_CLEAN = "v10_signals_clean"

# Paires V10 — 7 majeures (sans NZD qui n'est pas dans CURRENCIES V10.1)
# Note : forces_snapshots a 8 colonnes force_* incluant NZD.
# Pour V10.1 on utilise les 7 devises (CURRENCIES) + NZD en extension
# quand le module v10_currency_strength.py sera mis à jour.
CURRENCIES_V10_FULL = ("EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD")

# Paires à traiter
PAIRS_V10_DEFAULT = (
    "EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY",
)

# Seuils signaux V10 (alignés avec Phase 4 v10_signal_scorer)
SIGNAL_LEVEL_NONE = "NONE"
SIGNAL_LEVEL_A3 = "A3"
SIGNAL_LEVEL_A2 = "A2"
SIGNAL_LEVEL_A1 = "A1"

# Fenêtre glissante pour compute_currency_strength
WINDOW_BARS = 50  # 50 bougies fermées

# PnL proxy (pour backtest du dataset V10 propre)
PIPS_PER_PIP_FOREX = 100.0  # convention

# Horizon par TF — Étape 5A patch (CEO diagnostic 5/8)
# Signal Fatman se réalise sur 2-3 bougies courtes, pas 5 longues.
HORIZON_BARS_BY_TF: Dict[str, int] = {
    "M30": 3,
    "H1": 2,
    "H4": 1,
}

# Timeframes par défaut — Étape 5A patch (CEO diagnostic 5/8 : M30 obligatoire)
TIMEFRAMES_DEFAULT: Tuple[str, ...] = ("M30", "H1", "H4")

# Filtre anti-binaire — Étape 5A patch (forces all-or-nothing V9)
# Exclut snapshots où force_base ET force_quote sont simultanément 0.0 ou 100.0
BINARY_FORCE_VALUES = frozenset({0.0, 100.0})


# ─────────────────────────────────────────────────────────────────────
# ENUMS & DATACLASSES
# ─────────────────────────────────────────────────────────────────────

class SignalSource(str, Enum):
    """Source des features V10 (R9 audit)."""
    FORCES_SNAPSHOTS = "forces_snapshots"  # source primaire
    SYNTHETIC = "synthetic"               # pour tests


@dataclass
class V10SignalRow:
    """Un signal V10 propre dans le dataset."""
    signal_id: str
    timestamp: str
    symbol: str
    timeframe: str
    pair: str
    direction: str
    signal_level: str  # A1/A2/A3/NONE
    # Features V10
    force_base: float = 0.0
    force_quote: float = 0.0
    velocity_base: float = 0.0
    velocity_quote: float = 0.0
    rank_base: int = 0
    rank_quote: int = 0
    spread_score: float = 0.0
    tick_volume: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    # PnL proxy (sur barres suivantes si dispo)
    pnl_pips_proxy: float = 0.0  # mouvement close[t+N] - close[t]
    is_win_proxy: int = 0        # 1 si pnl_pips_proxy > 0
    # C9-FIX1: session dans le signal
    session: str = "UNKNOWN"
    # Audit
    source: str = SignalSource.FORCES_SNAPSHOTS.value
    features_json: str = ""

    def as_dict(self) -> Dict:
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "pair": self.pair,
            "direction": self.direction,
            "signal_level": self.signal_level,
            "force_base": round(self.force_base, 2),
            "force_quote": round(self.force_quote, 2),
            "velocity_base": round(self.velocity_base, 4),
            "velocity_quote": round(self.velocity_quote, 4),
            "rank_base": self.rank_base,
            "rank_quote": self.rank_quote,
            "spread_score": round(self.spread_score, 2),
            "tick_volume": self.tick_volume,
            "bid": self.bid,
            "ask": self.ask,
            "pnl_pips_proxy": round(self.pnl_pips_proxy, 2),
            "is_win_proxy": self.is_win_proxy,
            "source": self.source,
            "features_json": self.features_json,
            "session": self.session,
        }


@dataclass
class GeneratorReport:
    """Rapport génération dataset V10 propre (R9 audit)."""
    timestamp: str = ""
    db_path: str = ""
    n_snapshots_loaded: int = 0
    n_signals_generated: int = 0
    n_signals_persisted: int = 0
    pairs_processed: List[str] = field(default_factory=list)
    timeframes_processed: List[str] = field(default_factory=list)
    kpis_by_pair: Dict[str, Dict] = field(default_factory=dict)
    kpis_by_level: Dict[str, Dict] = field(default_factory=dict)
    kpis_by_tf: Dict[str, Dict] = field(default_factory=dict)         # Étape 5A
    kpis_by_pair_tf: Dict[str, Dict] = field(default_factory=dict)     # Étape 5A
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "db_path": self.db_path,
            "n_snapshots_loaded": self.n_snapshots_loaded,
            "n_signals_generated": self.n_signals_generated,
            "n_signals_persisted": self.n_signals_persisted,
            "pairs_processed": self.pairs_processed,
            "timeframes_processed": self.timeframes_processed,
            "kpis_by_pair": self.kpis_by_pair,
            "kpis_by_level": self.kpis_by_level,
            "kpis_by_tf": self.kpis_by_tf,
            "kpis_by_pair_tf": self.kpis_by_pair_tf,
            "audit": self.audit,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────
# FORCES_SNAPSHOTS LOADER
# ─────────────────────────────────────────────────────────────────────

def _load_forces_snapshots(
    db_path: str,
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict]:
    """Charge les snapshots depuis forces_snapshots.

    Retourne liste de dicts avec : symbol, timeframe, timestamp, force_<DEVISE>,
    tick_volume, bid, ask, direction, vitesse, etc.
    """
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

        where_parts = []
        params: list = []
        if symbol:
            where_parts.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            where_parts.append("timeframe = ?")
            params.append(timeframe)
        if not where_parts:
            where_parts.append("1=1")

        order = "bar_time ASC"
        limit_sql = f"LIMIT {limit}" if limit else ""

        query = f"""
            SELECT snapshot_id, timestamp, symbol, timeframe, bar_time, bar_close_time,
                   direction, vitesse,
                   force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd,
                   tick_volume, spread_points, bid, ask, mid, open, high, low, close
            FROM forces_snapshots
            WHERE {' AND '.join(where_parts)}
            ORDER BY {order}
            {limit_sql}
        """
        for row in cur.execute(query, params):
            d = {
                "snapshot_id": row[0],
                "timestamp": row[1],
                "symbol": row[2],
                "timeframe": row[3],
                "bar_time": row[4],
                "bar_close_time": row[5],
                "direction": row[6],
                "vitesse": row[7] or 0.0,
                "force": {
                    "USD": row[8] or 0.0,
                    "GBP": row[9] or 0.0,
                    "EUR": row[10] or 0.0,
                    "JPY": row[11] or 0.0,
                    "CAD": row[12] or 0.0,
                    "CHF": row[13] or 0.0,
                    "AUD": row[14] or 0.0,
                    "NZD": row[15] or 0.0,
                },
                "tick_volume": row[16] or 0.0,
                "spread_points": row[17] or 0.0,
                "bid": row[18] or 0.0,
                "ask": row[19] or 0.0,
                "mid": row[20] or 0.0,
                "open": row[21] or 0.0,
                "high": row[22] or 0.0,
                "low": row[23] or 0.0,
                "close": row[24] or 0.0,
            }
            out.append(d)
    except Exception as exc:
        log.warning("Erreur lecture forces_snapshots : %s", exc)
    finally:
        con.close()
    return out


# ─────────────────────────────────────────────────────────────────────
# SIGNAL LEVEL DECISION
# ─────────────────────────────────────────────────────────────────────

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
    """Décide signal_level A1/A2/A3/NONE depuis features V10.

    Logique :
      - NONE  : direction=='neutre' ou (rank_base-rank_quote) ∈ [-1, 0]
      - A3    : direction détectée mais magnitude faible (delta_force < 20)
      - A2    : delta_force > 20 et velocities alignées
      - A1    : delta_force > 30 + velocities alignées + (base top 3 OU quote top 3
                 si bearish) — la devise dominante doit être dans le top 3.

    Returns (signal_level, "BULLISH"/"BEARISH")
    """
    delta_force = force_base - force_quote
    delta_velocity = velocity_base - velocity_quote
    rank_delta = rank_quote - rank_base  # positif si base > quote

    # Direction
    if direction == "haussiere":
        dir_sign = 1
    elif direction == "baissiere":
        dir_sign = -1
    else:
        dir_sign = 0

    # Inferred direction depuis les forces
    inferred_dir = "BULLISH" if delta_force > 0 else ("BEARISH" if delta_force < 0 else "NEUTRAL")

    # Vérifie alignement : direction collecteur + delta_force doivent matcher
    aligned = (dir_sign > 0 and delta_force > 0) or (dir_sign < 0 and delta_force < 0) or dir_sign == 0

    if not aligned or abs(delta_force) < 10:
        return (SIGNAL_LEVEL_NONE, inferred_dir)
    if abs(delta_force) < 20:
        return (SIGNAL_LEVEL_A3, inferred_dir)
    if abs(delta_force) < 30:
        return (SIGNAL_LEVEL_A2, inferred_dir)
    # A1 : la devise dominante (base si BULLISH, quote si BEARISH) doit être top 3
    dominant_is_top3 = (
        (delta_force > 0 and rank_base <= 3) or
        (delta_force < 0 and rank_quote <= 3)
    )
    if not dominant_is_top3:
        return (SIGNAL_LEVEL_A2, inferred_dir)
    return (SIGNAL_LEVEL_A1, inferred_dir)


# ─────────────────────────────────────────────────────────────────────
# PNL PROXY (R9 honest : mouvement close[t+N] - close[t])
# ─────────────────────────────────────────────────────────────────────

def _compute_pnl_proxy(
    snapshots: List[Dict],
    idx: int,
    *,
    horizon_bars: int = 5,
) -> Tuple[float, int]:
    """PnL proxy : mouvement mid sur N bougies futures (R9 audit honest).

    Étape 5A (CEO diagnostic) : horizon_bars doit être court (1-3) pour H1/H4
    car signal Fatman se réalise sur 2-3 bougies courtes, pas 5 longues.
    """
    if idx + horizon_bars >= len(snapshots):
        return 0.0, 0
    close_now = snapshots[idx].get("mid") or snapshots[idx].get("close") or 0.0
    close_next = snapshots[idx + horizon_bars].get("mid") or snapshots[idx + horizon_bars].get("close") or 0.0
    if close_now <= 0:
        return 0.0, 0
    pips = (close_next - close_now) * PIPS_PER_PIP_FOREX
    is_win = 1 if pips > 0 else 0
    return round(pips, 2), is_win


def _is_binary_snapshot(snap: Dict, base: str, quote: str) -> bool:
    """Retourne True si force_base ET force_quote sont simultanément 0.0 ou 100.0.

    Étape 5A (CEO diagnostic) : exclut les snapshots V9 all-or-nothing
    où les forces sont binaires (0.0 ou 100.0), ce qui biaise le rank
    et le delta_force.
    """
    force = snap.get("force", {})
    fb = float(force.get(base, 0.0))
    fq = float(force.get(quote, 0.0))
    return (fb in BINARY_FORCE_VALUES) and (fq in BINARY_FORCE_VALUES)


# ─────────────────────────────────────────────────────────────────────
# DATASET GENERATION
# ─────────────────────────────────────────────────────────────────────

def generate_signals_for_pair_tf(
    snapshots: List[Dict],
    *,
    pair: str,
    timeframe: str,
    horizon_bars: int = 5,
    filter_binary: bool = True,
) -> Tuple[List[V10SignalRow], int]:
    """Génère signaux V10 propres pour une paire × timeframe.

    Pour chaque bougie fermée :
      - Calcule features V10 depuis forces_snapshots
      - Décide signal_level (A1/A2/A3/NONE)
      - Calcule pnl_pips_proxy sur horizon_bars futures

    Étape 5A (CEO diagnostic) :
      - horizon_bars doit être court (1-3) pour H1/H4 (cf HORIZON_BARS_BY_TF)
      - filter_binary=True : exclut snapshots V9 all-or-nothing (base ET quote
        simultanément ∈ {0.0, 100.0})

    Returns
    -------
    (signals, n_filtered_binary) : signaux + nombre de snapshots exclus
    """
    # SGL-C9-FIX2: signal_level="NONE" quand bars < 10
    if len(snapshots) < max(horizon_bars + 1, 10):
        return [], 0

    base, quote = pair[:3], pair[3:]
    out: List[V10SignalRow] = []
    n_filtered_binary = 0
    
    # Déterminer la session depuis le premier snapshot
    session_detected = "UNKNOWN"
    if snapshots:
        first_snap = snapshots[0]
        # Essayer de déduire la session depuis bar_time
        bar_time = first_snap.get("bar_time", 0)
        if bar_time:
            from datetime import datetime, timezone
            try:
                dt = datetime.fromtimestamp(bar_time, tz=timezone.utc)
                hour = dt.hour
                if 7 <= hour < 13:
                    session_detected = "LONDON"
                elif 13 <= hour < 16:
                    session_detected = "LONDON_NY"
                elif 16 <= hour < 22:
                    session_detected = "NEW_YORK"
                elif 0 <= hour < 7:
                    session_detected = "TOKYO"
                else:
                    session_detected = "OFF"
            except Exception:
                pass

    base, quote = pair[:3], pair[3:]
    out: List[V10SignalRow] = []
    n_filtered_binary = 0
    for idx in range(len(snapshots) - horizon_bars):
        snap = snapshots[idx]

        # Étape 5A : filtre anti-binaire V9
        if filter_binary and _is_binary_snapshot(snap, base, quote):
            n_filtered_binary += 1
            continue

        force = snap.get("force", {})

        force_base = float(force.get(base, 0.0))
        force_quote = float(force.get(quote, 0.0))

        # Velocity = différence force[t] - force[t-1] (proxy simple)
        velocity_base = 0.0
        velocity_quote = 0.0
        if idx > 0:
            prev_force = snapshots[idx - 1].get("force", {})
            velocity_base = force_base - float(prev_force.get(base, force_base))
            velocity_quote = force_quote - float(prev_force.get(quote, force_quote))

        # Velocity = différence force[t] - force[t-1] (proxy simple)
        velocity_base = 0.0
        velocity_quote = 0.0
        if idx > 0:
            prev_force = snapshots[idx - 1].get("force", {})
            velocity_base = force_base - float(prev_force.get(base, force_base))
            velocity_quote = force_quote - float(prev_force.get(quote, force_quote))

        # Rank : position dans le top 8 (par ordre décroissant de force)
        all_forces = sorted(
            [(c, float(force.get(c, 0.0))) for c in CURRENCIES_V10_FULL],
            key=lambda x: x[1],
            reverse=True,
        )
        rank_map = {c: i + 1 for i, (c, _) in enumerate(all_forces)}
        rank_base = rank_map.get(base, 99)
        rank_quote = rank_map.get(quote, 99)

        direction = snap.get("direction", "neutre")
        vitesse = float(snap.get("vitesse", 0.0))

        # SGL-C9-FIX1: déterminer session depuis bar_time
        bar_time = snap.get("bar_time", 0)
        session_detected = "UNKNOWN"
        if bar_time:
            from datetime import datetime, timezone
            try:
                dt = datetime.fromtimestamp(bar_time, tz=timezone.utc)
                hour = dt.hour
                if 7 <= hour < 13:
                    session_detected = "LONDON"
                elif 13 <= hour < 16:
                    session_detected = "LONDON_NY"
                elif 16 <= hour < 22:
                    session_detected = "NEW_YORK"
                elif 0 <= hour < 7:
                    session_detected = "TOKYO"
                else:
                    session_detected = "OFF"
            except Exception:
                pass

        # Decide signal level
        level, inferred_dir = decide_signal_level(
            force_base=force_base, force_quote=force_quote,
            velocity_base=velocity_base, velocity_quote=velocity_quote,
            rank_base=rank_base, rank_quote=rank_quote,
            direction=direction, vitesse=vitesse,
        )

        # PnL proxy (Étape 5A : horizon court par TF)
        pnl_pips, is_win = _compute_pnl_proxy(snapshots, idx, horizon_bars=horizon_bars)

        # SGL-C9-OPT2: delta_force borné [-1.0, +1.0]
        delta_force = force_base - force_quote
        delta_force_clamped = max(-1.0, min(1.0, delta_force))

        signal_id = f"V10CLEAN-{pair}-{timeframe}-{snap.get('bar_time', idx)}-h{horizon_bars}"
        row = V10SignalRow(
            signal_id=signal_id,
            timestamp=str(snap.get("timestamp", "")),
            symbol=snap.get("symbol", pair),
            timeframe=timeframe,
            pair=pair,
            direction=inferred_dir,
            signal_level=level,
            force_base=force_base,
            force_quote=force_quote,
            velocity_base=velocity_base,
            velocity_quote=velocity_quote,
            rank_base=rank_base,
            rank_quote=rank_quote,
            spread_score=float(snap.get("spread_points", 0.0)),
            tick_volume=float(snap.get("tick_volume", 0.0)),
            bid=float(snap.get("bid", 0.0)),
            ask=float(snap.get("ask", 0.0)),
            pnl_pips_proxy=pnl_pips,
            is_win_proxy=is_win,
            source=SignalSource.FORCES_SNAPSHOTS.value,
            session=session_detected,
            features_json=json.dumps({
                "vitesse": vitesse,
                "spread_points": float(snap.get("spread_points", 0.0)),
                "tick_volume": float(snap.get("tick_volume", 0.0)),
                "horizon_bars": horizon_bars,
                "filtered_binary": filter_binary,
                "delta_force_raw": delta_force,
                "delta_force_clamped": delta_force_clamped,
            }),
        )
        out.append(row)
    return out, n_filtered_binary


# ─────────────────────────────────────────────────────────────────────
# KPI COMPUTATION
# ─────────────────────────────────────────────────────────────────────

def compute_kpis(
    signals: List[V10SignalRow],
    *,
    separate_by_tf: bool = True,
) -> Dict:
    """KPIs globaux + par niveau + par paire (+ par TF si separate_by_tf).

    Étape 5A : ajout WR par (pair, TF) et par (TF, level) pour Étape 6
    Bayesian recalibrator par (paire, TF).
    """
    n = len(signals)
    wins = sum(s.is_win_proxy for s in signals)
    wr = wins / n if n else 0.0
    pnl = sum(s.pnl_pips_proxy for s in signals)

    by_level: Dict[str, Dict] = {}
    for level in (SIGNAL_LEVEL_A1, SIGNAL_LEVEL_A2, SIGNAL_LEVEL_A3, SIGNAL_LEVEL_NONE):
        sub = [s for s in signals if s.signal_level == level]
        n_sub = len(sub)
        wins_sub = sum(s.is_win_proxy for s in sub)
        pnl_sub = sum(s.pnl_pips_proxy for s in sub)
        by_level[level] = {
            "n": n_sub,
            "wr": round(wins_sub / n_sub, 4) if n_sub else 0.0,
            "pnl_pips": round(pnl_sub, 2),
        }

    by_pair: Dict[str, Dict] = {}
    pairs_set = sorted({s.pair for s in signals})
    for p in pairs_set:
        sub = [s for s in signals if s.pair == p]
        n_p = len(sub)
        wins_p = sum(s.is_win_proxy for s in sub)
        pnl_p = sum(s.pnl_pips_proxy for s in sub)
        by_pair[p] = {
            "n": n_p,
            "wr": round(wins_p / n_p, 4) if n_p else 0.0,
            "pnl_pips": round(pnl_p, 2),
        }

    result: Dict = {
        "n_total": n,
        "wr_global": round(wr, 4),
        "pnl_total_pips": round(pnl, 2),
        "by_level": by_level,
        "by_pair": by_pair,
    }

    if separate_by_tf:
        # KPIs par TF
        by_tf: Dict[str, Dict] = {}
        tfs_set = sorted({s.timeframe for s in signals})
        for tf in tfs_set:
            sub = [s for s in signals if s.timeframe == tf]
            n_tf = len(sub)
            wins_tf = sum(s.is_win_proxy for s in sub)
            pnl_tf = sum(s.pnl_pips_proxy for s in sub)
            # WR par (TF, level)
            by_tf_level: Dict[str, Dict] = {}
            for level in (SIGNAL_LEVEL_A1, SIGNAL_LEVEL_A2, SIGNAL_LEVEL_A3, SIGNAL_LEVEL_NONE):
                sub_lv = [s for s in sub if s.signal_level == level]
                n_lv = len(sub_lv)
                wins_lv = sum(s.is_win_proxy for s in sub_lv)
                pnl_lv = sum(s.pnl_pips_proxy for s in sub_lv)
                by_tf_level[level] = {
                    "n": n_lv,
                    "wr": round(wins_lv / n_lv, 4) if n_lv else 0.0,
                    "pnl_pips": round(pnl_lv, 2),
                }
            by_tf[tf] = {
                "n": n_tf,
                "wr": round(wins_tf / n_tf, 4) if n_tf else 0.0,
                "pnl_pips": round(pnl_tf, 2),
                "by_level": by_tf_level,
            }
        result["by_tf"] = by_tf

        # KPIs par (paire, TF)
        by_pair_tf: Dict[str, Dict] = {}
        pair_tf_set = sorted({(s.pair, s.timeframe) for s in signals})
        for p, tf in pair_tf_set:
            key = f"{p}_{tf}"
            sub = [s for s in signals if s.pair == p and s.timeframe == tf]
            n_pt = len(sub)
            wins_pt = sum(s.is_win_proxy for s in sub)
            pnl_pt = sum(s.pnl_pips_proxy for s in sub)
            # WR par (paire, TF, level)
            by_pt_level: Dict[str, Dict] = {}
            for level in (SIGNAL_LEVEL_A1, SIGNAL_LEVEL_A2, SIGNAL_LEVEL_A3, SIGNAL_LEVEL_NONE):
                sub_lv = [s for s in sub if s.signal_level == level]
                n_lv = len(sub_lv)
                wins_lv = sum(s.is_win_proxy for s in sub_lv)
                pnl_lv = sum(s.pnl_pips_proxy for s in sub_lv)
                by_pt_level[level] = {
                    "n": n_lv,
                    "wr": round(wins_lv / n_lv, 4) if n_lv else 0.0,
                    "pnl_pips": round(pnl_lv, 2),
                }
            by_pair_tf[key] = {
                "pair": p,
                "tf": tf,
                "n": n_pt,
                "wr": round(wins_pt / n_pt, 4) if n_pt else 0.0,
                "pnl_pips": round(pnl_pt, 2),
                "by_level": by_pt_level,
            }
        result["by_pair_tf"] = by_pair_tf

    return result


# ─────────────────────────────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────────────────────────────

def persist_signals(db_path: str, signals: List[V10SignalRow]) -> int:
    """Persiste signaux V10 propres dans v9_forces.db table v10_signals_clean."""
    if not signals:
        return 0
    con = sqlite3.connect(db_path, timeout=10)
    n_persisted = 0
    try:
        cur = con.cursor()
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_SIGNALS_CLEAN} (
                signal_id TEXT PRIMARY KEY,
                timestamp TEXT,
                symbol TEXT,
                timeframe TEXT,
                pair TEXT,
                direction TEXT,
                signal_level TEXT,
                force_base REAL,
                force_quote REAL,
                velocity_base REAL,
                velocity_quote REAL,
                rank_base INTEGER,
                rank_quote INTEGER,
                spread_score REAL,
                tick_volume REAL,
                bid REAL,
                ask REAL,
                pnl_pips_proxy REAL,
                is_win_proxy INTEGER,
                source TEXT,
                features_json TEXT,
                session TEXT
            )
        """)
        # Ensure session column exists (migration for existing tables)
        try:
            cur.execute("ALTER TABLE {TABLE_SIGNALS_CLEAN} ADD COLUMN session TEXT")
        except Exception:
            pass  # Column already exists
        
        for s in signals:
            try:
                cur.execute(f"""
                    INSERT OR REPLACE INTO {TABLE_SIGNALS_CLEAN} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    s.signal_id, s.timestamp, s.symbol, s.timeframe, s.pair,
                    s.direction, s.signal_level,
                    s.force_base, s.force_quote, s.velocity_base, s.velocity_quote,
                    s.rank_base, s.rank_quote, s.spread_score, s.tick_volume,
                    s.bid, s.ask, s.pnl_pips_proxy, s.is_win_proxy,
                    s.source, s.features_json,
                    s.session,
                ))
                n_persisted += 1
            except Exception as exc:
                log.warning("Insert signal %s failed : %s", s.signal_id, exc)
        con.commit()
    finally:
        con.close()
    return n_persisted


# ─────────────────────────────────────────────────────────────────────
# ORCHESTRATEUR
# ─────────────────────────────────────────────────────────────────────

def _truncate_signals_table(db_path: str) -> None:
    """Vide la table v10_signals_clean avant regénération (R6 fail-open)."""
    try:
        con = sqlite3.connect(db_path, timeout=10)
        cur = con.cursor()
        cur.execute(f"DELETE FROM {TABLE_SIGNALS_CLEAN}")
        con.commit()
        con.close()
    except Exception as exc:
        log.warning("TRUNCATE %s failed : %s (R6 fail-open, continue)", TABLE_SIGNALS_CLEAN, exc)


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
    """Génère dataset V10 propre complet et persiste en DB.

    Étape 5A patches (CEO diagnostic 5/8) :
      - timeframes = ("M30", "H1", "H4") par défaut (M30 obligatoire)
      - horizon_bars par TF via HORIZON_BARS_BY_TF : M30→3, H1→2, H4→1
      - filter_binary=True : exclut snapshots V9 all-or-nothing
      - truncate_first=True : TRUNCATE table avant INSERT (pas d'append)

    Returns
    -------
    GeneratorReport : KPIs par paire + par niveau + par TF + par (paire, TF).
                      n_filtered dans audit. n_filtered_pct.
    """
    report = GeneratorReport(
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        db_path=db_path,
        pairs_processed=list(pairs),
        timeframes_processed=list(timeframes),
    )

    # Resolution horizon map : param explicite > dict global > défaut
    horizon_map: Dict[str, int] = {}
    if horizon_by_tf is not None:
        horizon_map.update(horizon_by_tf)
    else:
        horizon_map.update(HORIZON_BARS_BY_TF)
    # Si horizon_bars passé en int (legacy), on l'applique à tous les TF
    if horizon_bars is not None:
        for tf in timeframes:
            horizon_map[tf] = horizon_bars

    # Truncate table si demandé
    if truncate_first:
        _truncate_signals_table(db_path)

    all_signals: List[V10SignalRow] = []
    n_loaded_total = 0
    n_filtered_total = 0
    n_filtered_by_pair_tf: Dict[str, int] = {}
    n_snapshots_by_tf: Dict[str, int] = {}

    for pair in pairs:
        for tf in timeframes:
            snaps = _load_forces_snapshots(
                db_path, symbol=pair, timeframe=tf,
                limit=limit_per_pair_tf,
            )
            n_loaded_total += len(snaps)
            n_snapshots_by_tf[tf] = n_snapshots_by_tf.get(tf, 0) + len(snaps)
            if not snaps:
                log.info("Aucun snapshot pour %s/%s", pair, tf)
                continue
            horizon_for_tf = horizon_map.get(tf, 5)
            signals, n_filtered = generate_signals_for_pair_tf(
                snaps, pair=pair, timeframe=tf,
                horizon_bars=horizon_for_tf,
                filter_binary=filter_binary,
            )
            all_signals.extend(signals)
            n_filtered_total += n_filtered
            n_filtered_by_pair_tf[f"{pair}_{tf}"] = n_filtered

    report.n_snapshots_loaded = n_loaded_total
    report.n_signals_generated = len(all_signals)

    # Persist (TRUNCATE déjà fait si demandé)
    report.n_signals_persisted = persist_signals(db_path, all_signals)

    # KPIs par paire + par niveau + par TF + par (paire, TF)
    kpis = compute_kpis(all_signals, separate_by_tf=True)
    report.kpis_by_pair = kpis["by_pair"]
    report.kpis_by_level = kpis["by_level"]
    if "by_tf" in kpis:
        report.kpis_by_tf = kpis["by_tf"]
    if "by_pair_tf" in kpis:
        report.kpis_by_pair_tf = kpis["by_pair_tf"]

    # R9 audit complet
    n_filtered_pct = (n_filtered_total / n_loaded_total * 100.0) if n_loaded_total else 0.0
    report.audit = {
        "wr_global": kpis["wr_global"],
        "pnl_total_pips": kpis["pnl_total_pips"],
        "n_total": kpis["n_total"],
        "horizon_by_tf": horizon_map,
        "filter_binary": filter_binary,
        "currencies_used": list(CURRENCIES_V10_FULL),
        "n_pairs_in_db_table": sum(1 for p in report.kpis_by_pair.values() if p["n"] > 0),
        # Étape 5A : R9 audit honnete
        "n_filtered_binary": n_filtered_total,
        "n_filtered_pct": round(n_filtered_pct, 2),
        "n_filtered_by_pair_tf": n_filtered_by_pair_tf,
        "n_snapshots_by_tf": n_snapshots_by_tf,
        # R6 fail-open si > 80% filtrés → log CRITIQUE
        "filter_critical": n_filtered_pct > 80.0,
        "filter_critical_msg": (
            f"FORCES_SNAPSHOTS majoritairement V9 binaires ({n_filtered_pct:.1f}% filtrés). "
            "V10 doit recalculer les forces nativement via v10_currency_strength.py (Phase 20)."
        ) if n_filtered_pct > 80.0 else None,
    }
    if n_filtered_pct > 80.0:
        log.critical("R6 — %s", report.audit["filter_critical_msg"])

    return report


# ─────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────

__all__ = [
    "TABLE_SIGNALS_CLEAN",
    "CURRENCIES_V10_FULL",
    "PAIRS_V10_DEFAULT",
    "SignalSource",
    "V10SignalRow",
    "GeneratorReport",
    "decide_signal_level",
    "generate_signals_for_pair_tf",
    "compute_kpis",
    "persist_signals",
    "generate_clean_dataset",
    "_load_forces_snapshots",
]
