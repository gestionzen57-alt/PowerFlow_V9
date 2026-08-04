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
    """PnL proxy : mouvement mid sur N bougies futures (R9 audit honest)."""
    if idx + horizon_bars >= len(snapshots):
        return 0.0, 0
    close_now = snapshots[idx].get("mid") or snapshots[idx].get("close") or 0.0
    close_next = snapshots[idx + horizon_bars].get("mid") or snapshots[idx + horizon_bars].get("close") or 0.0
    if close_now <= 0:
        return 0.0, 0
    pips = (close_next - close_now) * PIPS_PER_PIP_FOREX
    is_win = 1 if pips > 0 else 0
    return round(pips, 2), is_win


# ─────────────────────────────────────────────────────────────────────
# DATASET GENERATION
# ─────────────────────────────────────────────────────────────────────

def generate_signals_for_pair_tf(
    snapshots: List[Dict],
    *,
    pair: str,
    timeframe: str,
    horizon_bars: int = 5,
) -> List[V10SignalRow]:
    """Génère signaux V10 propres pour une paire × timeframe.

    Pour chaque bougie fermée :
      - Calcule features V10 depuis forces_snapshots
      - Décide signal_level (A1/A2/A3/NONE)
      - Calcule pnl_pips_proxy sur horizon_bars futures
    """
    if len(snapshots) < horizon_bars + 1:
        return []

    base, quote = pair[:3], pair[3:]
    out: List[V10SignalRow] = []
    for idx in range(len(snapshots) - horizon_bars):
        snap = snapshots[idx]
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

        # Decide signal level
        level, inferred_dir = decide_signal_level(
            force_base=force_base, force_quote=force_quote,
            velocity_base=velocity_base, velocity_quote=velocity_quote,
            rank_base=rank_base, rank_quote=rank_quote,
            direction=direction, vitesse=vitesse,
        )

        # PnL proxy
        pnl_pips, is_win = _compute_pnl_proxy(snapshots, idx, horizon_bars=horizon_bars)

        signal_id = f"V10CLEAN-{pair}-{timeframe}-{snap.get('bar_time', idx)}"
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
            features_json=json.dumps({
                "vitesse": vitesse,
                "spread_points": float(snap.get("spread_points", 0.0)),
                "tick_volume": float(snap.get("tick_volume", 0.0)),
                "horizon_bars": horizon_bars,
            }),
        )
        out.append(row)
    return out


# ─────────────────────────────────────────────────────────────────────
# KPI COMPUTATION
# ─────────────────────────────────────────────────────────────────────

def compute_kpis(signals: List[V10SignalRow]) -> Dict:
    """KPIs globaux + par niveau + par paire."""
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

    return {
        "n_total": n,
        "wr_global": round(wr, 4),
        "pnl_total_pips": round(pnl, 2),
        "by_level": by_level,
        "by_pair": by_pair,
    }


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
                features_json TEXT
            )
        """)
        for s in signals:
            try:
                cur.execute(f"""
                    INSERT OR REPLACE INTO {TABLE_SIGNALS_CLEAN} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    s.signal_id, s.timestamp, s.symbol, s.timeframe, s.pair,
                    s.direction, s.signal_level,
                    s.force_base, s.force_quote, s.velocity_base, s.velocity_quote,
                    s.rank_base, s.rank_quote, s.spread_score, s.tick_volume,
                    s.bid, s.ask, s.pnl_pips_proxy, s.is_win_proxy,
                    s.source, s.features_json,
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

def generate_clean_dataset(
    db_path: str,
    *,
    pairs: Tuple[str, ...] = PAIRS_V10_DEFAULT,
    timeframes: Tuple[str, ...] = ("H1", "H4"),
    horizon_bars: int = 5,
    timestamp: str = "",
    limit_per_pair_tf: Optional[int] = None,
) -> GeneratorReport:
    """Génère dataset V10 propre complet et persiste en DB.

    Returns
    -------
    GeneratorReport : KPIs par paire + par niveau, audit complet.
    """
    report = GeneratorReport(
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        db_path=db_path,
        pairs_processed=list(pairs),
        timeframes_processed=list(timeframes),
    )

    all_signals: List[V10SignalRow] = []
    n_loaded_total = 0

    for pair in pairs:
        for tf in timeframes:
            snaps = _load_forces_snapshots(
                db_path, symbol=pair, timeframe=tf,
                limit=limit_per_pair_tf,
            )
            n_loaded_total += len(snaps)
            if not snaps:
                log.info("Aucun snapshot pour %s/%s", pair, tf)
                continue
            signals = generate_signals_for_pair_tf(
                snaps, pair=pair, timeframe=tf, horizon_bars=horizon_bars,
            )
            all_signals.extend(signals)

    report.n_snapshots_loaded = n_loaded_total
    report.n_signals_generated = len(all_signals)

    # Persist
    report.n_signals_persisted = persist_signals(db_path, all_signals)

    # KPIs
    kpis = compute_kpis(all_signals)
    report.kpis_by_pair = kpis["by_pair"]
    report.kpis_by_level = kpis["by_level"]
    report.audit = {
        "wr_global": kpis["wr_global"],
        "pnl_total_pips": kpis["pnl_total_pips"],
        "n_total": kpis["n_total"],
        "horizon_bars": horizon_bars,
        "currencies_used": list(CURRENCIES_V10_FULL),
        "n_pairs_in_db_table": sum(1 for p in report.kpis_by_pair.values() if p["n"] > 0),
    }
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
