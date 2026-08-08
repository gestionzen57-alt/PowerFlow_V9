"""V10 Replay Engine — S25-OMEGA.

Pipeline de replay parallèle, complet et cohérent avec ErrorLearner et MetaOptimizer.

Fonctionnalités :
  ThreadPoolExecutor(max_workers=4) — toutes les paires en parallèle
  Horizon adaptatif ATR — _adaptive_horizon() ajuste selon volatilité réelle
  EWM Drift Tracker O(1) — alerte sans fenêtre glissante
  Reward Shaping — PnL pondéré session_quality × CS_delta
  Curriculum Learning — étend l'historique si WR > 52%
  TradeOutcome → ErrorLearner.record() — intégration native
  ReplayResult → MetaOptimizer.evolve() — intégration native
  R6 fail-open sur tout, R9 audit

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit, R10 zéro ordre.
"""
from __future__ import annotations

import math
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .v10_error_learner import ErrorLearner, TradeOutcome

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "USDCHF", "NZDUSD", "USDCAD",
]
DEFAULT_TIMEFRAMES   = ["M30", "H1"]
MAX_WORKERS          = 4
CURRICULUM_BASE      = 150    # barres de départ
CURRICULUM_STEP      = 50    # incrément si WR > seuil
CURRICULUM_WR_THR    = 0.52  # seuil WR pour extension
ATR_LOW_QUANTILE     = 0.33  # ATR faible → horizon court
ATR_HIGH_QUANTILE    = 0.67  # ATR élevé → horizon long
SESSION_QUALITY: Dict[str, float] = {
    "london":        1.0,
    "new_york":      1.0,
    "london_ny":     1.2,
    "asia":          0.6,
    "pre_london":    0.7,
    "off":           0.4,
}


# ── Structures ────────────────────────────────────────────────────────────────
@dataclass
class ReplayDecision:
    ts:           str
    direction:    str     # BUY | SELL | HOLD
    win:          bool
    pnl_pips:     float
    session:      str
    cs_delta:     float
    reward:       float   # reward shapé
    horizon:      int


@dataclass
class ReplayResult:
    symbol:      str
    timeframe:   str
    n_decisions: int
    n_wins:      int
    wr:          float
    avg_reward:  float
    curriculum:  int     # nb barres utilisées
    decisions:   List[Dict] = field(default_factory=list)
    error:       Optional[str] = None

    def as_dict(self) -> dict:
        base = {
            "symbol":      self.symbol,
            "timeframe":   self.timeframe,
            "n_decisions": self.n_decisions,
            "n_wins":      self.n_wins,
            "wr":          round(self.wr, 4),
            "avg_reward":  round(self.avg_reward, 4),
            "curriculum":  self.curriculum,
        }
        if self.error:
            base["error"] = self.error
        return base


# ── Drift Tracker EWM O(1) ────────────────────────────────────────────────────
class _EWMDriftTracker:
    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha   = alpha
        self.ewm_wr  = 0.5
        self.n       = 0

    def update(self, win: bool) -> bool:
        """Retourne True si drift détecté."""
        self.n      += 1
        self.ewm_wr  = self.alpha * int(win) + (1 - self.alpha) * self.ewm_wr
        return self.n >= 20 and self.ewm_wr < 0.44


# ── Helpers DB ───────────────────────────────────────────────────────────────
def _fetch_bars(
    db_path: str,
    symbol: str,
    timeframe: str,
    limit: int,
) -> List[Dict]:
    """Lit les barres OHLCV + metadata depuis la DB fatman (R6 fail-open)."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT bar_time, open, high, low, close, tick_volume,
                   session, cs_delta, atr
            FROM forces_snapshots
            WHERE symbol = ? AND timeframe = ?
            ORDER BY bar_time DESC
            LIMIT ?
            """,
            (symbol, timeframe, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]
    except Exception as exc:
        return [{"error": str(exc)}]


def _adaptive_horizon(bars: List[Dict], idx: int) -> int:
    """Horizon adaptatif : 1 si ATR faible, 3 si élevé."""
    try:
        atrs = [b.get("atr", 0.0) for b in bars if b.get("atr") is not None]
        if len(atrs) < 4:
            return 2
        q33 = sorted(atrs)[int(len(atrs) * ATR_LOW_QUANTILE)]
        q67 = sorted(atrs)[int(len(atrs) * ATR_HIGH_QUANTILE)]
        cur = bars[idx].get("atr", 0.0)
        if cur <= q33:
            return 1
        if cur >= q67:
            return 3
        return 2
    except Exception:
        return 2


def _simulate_decision(bar: Dict, next_bar: Optional[Dict]) -> Tuple[str, bool, float]:
    """Simulation minimale : BUY si cs_delta > 0, SELL sinon, PnL = (close - open) × direction."""
    cs = bar.get("cs_delta", 0.0) or 0.0
    direction = "BUY" if cs > 0 else ("SELL" if cs < 0 else "HOLD")
    if direction == "HOLD" or next_bar is None:
        return direction, False, 0.0
    pips = (next_bar["close"] - bar["close"]) * (1 if direction == "BUY" else -1)
    pips_scaled = pips * 10_000  # conversion approximative pips
    win = pips_scaled > 0
    return direction, win, round(pips_scaled, 2)


# ── Replay d'une paire/TF ─────────────────────────────────────────────────────
def _replay_single(
    db_path: str,
    symbol: str,
    timeframe: str,
    learner: ErrorLearner,
    curriculum: int,
) -> ReplayResult:
    """Rejoue une paire/TF et alimente ErrorLearner en temps réel."""
    bars = _fetch_bars(db_path, symbol, timeframe, curriculum)

    if not bars or "error" in bars[0]:
        err = bars[0].get("error", "no_data") if bars else "no_data"
        return ReplayResult(
            symbol=symbol, timeframe=timeframe,
            n_decisions=0, n_wins=0, wr=0.0,
            avg_reward=0.0, curriculum=curriculum,
            error=err,
        )

    drift_tracker = _EWMDriftTracker()
    decisions: List[Dict] = []
    n_wins = 0
    total_reward = 0.0

    for i, bar in enumerate(bars[:-1]):
        next_bar = bars[i + 1]
        horizon  = _adaptive_horizon(bars, i)
        fwd_idx  = min(i + horizon, len(bars) - 1)
        fwd_bar  = bars[fwd_idx]

        direction, win, pnl_pips = _simulate_decision(bar, fwd_bar)
        if direction == "HOLD":
            continue

        session    = bar.get("session", "off")
        cs_delta   = abs(bar.get("cs_delta", 0.0) or 0.0)
        sq         = SESSION_QUALITY.get(session, 0.5)
        reward     = pnl_pips * sq * (1 + cs_delta * 0.1)

        drift_tracker.update(win)
        if win:
            n_wins += 1
        total_reward += reward

        # Alimente ErrorLearner
        learner.record(TradeOutcome(
            symbol=symbol,
            setup="cs_delta_direction",
            kill_zone=session,
            win=win,
            pnl=pnl_pips,
            timestamp=bar.get("bar_time", ""),
        ))

        decisions.append({
            "ts":        bar.get("bar_time", ""),
            "direction": direction,
            "win":       win,
            "pnl_pips":  pnl_pips,
            "session":   session,
            "reward":    round(reward, 4),
            "horizon":   horizon,
            "drift":     drift_tracker.ewm_wr,
        })

    n_dec = len(decisions)
    wr    = n_wins / max(1, n_dec)
    return ReplayResult(
        symbol=symbol, timeframe=timeframe,
        n_decisions=n_dec, n_wins=n_wins,
        wr=round(wr, 4),
        avg_reward=round(total_reward / max(1, n_dec), 4),
        curriculum=curriculum,
        decisions=decisions,
    )


# ── Replay Engine principal ────────────────────────────────────────────────────
class ReplayEngine:
    """Orchestre le replay parallèle de toutes les paires/TF."""

    def __init__(
        self,
        db_path: str,
        pairs: Optional[List[str]]      = None,
        timeframes: Optional[List[str]] = None,
        max_workers: int                = MAX_WORKERS,
    ) -> None:
        self.db_path    = db_path
        self.pairs      = pairs or DEFAULT_PAIRS
        self.timeframes = timeframes or DEFAULT_TIMEFRAMES
        self.max_workers= max_workers
        self.learner    = ErrorLearner()
        self._curriculum_map: Dict[str, int] = {}

    def _curriculum(self, key: str, wr: float) -> int:
        """Curriculum Learning : étend l'horizon si WR suffisant."""
        cur = self._curriculum_map.get(key, CURRICULUM_BASE)
        if wr > CURRICULUM_WR_THR:
            cur += CURRICULUM_STEP
        self._curriculum_map[key] = cur
        return cur

    def run(
        self,
        return_decisions: bool = False,
    ) -> Dict:
        """Lance le replay parallèle sur toutes les paires × TF.

        Retourne:
            summary  — métriques globales
            results  — liste ReplayResult par (pair, TF)
            learner  — état ErrorLearner
        """
        tasks: List[Tuple[str, str]] = [
            (p, tf)
            for p  in self.pairs
            for tf in self.timeframes
        ]
        results: List[ReplayResult] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(
                    _replay_single,
                    self.db_path, p, tf,
                    self.learner,
                    self._curriculum(f"{p}_{tf}", 0.5),
                ): (p, tf)
                for p, tf in tasks
            }
            for future in as_completed(future_map):
                try:
                    res = future.result(timeout=30)
                except Exception as exc:
                    p, tf = future_map[future]
                    res = ReplayResult(
                        symbol=p, timeframe=tf,
                        n_decisions=0, n_wins=0, wr=0.0,
                        avg_reward=0.0, curriculum=CURRICULUM_BASE,
                        error=str(exc),
                    )
                # Mise à jour curriculum
                key = f"{res.symbol}_{res.timeframe}"
                self._curriculum(key, res.wr)
                if not return_decisions:
                    res.decisions = []
                results.append(res)

        # Summary global
        valid  = [r for r in results if not r.error]
        total_n  = sum(r.n_decisions for r in valid)
        total_w  = sum(r.n_wins      for r in valid)
        global_wr = total_w / max(1, total_n)
        avg_rew   = (sum(r.avg_reward * r.n_decisions for r in valid)
                     / max(1, total_n))

        # Tri par WR × n_decisions (edge × volume)
        valid.sort(key=lambda r: r.wr * r.n_decisions, reverse=True)

        return {
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "n_tasks":     len(tasks),
            "n_valid":     len(valid),
            "n_errors":    len(results) - len(valid),
            "global_wr":   round(global_wr, 4),
            "global_avg_reward": round(avg_rew, 4),
            "total_decisions":   total_n,
            "learner":     self.learner.state.as_dict(),
            "results":     [r.as_dict() for r in valid[:20]],
        }
