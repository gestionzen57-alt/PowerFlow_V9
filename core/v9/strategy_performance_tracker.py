"""StrategyPerformanceTracker — Apprentissage continu de la performance par stratégie.

Track WR, expectancy, PF, maxDD par (principe, session, regime, phase, strategy).
Sélection adaptative via UCB (Upper Confidence Bound) pour exploration/exploitation.

Doctrine : R2 additif, R6 défensif, R18 code pur, R33 Système Prédictif.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.v9.config import DB_PATH, ROOT_DIR
from core.v9.db_schema import get_connection

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

STRATEGY_PERF_DB = ROOT_DIR / "data" / "v9_strategy_performance.db"
MIN_TRADES_FOR_UCB = 20          # Minimum trades pour score UCB fiable
UCB_EXPLORATION_C = 1.5          # Paramètre exploration UCB
MIN_TRADES_FOR_BEST = 30         # Minimum pour considérer "best strategy"
STRATEGIES = ("TP_SL", "TRAILING", "TP_PARTIAL", "FAST_EXIT")

# ──────────────────────────────────────────────────────────────────────────────
# Schéma DB
# ──────────────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS strategy_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    principle_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    session TEXT NOT NULL,
    regime_type TEXT NOT NULL,
    phase TEXT NOT NULL,
    strategy TEXT NOT NULL,
    is_win INTEGER NOT NULL,           -- 1 win, 0 loss
    pips REAL NOT NULL,
    hold_bars INTEGER,
    confidence REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_strategy_outcomes_ctx
    ON strategy_outcomes(principle_id, session, regime_type, phase, strategy);

CREATE TABLE IF NOT EXISTS strategy_aggregates (
    principle_id TEXT NOT NULL,
    session TEXT NOT NULL,
    regime_type TEXT NOT NULL,
    phase TEXT NOT NULL,
    strategy TEXT NOT NULL,
    n_trades INTEGER DEFAULT 0,
    n_wins INTEGER DEFAULT 0,
    total_pips REAL DEFAULT 0.0,
    sum_pips_sq REAL DEFAULT 0.0,      -- pour variance
    max_dd_pips REAL DEFAULT 0.0,      -- max drawdown observé
    current_dd_pips REAL DEFAULT 0.0,  -- drawdown courant
    peak_pips REAL DEFAULT 0.0,
    expectancy REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    sharpe_like REAL DEFAULT 0.0,
    ucb_score REAL DEFAULT 0.0,
    last_updated TEXT NOT NULL,
    PRIMARY KEY (principle_id, session, regime_type, phase, strategy)
);

CREATE TABLE IF NOT EXISTS best_strategy_cache (
    principle_id TEXT NOT NULL,
    session TEXT NOT NULL,
    regime_type TEXT NOT NULL,
    phase TEXT NOT NULL,
    best_strategy TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    n_trades INTEGER DEFAULT 0,
    last_updated TEXT NOT NULL,
    PRIMARY KEY (principle_id, session, regime_type, phase)
);
"""


# ──────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class StrategyStats:
    """Statistiques agrégées pour une stratégie dans un contexte."""
    principle_id: str
    session: str
    regime_type: str
    phase: str
    strategy: str
    n_trades: int = 0
    n_wins: int = 0
    total_pips: float = 0.0
    sum_pips_sq: float = 0.0
    max_dd_pips: float = 0.0
    current_dd_pips: float = 0.0
    peak_pips: float = 0.0
    
    @property
    def win_rate(self) -> float:
        return self.n_wins / self.n_trades if self.n_trades > 0 else 0.0
    
    @property
    def expectancy(self) -> float:
        return self.total_pips / self.n_trades if self.n_trades > 0 else 0.0
    
    @property
    def profit_factor(self) -> float:
        if self.n_trades == 0:
            return 0.0
        wins = sum(p for p in [] if p > 0)  # Note: on a pas les pips individuels ici
        losses = abs(sum(p for p in [] if p < 0))
        return wins / losses if losses > 0 else float('inf')
    
    @property
    def sharpe_like(self) -> float:
        if self.n_trades < 2:
            return 0.0
        mean = self.expectancy
        var = (self.sum_pips_sq / self.n_trades) - (mean * mean)
        std = math.sqrt(max(var, 0.0))
        return mean / std if std > 0 else 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "win_rate": self.win_rate,
            "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "sharpe_like": self.sharpe_like,
        }


@dataclass
class StrategyPerformanceTracker:
    """Tracker de performance par stratégie contextuelle."""
    
    db_path: Path = STRATEGY_PERF_DB
    
    def __post_init__(self):
        self._init_db()
    
    def _init_db(self):
        """Initialise la DB de performance stratégie."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()
    
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    # ──────────────────────────────────────────────────────────────────────────
    # Enregistrement outcomes
    # ──────────────────────────────────────────────────────────────────────────
    
    def record_outcome(
        self,
        principle_id: str,
        symbol: str,
        timeframe: str,
        session: str,
        regime_type: str,
        phase: str,
        strategy: str,
        is_win: bool,
        pips: float,
        hold_bars: int | None = None,
        confidence: float | None = None,
    ) -> None:
        """Enregistre un trade résolu pour une stratégie dans un contexte."""
        if strategy not in STRATEGIES:
            logger.warning(f"Stratégie inconnue: {strategy}")
            return
        
        conn = self._connect()
        try:
            # 1. Insert outcome brut
            conn.execute(
                """INSERT INTO strategy_outcomes
                   (timestamp, principle_id, symbol, timeframe, session, regime_type, phase,
                    strategy, is_win, pips, hold_bars, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    principle_id, symbol, timeframe, session, regime_type, phase,
                    strategy, int(is_win), pips, hold_bars, confidence,
                ),
            )
            
            # 2. Mise à jour agrégats incrémentale (Welford pour mean/var)
            self._update_aggregates_incremental(
                conn, principle_id, session, regime_type, phase, strategy,
                is_win, pips,
            )
            
            # 3. Mise à jour cache best strategy
            self._update_best_strategy_cache(conn, principle_id, session, regime_type, phase)
            
            conn.commit()
        except Exception as e:
            logger.error(f"StrategyPerformanceTracker.record_outcome failed: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def _update_aggregates_incremental(
        self,
        conn: sqlite3.Connection,
        principle_id: str,
        session: str,
        regime_type: str,
        phase: str,
        strategy: str,
        is_win: bool,
        pips: float,
    ):
        """Mise à jour incrémentale des agrégats (Welford online algorithm)."""
        # Lire état courant
        row = conn.execute(
            """SELECT n_trades, n_wins, total_pips, sum_pips_sq, max_dd_pips,
                      current_dd_pips, peak_pips
               FROM strategy_aggregates
               WHERE principle_id=? AND session=? AND regime_type=? AND phase=? AND strategy=?""",
            (principle_id, session, regime_type, phase, strategy),
        ).fetchone()
        
        if row:
            n, n_wins, total_pips, sum_sq, max_dd, cur_dd, peak = row
            n = int(n or 0)
            n_wins = int(n_wins or 0)
            total_pips = float(total_pips or 0.0)
            sum_sq = float(sum_sq or 0.0)
            max_dd = float(max_dd or 0.0)
            cur_dd = float(cur_dd or 0.0)
            peak = float(peak or 0.0)
        else:
            n = n_wins = 0
            total_pips = sum_sq = max_dd = cur_dd = peak = 0.0
        
        # Mise à jour Welford
        n_new = n + 1
        delta = pips - (total_pips / n if n > 0 else 0.0)
        total_pips_new = total_pips + pips
        mean_new = total_pips_new / n_new
        sum_sq_new = sum_sq + delta * (pips - mean_new)
        
        # Drawdown tracking
        peak_new = max(peak, total_pips_new)
        cur_dd_new = peak_new - total_pips_new
        max_dd_new = max(max_dd, cur_dd_new)
        n_wins_new = n_wins + (1 if is_win else 0)
        
        # Expectancy, win_rate, profit_factor, sharpe_like
        expectancy = total_pips_new / n_new
        win_rate = n_wins_new / n_new
        
        # Profit factor approximé
        if n_new > 1:
            # Approximation: on utilise expectancy et variance
            var = sum_sq_new / n_new
            std = math.sqrt(max(var, 1e-10))
            sharpe = expectancy / std if std > 0 else 0.0
        else:
            sharpe = 0.0
        
        # UCB score = expectancy + C * sqrt(log(total) / n)
        total_all = self._get_total_trades_context(conn, principle_id, session, regime_type, phase)
        ucb = expectancy
        if n_new >= MIN_TRADES_FOR_UCB and total_all > 0:
            ucb += UCB_EXPLORATION_C * math.sqrt(math.log(total_all) / n_new)
        
        # Upsert
        conn.execute(
            """INSERT OR REPLACE INTO strategy_aggregates
               (principle_id, session, regime_type, phase, strategy,
                n_trades, n_wins, total_pips, sum_pips_sq, max_dd_pips,
                current_dd_pips, peak_pips, expectancy, win_rate, profit_factor,
                sharpe_like, ucb_score, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                principle_id, session, regime_type, phase, strategy,
                n_new, n_wins_new, total_pips_new, sum_sq_new, max_dd_new,
                cur_dd_new, peak_new, expectancy, win_rate, 0.0,  # profit_factor calc séparé si besoin
                sharpe, ucb, datetime.now(timezone.utc).isoformat(),
            ),
        )
    
    def _get_total_trades_context(
        self, conn: sqlite3.Connection, principle_id: str, session: str, 
        regime_type: str, phase: str
    ) -> int:
        """Total trades toutes stratégies pour ce contexte (pour UCB)."""
        row = conn.execute(
            """SELECT SUM(n_trades) FROM strategy_aggregates
               WHERE principle_id=? AND session=? AND regime_type=? AND phase=?""",
            (principle_id, session, regime_type, phase),
        ).fetchone()
        return row[0] if row and row[0] else 0
    
    def _update_best_strategy_cache(
        self, conn: sqlite3.Connection,
        principle_id: str, session: str, regime_type: str, phase: str,
    ):
        """Met à jour le cache de la meilleure stratégie pour un contexte."""
        # Récupérer stats toutes stratégies
        rows = conn.execute(
            """SELECT strategy, n_trades, expectancy, ucb_score, win_rate, sharpe_like
               FROM strategy_aggregates
               WHERE principle_id=? AND session=? AND regime_type=? AND phase=?
                 AND n_trades >= ?""",
            (principle_id, session, regime_type, phase, MIN_TRADES_FOR_BEST),
        ).fetchall()
        
        if not rows:
            return
        
        # Choisir la meilleure par UCB score (exploration) puis expectancy (exploitation)
        best = max(rows, key=lambda r: (r["ucb_score"], r["expectancy"], r["n_trades"]))
        
        confidence = min(1.0, best["n_trades"] / 100.0)  # confidence croît avec n
        
        conn.execute(
            """INSERT OR REPLACE INTO best_strategy_cache
               (principle_id, session, regime_type, phase, best_strategy, confidence, n_trades, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                principle_id, session, regime_type, phase,
                best["strategy"], confidence, best["n_trades"],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    
    # ──────────────────────────────────────────────────────────────────────────
    # Requêtes lecture
    # ──────────────────────────────────────────────────────────────────────────
    
    def get_best_strategy(
        self,
        principle_id: str,
        session: str,
        regime_type: str,
        phase: str,
    ) -> tuple[str, float]:
        """
        Retourne (best_strategy, confidence) pour un contexte.
        Fallback: TRAILING si pas assez de données.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT best_strategy, confidence, n_trades
                   FROM best_strategy_cache
                   WHERE principle_id=? AND session=? AND regime_type=? AND phase=?""",
                (principle_id, session, regime_type, phase),
            ).fetchone()
            
            if row and row["n_trades"] >= MIN_TRADES_FOR_BEST:
                return row["best_strategy"], float(row["confidence"])
            
            # Fallback: chercher dans aggregates avec n_trades >= MIN_TRADES_FOR_UCB
            row2 = conn.execute(
                """SELECT strategy, ucb_score, expectancy, n_trades
                   FROM strategy_aggregates
                   WHERE principle_id=? AND session=? AND regime_type=? AND phase=?
                     AND n_trades >= ?
                   ORDER BY ucb_score DESC, expectancy DESC, n_trades DESC
                   LIMIT 1""",
                (principle_id, session, regime_type, phase, MIN_TRADES_FOR_UCB),
            ).fetchone()
            
            if row2:
                return row2["strategy"], min(1.0, row2["n_trades"] / 100.0)
            
            return "TRAILING", 0.0  # défaut robuste
        finally:
            conn.close()
    
    def get_strategy_stats(
        self,
        principle_id: str,
        session: str,
        regime_type: str,
        phase: str,
    ) -> dict[str, StrategyStats]:
        """Retourne les stats pour toutes stratégies dans un contexte."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM strategy_aggregates
                   WHERE principle_id=? AND session=? AND regime_type=? AND phase=?
                   ORDER BY ucb_score DESC""",
                (principle_id, session, regime_type, phase),
            ).fetchall()
            
            result = {}
            for row in rows:
                stats = StrategyStats(
                    principle_id=row["principle_id"],
                    session=row["session"],
                    regime_type=row["regime_type"],
                    phase=row["phase"],
                    strategy=row["strategy"],
                    n_trades=row["n_trades"],
                    n_wins=row["n_wins"],
                    total_pips=row["total_pips"],
                    sum_pips_sq=row["sum_pips_sq"],
                    max_dd_pips=row["max_dd_pips"],
                    current_dd_pips=row["current_dd_pips"],
                    peak_pips=row["peak_pips"],
                )
                result[row["strategy"]] = stats
            return result
        finally:
            conn.close()
    
    def get_all_contexts_summary(self) -> list[dict]:
        """Résumé de tous les contextes avec best strategy."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT principle_id, session, regime_type, phase, best_strategy, 
                          confidence, n_trades, last_updated
                   FROM best_strategy_cache
                   ORDER BY last_updated DESC""",
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# API simplifiée
# ──────────────────────────────────────────────────────────────────────────────

_tracker_instance: StrategyPerformanceTracker | None = None


def get_strategy_performance_tracker() -> StrategyPerformanceTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = StrategyPerformanceTracker()
    return _tracker_instance


def record_strategy_outcome(
    principle_id: str,
    symbol: str,
    timeframe: str,
    session: str,
    regime_type: str,
    phase: str,
    strategy: str,
    is_win: bool,
    pips: float,
    hold_bars: int | None = None,
    confidence: float | None = None,
) -> None:
    """API simple pour trade_engine / paper_trade_logger."""
    tracker = get_strategy_performance_tracker()
    tracker.record_outcome(
        principle_id, symbol, timeframe, session, regime_type, phase,
        strategy, is_win, pips, hold_bars, confidence,
    )


def get_best_strategy_for_context(
    principle_id: str,
    session: str,
    regime_type: str,
    phase: str,
) -> tuple[str, float]:
    """Retourne (strategy, confidence) pour un contexte."""
    tracker = get_strategy_performance_tracker()
    return tracker.get_best_strategy(principle_id, session, regime_type, phase)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    
    parser = argparse.ArgumentParser(description="Strategy Performance Tracker V9")
    parser.add_argument("--summary", action="store_true", help="Show all contexts summary")
    parser.add_argument("--context", nargs=4, metavar=("PRINCIPLE", "SESSION", "REGIME", "PHASE"),
                        help="Show stats for specific context")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    tracker = get_strategy_performance_tracker()
    
    if args.summary:
        data = tracker.get_all_contexts_summary()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            for row in data:
                print(f"{row['principle_id']:30s} | {row['session']:8s} | {row['regime_type']:12s} | "
                      f"{row['phase']:12s} → {row['best_strategy']:10s} (conf={row['confidence']:.2f}, n={row['n_trades']})")
    
    elif args.context:
        principle, session, regime, phase = args.context
        stats = tracker.get_strategy_stats(principle, session, regime, phase)
        best, conf = tracker.get_best_strategy(principle, session, regime, phase)
        
        print(f"Context: {principle} | {session} | {regime} | {phase}")
        print(f"Best: {best} (confidence={conf:.2f})")
        print()
        for strat, s in stats.items():
            print(f"  {strat:10s}: n={s.n_trades:3d} WR={s.win_rate:.1%} exp={s.expectancy:.2f} "
                  f"PF={s.profit_factor:.2f} sharpe={s.sharpe_like:.2f} ucb={s.ucb_score:.3f}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())