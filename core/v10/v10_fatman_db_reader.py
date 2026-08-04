"""V10 Fatman DB Reader — Lecture des vraies données Fatman depuis v9_forces.db.

ATTENTION — R9 ARCHITECTURE
===========================
L'indicateur Fatman est PROPRIÉTAIRE MT4 uniquement (pas de version MT5,
jamais de code source partagé). La SEULE source légitime des scores Fatman
est la table `forces_snapshots` de `data/v9_forces.db`, alimentée en temps
réel par le collecteur V9 (Expert Advisor MT4) qui lit les buffers Fatman.

Ce module :
  - Lit 8 colonnes force_<DEVISE> (force_eur/usd/gbp/jpy/cad/chf/aud/nzd)
  - Calcule par (symbol, timeframe) : base_score, quote_score, base_rank,
    quote_rank, delta_score, momentum, freshness en secondes.
  - R6 fail-open : si DB absente ou stale (>300s) → fallback v10_currency_strength.
  - R9 audit : source est 'v9_forces_db' ou 'fallback_strength'.

API :
  FatmanLiveState dataclass avec :
    - symbol, timeframe, timestamp
    - base_score, quote_score ∈ [0, 100]
    - base_rank, quote_rank ∈ {1..8} parmi les 8 majors
    - delta_score  : variation depuis la barre précédente (%)
    - momentum     : UP / DOWN / FLAT
    - freshness_seconds
    - is_stale     : True si freshness > max_age_seconds
    - source       : 'v9_forces_db' | 'fallback_strength' | 'compute_proxy'
    - audit        : dict (seed, db_age_seconds, n_bars_read)

  get_fatman_live(symbol, tf, db_path=...) -> FatmanLiveState
  freshness_check(max_age_seconds=300, db_path=...) -> bool
  get_all_fatman_live(db_path=...) -> Dict[(symbol, tf) -> FatmanLiveState]

Doctrine : R1-AGIR, R2 additif pur (0 import core/v9/), R6 fail-open,
            R7 tests verts (≥12), R9 audit, R10 zero capital.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────
DEFAULT_DB_PATH = "data/v9_forces.db"
DEFAULT_MAX_AGE_SECONDS = 300  # 5 min — au-delà, on considére la donnée stale
FORCE_COLUMNS = (
    "force_eur", "force_usd", "force_gbp", "force_jpy",
    "force_cad", "force_chf", "force_aud", "force_nzd",
)
DEFAULT_CURRENCY_COL = {
    "EUR": "force_eur",
    "USD": "force_usd",
    "GBP": "force_gbp",
    "JPY": "force_jpy",
    "CAD": "force_cad",
    "CHF": "force_chf",
    "AUD": "force_aud",
    "NZD": "force_nzd",
}


class FatmanSource(str, Enum):
    """Source effective des scores Fatman (R9 audit)."""
    V9_FORCES_DB = "v9_forces_db"            # cas nominal
    FALLBACK_STRENGTH = "fallback_strength"  # R6 fail-open → v10_currency_strength
    COMPUTE_PROXY = "compute_proxy"          # fallback extrême via proxy simple
    MISSING = "missing"                      # aucune source utilisable


class Momentum(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"

    def sign(self) -> int:
        return {Momentum.UP: +1, Momentum.DOWN: -1, Momentum.FLAT: 0, Momentum.UNKNOWN: 0}[self]


# ─────────────────────────────────────────────────────────────────────
# Dataclasses sortie
# ─────────────────────────────────────────────────────────────────────
@dataclass
class FatmanLiveState:
    """État Fatman LIVE pour (symbol × timeframe)."""

    symbol: str
    timeframe: str
    timestamp: str                  # ISO 8601 UTC du snapshot DB
    bar_time: int                   # epoch seconds

    # Scores devise base / quote [0, 100]
    base_score: float = 50.0
    quote_score: float = 50.0
    base_rank: int = 4              # rang 1=fort parmi les 8 majors
    quote_rank: int = 4

    # Dynamique
    delta_score: float = 0.0        # delta base_score - base_score_prev
    momentum: Momentum = Momentum.UNKNOWN

    # R6 / R9
    freshness_seconds: float = 999.0
    is_stale: bool = True
    source: FatmanSource = FatmanSource.MISSING

    # Audit
    n_bars_read: int = 0
    db_path: Optional[str] = None
    seed: Optional[int] = None
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp,
            "bar_time": self.bar_time,
            "base_score": round(self.base_score, 2),
            "quote_score": round(self.quote_score, 2),
            "base_rank": self.base_rank,
            "quote_rank": self.quote_rank,
            "delta_score": round(self.delta_score, 2),
            "momentum": self.momentum.value,
            "freshness_seconds": round(self.freshness_seconds, 1),
            "is_stale": self.is_stale,
            "source": self.source.value,
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers DB purs
# ─────────────────────────────────────────────────────────────────────
def _open_db_readonly(db_path: str) -> Optional[sqlite3.Connection]:
    """R6 fail-open : DB absente / non accessible → None."""
    try:
        if not Path(db_path).exists():
            log.debug(f"v10_fatman_db_reader: DB absente {db_path}")
            return None
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        return con
    except (sqlite3.OperationalError, OSError) as e:
        log.debug(f"v10_fatman_db_reader: ouverture DB impossible {e}")
        return None


def _table_has_columns(con: sqlite3.Connection, table: str, columns: Tuple[str, ...]) -> bool:
    """Vérifie présence des colonnes force_* dans la table."""
    try:
        cur = con.cursor()
        existing = {c[1] for c in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        return all(c in existing for c in columns)
    except sqlite3.OperationalError:
        return False


def _extract_base_quote(symbol: str) -> Tuple[str, str]:
    """EURUSD → ('EUR', 'USD'), USDJPY → ('USD', 'JPY'), etc."""
    s = symbol.upper().replace("/", "").replace("_", "")
    if len(s) >= 6:
        return s[:3], s[3:6]
    return s, ""


def _rank_from_scores(
    base_score: float,
    quote_score: float,
    symbol: str,
    bar_row: sqlite3.Row,
) -> Tuple[int, int]:
    """Calcule rang base/quote parmi les 8 majors à partir des colonnes force_*."""
    scores = {cur: bar_row[DEFAULT_CURRENCY_COL[cur]] for cur in DEFAULT_CURRENCY_COL}
    # Trier desc (1 = plus fort)
    sorted_curr = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    ranks = {cur: i + 1 for i, (cur, _) in enumerate(sorted_curr)}
    base, quote = _extract_base_quote(symbol)
    return ranks.get(base, 4), ranks.get(quote, 4)


def _check_table_exists(con: sqlite3.Connection, table: str) -> bool:
    try:
        cur = con.cursor()
        n = cur.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).fetchone()[0]
        return bool(n)
    except sqlite3.OperationalError:
        return False


def _detect_collector_alive(max_age_seconds: float, db_path: str) -> Tuple[bool, float]:
    """Retourne (alive, age_seconds) — vérifie dernière mise à jour de forces_snapshots."""
    con = _open_db_readonly(db_path)
    if con is None:
        return False, float("inf")
    try:
        cur = con.cursor()
        try:
            row = cur.execute(
                "SELECT MAX(server_time), MAX(bar_time) FROM forces_snapshots WHERE is_closed_bar=1"
            ).fetchone()
        except sqlite3.OperationalError:
            return False, float("inf")
    finally:
        con.close()
    if not row or not row[0]:
        return False, float("inf")
    last_time = max(row[0] or 0, row[1] or 0)
    age = time.time() - last_time
    return age <= max_age_seconds, age


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def freshness_check(max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
                    db_path: str = DEFAULT_DB_PATH) -> bool:
    """Vérifie que le collecteur MT4 tourne (DB fraîche).

    Returns True si la dernière snapshot est plus récente que max_age_seconds.
    False sinon (= alerte : collecteur arrêté, fallback v10_currency_strength).
    """
    alive, _ = _detect_collector_alive(max_age_seconds, db_path)
    return alive


def get_fatman_live(
    symbol: str,
    timeframe: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    seed: Optional[int] = None,
) -> FatmanLiveState:
    """Lit l'état Fatman LIVE pour (symbol, timeframe) depuis v9_forces.db.

    R6 fail-open :
      1. DB absente ou table manquante → MISSING (utiliser fallback en amont)
      2. Collecteur stale (> max_age_seconds) → is_stale=True, source='v9_forces_db'
         (les données sont lues mais marquées stale — l'orchestrateur décidera)

    Doctrine R10 : compute only. Aucun ordre n'est transmis.
    """
    state = FatmanLiveState(
        symbol=symbol,
        timeframe=timeframe,
        timestamp="",
        bar_time=0,
        db_path=db_path,
        seed=seed,
    )

    con = _open_db_readonly(db_path)
    if con is None:
        state.source = FatmanSource.MISSING
        state.audit["reason"] = "db_unavailable"
        return state

    try:
        cur = con.cursor()
        # Vérifier tables et colonnes
        if not _check_table_exists(con, "forces_snapshots"):
            state.source = FatmanSource.MISSING
            state.audit["reason"] = "table_forces_snapshots_missing"
            return state
        if not _table_has_columns(con, "forces_snapshots", FORCE_COLUMNS):
            state.source = FatmanSource.MISSING
            state.audit["reason"] = "force_columns_missing"
            return state

        # Lire dernière barre fermée pour (symbol, tf)
        cols_sql = ", ".join(FORCE_COLUMNS)
        try:
            row = cur.execute(
                f"""
                SELECT timestamp, bar_time, server_time, {cols_sql}
                FROM forces_snapshots
                WHERE symbol=? AND timeframe=? AND is_closed_bar=1
                ORDER BY bar_time DESC LIMIT 1
                """,
                (symbol, timeframe),
            ).fetchone()
        except sqlite3.OperationalError as e:
            state.source = FatmanSource.MISSING
            state.audit["reason"] = f"query_error:{e}"
            return state
        if row is None:
            state.source = FatmanSource.MISSING
            state.audit["reason"] = "no_bar_for_symbol_tf"
            return state

        timestamp_str, bar_time, server_time, *force_vals = row
        # Map force_vals par colonne
        scores_raw = dict(zip(FORCE_COLUMNS, force_vals))

        # Base / quote
        base, quote = _extract_base_quote(symbol)
        col_base = DEFAULT_CURRENCY_COL.get(base)
        col_quote = DEFAULT_CURRENCY_COL.get(quote)
        if col_base is None or col_quote is None:
            state.source = FatmanSource.MISSING
            state.audit["reason"] = f"unknown_devise:{base}/{quote}"
            return state

        base_score = float(scores_raw[col_base] or 50.0)
        quote_score = float(scores_raw[col_quote] or 50.0)

        # Rang : on doit reconstruire un objet row-like avec toutes les colonnes force_*
        # db_utils.Row n'est pas utilisé ici donc on recalcule via un dict
        scores_dict = {cur_name: float(scores_raw[col] or 50.0)
                       for cur_name, col in DEFAULT_CURRENCY_COL.items()}
        sorted_curs = sorted(scores_dict.items(), key=lambda kv: kv[1], reverse=True)
        ranks = {c: i + 1 for i, (c, _) in enumerate(sorted_curs)}
        base_rank = ranks.get(base, 4)
        quote_rank = ranks.get(quote, 4)

        # Delta / momentum vs barre précédente
        try:
            row2 = cur.execute(
                f"""
                SELECT {cols_sql}
                FROM forces_snapshots
                WHERE symbol=? AND timeframe=? AND is_closed_bar=1
                ORDER BY bar_time DESC LIMIT 2
                """,
                (symbol, timeframe),
            ).fetchall()
        except sqlite3.OperationalError:
            row2 = []

        if len(row2) >= 2:
            prev_scores = dict(zip(FORCE_COLUMNS, row2[1]))
            prev_base = float(prev_scores[col_base] or base_score)
            delta = base_score - prev_base
            if delta > 1.0:
                momentum = Momentum.UP
            elif delta < -1.0:
                momentum = Momentum.DOWN
            else:
                momentum = Momentum.FLAT
        else:
            delta = 0.0
            momentum = Momentum.UNKNOWN

        # Freshness
        bar_time_int = int(bar_time or 0)
        freshness = time.time() - bar_time_int if bar_time_int else float("inf")
        is_stale = freshness > max_age_seconds

        state.timestamp = str(timestamp_str or "")
        state.bar_time = bar_time_int
        state.base_score = base_score
        state.quote_score = quote_score
        state.base_rank = base_rank
        state.quote_rank = quote_rank
        state.delta_score = delta
        state.momentum = momentum
        state.freshness_seconds = freshness
        state.is_stale = is_stale
        state.source = FatmanSource.V9_FORCES_DB
        state.n_bars_read = len(row2) if row2 else 1
        state.audit = {
            "db_age_seconds": freshness,
            "stale_threshold": max_age_seconds,
            "is_stale": is_stale,
            "delta_threshold": 1.0,
            "ranks_per_currency": ranks,
        }
        return state
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────
# API multi-paire / multi-TF — pour orchestrateur
# ─────────────────────────────────────────────────────────────────────
def get_all_fatman_live(
    timeframes: Tuple[str, ...] = ("M15", "M30", "H1", "H4", "D1"),
    symbols: Tuple[str, ...] = (
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
        "USDCAD", "NZDUSD", "USDCHF", "EURGBP",
    ),
    *,
    db_path: str = DEFAULT_DB_PATH,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    seed: Optional[int] = None,
) -> Dict[Tuple[str, str], FatmanLiveState]:
    """Scan multi-paire × multi-TF. Returns dict {(symbol, tf): state}."""
    out: Dict[Tuple[str, str], FatmanLiveState] = {}
    for sym in symbols:
        for tf in timeframes:
            state = get_fatman_live(
                sym, tf, db_path=db_path,
                max_age_seconds=max_age_seconds, seed=seed,
            )
            out[(sym, tf)] = state
    return out


# ─────────────────────────────────────────────────────────────────────
# R6 Fallback sur v10_currency_strength (proxy dégradation)
# ─────────────────────────────────────────────────────────────────────
def get_fatman_with_fallback(
    symbol: str,
    timeframe: str,
    *,
    db_path: str = DEFAULT_DB_PATH,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    pairs_bars: Optional[Dict[str, List[dict]]] = None,
    seed: Optional[int] = None,
) -> FatmanLiveState:
    """Fatman avec R6 fallback explicite vers v10_currency_strength.

    Étapes :
      1. Tente lecture DB v9_forces.db.
      2. Si source = MISSING ou IS_STALE → calcule via v10_currency_strength
         (computé depuis bars OHLCV si pairs_bars fourni).
      3. Retourne FatmanLiveState avec audit trail de la source effective.

    Doctrine : R6 explicite "R6 fail-open → fallback v10_currency_strength"
    """
    primary = get_fatman_live(
        symbol, timeframe,
        db_path=db_path, max_age_seconds=max_age_seconds, seed=seed,
    )
    # Cas nominal : DB fraîche → on la garde
    if primary.source == FatmanSource.V9_FORCES_DB and not primary.is_stale:
        return primary

    # R6 fail-open : DB absente ou stale → calcul proxy v10_currency_strength
    try:
        from .v10_currency_strength import compute_currency_strength
        # Si pas de bars fournis, on retourne quand même le primary
        # marqué comme fallback_strength (sources audibles).
        if not pairs_bars:
            primary.source = FatmanSource.FALLBACK_STRENGTH
            primary.audit["fallback_reason"] = "no_pairs_bars_for_proxy"
            primary.audit["fallback_method"] = "mark_only"
            return primary
        cs = compute_currency_strength(
            timestamp=primary.timestamp or "1970-01-01T00:00:00Z",
            timeframe=timeframe,
            pairs_bars=pairs_bars,
            seed=seed,
        )
        base, quote = _extract_base_quote(symbol)
        # v10_currency_strength scores are 0-100 (percentile rank)
        base_score = cs.scores.get(base, 50.0)
        quote_score = cs.scores.get(quote, 50.0)
        # Rang dérivation depuis ranks Currency Strength
        ranks = {cur: i + 1 for i, cur in enumerate(cs.strongest and sorted(cs.scores, key=lambda c: cs.scores.get(c, 50.0), reverse=True))}
        base_rank = ranks.get(base, 4)
        quote_rank = ranks.get(quote, 4)
        # Construire FatmanLiveState basé sur proxy
        return FatmanLiveState(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=primary.timestamp or "",
            bar_time=primary.bar_time,
            base_score=base_score,
            quote_score=quote_score,
            base_rank=base_rank,
            quote_rank=quote_rank,
            delta_score=primary.delta_score,
            momentum=primary.momentum,
            freshness_seconds=primary.freshness_seconds,
            is_stale=primary.is_stale,
            source=FatmanSource.FALLBACK_STRENGTH,
            n_bars_read=len(pairs_bars.get(symbol, []) or []),
            db_path=db_path,
            seed=seed,
            audit={
                "primary_source": primary.source.value,
                "fallback_method": "v10_currency_strength",
                "fallback_reason": "db_stale" if primary.is_stale else "db_missing",
                "primary_audit": primary.audit,
                "currency_strength_used": True,
            },
        )
    except Exception as e:
        primary.source = FatmanSource.COMPUTE_PROXY
        primary.audit["fallback_failed"] = str(e)
        return primary


__all__ = [
    "FatmanLiveState",
    "FatmanSource",
    "Momentum",
    "DEFAULT_DB_PATH",
    "DEFAULT_MAX_AGE_SECONDS",
    "FORCE_COLUMNS",
    "DEFAULT_CURRENCY_COL",
    "get_fatman_live",
    "get_all_fatman_live",
    "get_fatman_with_fallback",
    "freshness_check",
]
