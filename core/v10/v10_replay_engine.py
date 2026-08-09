"""V10 Replay Engine — S25-OMEGA Full-Stack v2.

Corrections post-rapport Zcode (2026-08-09) :
  - Pipeline authentique via DecisionPipeline (identique live)
  - Fallback 4 niveaux : DecisionPipeline → SignalGeneratorLive → SignalEngine → CS proxy
  - Fix LearningContinuum wrapper robuste
  - Fix fetch_bars colonne 'pair' vs 'symbol'
  - Fix NZDUSD vide (skip silencieux)
  - Pip factor JPY-aware
  - Rapport JSON enrichi : pipeline_used, blocked_reasons, sessions

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit, R10 zéro ordre.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ── imports V10 — fail-open R6 ────────────────────────────────────────────
# Niveau 1 : Pipeline complet authentique (= live)
try:
    from .v10_decision_pipeline import DecisionPipeline
    _HAS_PIPELINE = True
except ImportError:
    _HAS_PIPELINE = False

# Niveau 2 : SignalGeneratorLive (Force+Structure+Contexte+VSA+Fractal)
try:
    from .v10_signal_generator_live import SignalGeneratorLive
    _HAS_SGL = True
except ImportError:
    _HAS_SGL = False

# Niveau 3 : SignalEngine (CS + confluence)
try:
    from .v10_signal_engine import SignalEngine
    _HAS_SE = True
except ImportError:
    _HAS_SE = False

# Modules apprentissage
try:
    from .v10_error_learner import ErrorLearner, TradeOutcome
    _HAS_EL = True
except ImportError:
    _HAS_EL = False
    ErrorLearner = None
    TradeOutcome = None

try:
    from .v10_meta_optimizer import MetaOptimizer
    _HAS_MO = True
except ImportError:
    _HAS_MO = False

try:
    from .v10_learning_continuum import LearningContinuum
    _HAS_LC = True
except ImportError:
    _HAS_LC = False

try:
    from .v10_learning_persistence import LearningPersistence
    _HAS_LP = True
except ImportError:
    _HAS_LP = False

try:
    from .v10_rl_adapter import RLAdapter
    _HAS_RL = True
except ImportError:
    _HAS_RL = False

try:
    from .v10_bayesian_recalibrator import BayesianRecalibrator
    _HAS_BAYES = True
except ImportError:
    _HAS_BAYES = False

try:
    from .v10_session_filter import SessionFilter
    _HAS_SF = True
except ImportError:
    _HAS_SF = False

try:
    from .v10_spread_guard import SpreadGuard
    _HAS_SG = True
except ImportError:
    _HAS_SG = False

logger = logging.getLogger(__name__)

# ── Constantes ───────────────────────────────────────────────────────────────
DEFAULT_PAIRS: List[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "USDCHF", "NZDUSD", "USDCAD", "EURJPY",
]
DEFAULT_TIMEFRAMES: List[str] = ["M30", "H1"]
MAX_WORKERS:     int   = 4
MAX_BARS:        int   = 2000
WINDOW_BARS:     int   = 50
SPREAD_PIPS:     float = 2.0
CURRICULUM_BASE: int   = 200
CURRICULUM_STEP: int   = 100
CURRICULUM_WR_THR: float = 0.54
REPORTS_DIR: Path = Path("reports")

SESSION_QUALITY: Dict[str, float] = {
    "london":     1.0,
    "new_york":   1.0,
    "london_ny":  1.2,
    "asia":       0.6,
    "pre_london": 0.7,
    "off":        0.4,
}

CURRENCY_MAP: Dict[str, Tuple[str, str]] = {
    "EURUSD": ("eur", "usd"), "GBPUSD": ("gbp", "usd"),
    "USDJPY": ("usd", "jpy"), "AUDUSD": ("aud", "usd"),
    "USDCHF": ("usd", "chf"), "NZDUSD": ("nzd", "usd"),
    "USDCAD": ("usd", "cad"), "EURJPY": ("eur", "jpy"),
    "EURGBP": ("eur", "gbp"), "GBPJPY": ("gbp", "jpy"),
    "AUDJPY": ("aud", "jpy"), "CADJPY": ("cad", "jpy"),
}


# ── Dataclasses ───────────────────────────────────────────────────────────────
@dataclass
class TradeResult:
    pair:         str
    tf:           str
    bar_time:     int
    direction:    str
    horizon:      int
    pnl_pips:     float
    won:          bool
    signal_score: float = 0.0
    pipeline_used: str  = "cs_proxy"
    context_snap: Dict  = field(default_factory=dict)


@dataclass
class ReplayResult:
    """Compatible ascendant avec la version précédente."""
    symbol:      str
    timeframe:   str
    n_decisions: int
    n_wins:      int
    wr:          float
    avg_reward:  float
    curriculum:  int
    decisions:   List[Dict] = field(default_factory=list)
    error:       Optional[str] = None
    pnl_net:          float = 0.0
    profit_factor:    float = 0.0
    sharpe:           float = 0.0
    max_drawdown:     float = 0.0
    holds:            int   = 0
    blocked_reasons:  Dict  = field(default_factory=dict)
    modules_coverage: List[str] = field(default_factory=list)
    sessions:         Dict  = field(default_factory=dict)
    pipeline_used:    str   = "unknown"

    def as_dict(self) -> Dict:
        d = {
            "symbol":           self.symbol,
            "timeframe":        self.timeframe,
            "n_decisions":      self.n_decisions,
            "n_wins":           self.n_wins,
            "wr":               round(self.wr, 4),
            "avg_reward":       round(self.avg_reward, 4),
            "curriculum":       self.curriculum,
            "pnl_net":          round(self.pnl_net, 2),
            "profit_factor":    round(self.profit_factor, 4),
            "sharpe":           round(self.sharpe, 4),
            "max_drawdown":     round(self.max_drawdown, 4),
            "holds":            self.holds,
            "blocked_reasons":  self.blocked_reasons,
            "modules_coverage": self.modules_coverage,
            "sessions":         self.sessions,
            "pipeline_used":    self.pipeline_used,
            "status":           "FULLSTACK_V10_v2",
        }
        if self.error:
            d["error"] = self.error
        return d


# ── EWM Drift Tracker O(1) ────────────────────────────────────────────────────
class _EWMDriftTracker:
    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha  = alpha
        self.ewm_wr = 0.5
        self.n      = 0

    def update(self, win: bool) -> bool:
        self.n      += 1
        self.ewm_wr  = self.alpha * int(win) + (1 - self.alpha) * self.ewm_wr
        return self.n >= 20 and self.ewm_wr < 0.44


# ── ReplayEngine ─────────────────────────────────────────────────────────────
class ReplayEngine:
    """
    Replay Engine V10 Full-Stack v2.

    Pipeline de décision par barre (identique au live) :
      1. DecisionPipeline.process()  (Force+Struct+Context+VSA+Fractal+MCG+HMM+SMC+ICT+Bayes+Risk)
      2. Fallback : SignalGeneratorLive.generate()
      3. Fallback : SignalEngine.score()
      4. Fallback : CS proxy force_X - force_USD

    Compatibilité ascendante : run() et run_all() identiques en signature.
    """

    def __init__(
        self,
        db_path:     str              = "data/powerflow.db",
        pairs:       Optional[List[str]] = None,
        timeframes:  Optional[List[str]] = None,
        max_workers: int              = MAX_WORKERS,
    ) -> None:
        self.db_path     = db_path
        self.pairs       = pairs      or DEFAULT_PAIRS
        self.timeframes  = timeframes or DEFAULT_TIMEFRAMES
        self.max_workers = max_workers
        self._curriculum_map: Dict[str, int] = {}
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self._init_modules()

    # ── init ────────────────────────────────────────────────────────────────
    def _init_modules(self) -> None:
        # Niveau 1 : pipeline complet
        self.pipeline: Optional[Any] = None
        if _HAS_PIPELINE:
            try:
                self.pipeline = DecisionPipeline(db_path=self.db_path)
                logger.info("[ReplayEngine] Pipeline: DecisionPipeline ✅")
            except Exception as e:
                logger.warning(f"[ReplayEngine] DecisionPipeline init: {e}")

        # Niveau 2 : SignalGeneratorLive
        self.sgl: Optional[Any] = None
        if _HAS_SGL and self.pipeline is None:
            try:
                self.sgl = SignalGeneratorLive(db_path=self.db_path)
                logger.info("[ReplayEngine] Pipeline: SignalGeneratorLive ✅")
            except Exception as e:
                logger.warning(f"[ReplayEngine] SignalGeneratorLive init: {e}")

        # Niveau 3 : SignalEngine
        self.signal_engine: Optional[Any] = None
        if _HAS_SE and self.pipeline is None and self.sgl is None:
            try:
                self.signal_engine = SignalEngine()
                logger.info("[ReplayEngine] Pipeline: SignalEngine ✅")
            except Exception as e:
                logger.warning(f"[ReplayEngine] SignalEngine init: {e}")

        # Apprentissage
        self.learner     = ErrorLearner()         if _HAS_EL    else None
        self.meta_opt    = MetaOptimizer()         if _HAS_MO    else None
        self.rl          = RLAdapter()             if _HAS_RL    else None
        self.bayes       = BayesianRecalibrator()  if _HAS_BAYES else None
        self.session_filt= SessionFilter()         if _HAS_SF    else None
        self.spread_guard= SpreadGuard()           if _HAS_SG    else None
        self.persistence = LearningPersistence()   if _HAS_LP    else None
        self.lc          = LearningContinuum()     if _HAS_LC    else None

        active = [
            ("DecisionPipeline", self.pipeline),
            ("SignalGeneratorLive", self.sgl),
            ("SignalEngine", self.signal_engine),
            ("ErrorLearner", self.learner),
            ("MetaOptimizer", self.meta_opt),
            ("RLAdapter", self.rl),
            ("Bayesian", self.bayes),
            ("SessionFilter", self.session_filt),
            ("SpreadGuard", self.spread_guard),
            ("LearningContinuum", self.lc),
        ]
        loaded = [k for k, v in active if v is not None]
        logger.info(f"[ReplayEngine] {len(loaded)} modules actifs: {loaded}")

    # ── lecture DB ────────────────────────────────────────────────────────────
    def _fetch_bars(self, symbol: str, tf: str, limit: int):
        """Charge forces_snapshots avec détection auto colonnes pair/symbol."""
        import pandas as pd
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=10)
            # Détecter colonnes disponibles
            probe = pd.read_sql("SELECT * FROM forces_snapshots LIMIT 1", conn)
            avail = set(probe.columns)

            # Colonne identifiant paire
            pair_col   = "pair"   if "pair"   in avail else ("symbol" if "symbol" in avail else None)
            tf_col     = "timeframe" if "timeframe" in avail else None
            force_cols = [c for c in avail if c.startswith("forces_")]
            base_cols  = [c for c in [
                "bar_time", "open", "high", "low", "close", "tick_volume",
                "direction", "vitesse", "spread_points", "cvd_delta", "cvd_cumul",
                "session", "cs_delta", "atr",
            ] if c in avail]

            select = list(set(base_cols + force_cols
                              + ([pair_col] if pair_col else [])
                              + ([tf_col]   if tf_col   else [])))

            where_parts, params = [], []
            if pair_col:
                where_parts.append(f"{pair_col} = ?")
                params.append(symbol)
            if tf_col:
                where_parts.append(f"{tf_col} = ?")
                params.append(tf)
            where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

            df = pd.read_sql(
                f"SELECT {', '.join(select)} FROM forces_snapshots "
                f"{where} ORDER BY bar_time DESC LIMIT {limit}",
                conn, params=params or None,
            )
            conn.close()
            return df.sort_values("bar_time").reset_index(drop=True)
        except Exception as exc:
            logger.error(f"[_fetch_bars] {symbol}/{tf}: {exc}")
            import pandas as pd
            return pd.DataFrame()

    # ── session ───────────────────────────────────────────────────────────────
    def _get_session(self, bar_time: int) -> str:
        if self.session_filt:
            try: return self.session_filt.get_session(bar_time)
            except Exception: pass
        h = datetime.fromtimestamp(bar_time, tz=timezone.utc).hour
        if   7  <= h < 13: return "london"
        elif 13 <= h < 16: return "london_ny"
        elif 16 <= h < 22: return "new_york"
        elif 0  <= h < 7:  return "asia"
        return "off"

    # ── compose signal (4 niveaux) ────────────────────────────────────────────
    def _compose_signal(
        self,
        row: Any,
        window: Any,
        pair: str,
        tf: str,
        session: str,
        cs_delta: float,
    ) -> Tuple[str, float, str]:
        """Retourne (direction, score, pipeline_used). 4 niveaux de fallback."""

        # ─ Niveau 1 : DecisionPipeline (pipeline live authentique)
        if self.pipeline:
            try:
                res = self.pipeline.process(
                    pair=pair, timeframe=tf,
                    bars=window, session=session,
                    cs_delta=cs_delta,
                )
                d = str(res.get("direction", "HOLD")).upper()
                if d in ("BUY", "SELL", "HOLD"):
                    return d, float(res.get("score", 0.0)), "decision_pipeline"
            except Exception as e:
                logger.debug(f"[DecisionPipeline] {pair}/{tf}: {e}")

        # ─ Niveau 2 : SignalGeneratorLive
        if self.sgl:
            try:
                payload = {
                    "pair": pair, "timeframe": tf, "bars": window,
                    "session": session, "cs_delta": cs_delta,
                    "forces": {
                        c.replace("forces_", ""): float(row.get(c, 0.0))
                        for c in row.index if c.startswith("forces_")
                    },
                }
                res = self.sgl.generate(payload)
                d = str(res.get("direction", "HOLD")).upper()
                if d in ("BUY", "SELL", "HOLD"):
                    return d, float(res.get("score", 0.0)), "signal_generator_live"
            except Exception as e:
                logger.debug(f"[SignalGeneratorLive] {pair}/{tf}: {e}")

        # ─ Niveau 3 : SignalEngine
        if self.signal_engine:
            try:
                forces = {
                    c.replace("forces_", ""): float(row.get(c, 0.0))
                    for c in row.index if c.startswith("forces_")
                }
                res = self.signal_engine.score(
                    pair=pair, tf=tf, forces=forces,
                    session=session, bars=window,
                )
                d = str(res.get("direction", "HOLD")).upper()
                if d in ("BUY", "SELL", "HOLD"):
                    return d, float(res.get("score", 0.0)), "signal_engine"
            except Exception as e:
                logger.debug(f"[SignalEngine] {pair}/{tf}: {e}")

        # ─ Niveau 4 : CS proxy (fallback robuste)
        if   cs_delta > 0: return "BUY",  abs(cs_delta), "cs_proxy"
        elif cs_delta < 0: return "SELL", abs(cs_delta), "cs_proxy"
        return "HOLD", 0.0, "cs_proxy"

    # ── horizon adaptatif ─────────────────────────────────────────────────────
    @staticmethod
    def _adaptive_horizon(window: Any) -> int:
        try:
            r = window["high"] - window["low"]
            if len(r) < 3: return 1
            cur  = float(r.iloc[-1])
            q33  = float(np.percentile(r, 33))
            q67  = float(np.percentile(r, 67))
            if cur <= q33: return 1
            if cur <= q67: return 2
            return 3
        except Exception:
            return 2

    # ── simulation trade ─────────────────────────────────────────────────────
    @staticmethod
    def _simulate_trade(
        bars: Any, idx: int, direction: str, horizon: int, pair: str
    ) -> float:
        entry     = float(bars.iloc[idx]["close"])
        exit_idx  = min(idx + horizon, len(bars) - 1)
        exit_p    = float(bars.iloc[exit_idx]["close"])
        pip_f     = 100.0 if "JPY" in pair else 10_000.0
        raw       = (exit_p - entry) * pip_f * (1 if direction == "BUY" else -1)
        return round(raw - SPREAD_PIPS, 4)

    # ── apprentissage boucle fermée ────────────────────────────────────────────
    def _learn(
        self, trade: TradeResult, session: str, regime: str,
        atr_proxy: float, cs_delta: float,
    ) -> None:
        outcome = "win" if trade.won else "loss"

        if self.learner and TradeOutcome:
            try:
                self.learner.record(TradeOutcome(
                    symbol=trade.pair, setup="v10_fullstack",
                    kill_zone=session, win=trade.won,
                    pnl=trade.pnl_pips, timestamp=trade.bar_time,
                ))
            except Exception as e: logger.debug(f"learner: {e}")

        if self.rl:
            try:
                self.rl.update(
                    arm=trade.direction,
                    reward=trade.pnl_pips / max(atr_proxy * 10_000, 1.0),
                    context={"pair": trade.pair, "tf": trade.tf, "session": session},
                )
            except Exception as e: logger.debug(f"rl: {e}")

        if self.bayes:
            try:
                self.bayes.update(
                    pair=trade.pair, tf=trade.tf,
                    session=session, regime=regime, outcome=outcome,
                )
            except Exception as e: logger.debug(f"bayes: {e}")

        if self.meta_opt:
            try:
                self.meta_opt.record(
                    pair=trade.pair, tf=trade.tf,
                    metrics={"pnl": trade.pnl_pips, "won": int(trade.won),
                             "score": trade.signal_score},
                )
            except Exception as e: logger.debug(f"meta_opt: {e}")

        # LearningContinuum — wrapper robuste (fix crash Zcode)
        if self.lc:
            try:
                # Tenter learn_from_outcome si disponible
                if hasattr(self.lc, "learn_from_outcome"):
                    self.lc.learn_from_outcome(
                        behavior_key=f"{trade.pair}_{trade.tf}_{session}",
                        outcome=outcome,
                        pnl=trade.pnl_pips,
                    )
                elif hasattr(self.lc, "update"):
                    # Proxy via WR de l'ErrorLearner
                    wr_proxy = 0.5
                    if self.learner and hasattr(self.learner, "state"):
                        try: wr_proxy = float(self.learner.state.wr)
                        except Exception: pass
                    self.lc.update(wr=wr_proxy, sharpe=trade.pnl_pips / 10.0)
            except Exception as e: logger.debug(f"lc: {e}")

    # ── replay pair/TF ─────────────────────────────────────────────────────────
    def _replay_pair(self, pair: str, tf: str, limit: int) -> ReplayResult:
        import pandas as pd
        bars = self._fetch_bars(pair, tf, limit)
        if bars.empty or len(bars) < WINDOW_BARS + 2:
            return ReplayResult(
                symbol=pair, timeframe=tf, n_decisions=0, n_wins=0,
                wr=0.0, avg_reward=0.0, curriculum=limit,
                error=f"insufficient_data ({len(bars)} bars < {WINDOW_BARS + 2})",
            )

        # CS delta : utiliser colonne DB si dispo, sinon calculer
        force_cols_avail = [c for c in bars.columns if c.startswith("forces_")]
        base_ccy, quote_ccy = CURRENCY_MAP.get(pair, ("eur", "usd"))
        has_cs_col = "cs_delta" in bars.columns

        drift_tracker = _EWMDriftTracker()
        trades: List[TradeResult] = []
        holds  = 0
        blocked: Dict[str, int] = {}
        pipeline_votes: Dict[str, int] = {}
        total_reward = 0.0

        for idx in range(WINDOW_BARS, len(bars) - 1):
            row    = bars.iloc[idx]
            window = bars.iloc[max(0, idx - WINDOW_BARS): idx + 1].copy()

            # CS delta
            if has_cs_col:
                cs_delta = float(row.get("cs_delta", 0.0) or 0.0)
            else:
                f_base  = float(row.get(f"forces_{base_ccy}",  0.0) or 0.0)
                f_quote = float(row.get(f"forces_{quote_ccy}", 0.0) or 0.0)
                cs_delta = f_base - f_quote

            atr_proxy = float(row.get("high", 0.0)) - float(row.get("low", 0.0))
            session   = self._get_session(int(row.get("bar_time", 0)))
            regime    = str(row.get("regime", "unknown"))

            # Spread guard
            if self.spread_guard:
                try:
                    sp = float(row.get("spread_points", SPREAD_PIPS) or SPREAD_PIPS)
                    if not self.spread_guard.is_acceptable(pair, sp):
                        holds += 1
                        blocked["spread_too_wide"] = blocked.get("spread_too_wide", 0) + 1
                        continue
                except Exception: pass

            direction, score, pipeline_used = self._compose_signal(
                row, window, pair, tf, session, cs_delta
            )
            pipeline_votes[pipeline_used] = pipeline_votes.get(pipeline_used, 0) + 1

            if direction == "HOLD":
                holds += 1
                blocked["signal_hold"] = blocked.get("signal_hold", 0) + 1
                continue

            horizon  = self._adaptive_horizon(window)
            pnl_pips = self._simulate_trade(bars, idx, direction, horizon, pair)
            won      = pnl_pips > 0

            sq       = SESSION_QUALITY.get(session, 0.5)
            reward   = pnl_pips * sq * (1 + abs(cs_delta) * 0.1)
            total_reward += reward
            drift_tracker.update(won)

            trade = TradeResult(
                pair=pair, tf=tf, bar_time=int(row.get("bar_time", 0)),
                direction=direction, horizon=horizon,
                pnl_pips=pnl_pips, won=won,
                signal_score=score, pipeline_used=pipeline_used,
                context_snap={
                    "session":    session, "regime": regime,
                    "cs_delta":   cs_delta, "drift_wr": round(drift_tracker.ewm_wr, 4),
                    "atr_proxy":  atr_proxy,
                },
            )
            trades.append(trade)
            self._learn(trade, session, regime, atr_proxy, cs_delta)

        dominant_pipeline = max(pipeline_votes, key=pipeline_votes.get) if pipeline_votes else "cs_proxy"
        return self._build_result(
            pair, tf, trades, holds, blocked, limit, dominant_pipeline, total_reward
        )

    # ── métriques ───────────────────────────────────────────────────────────────
    @staticmethod
    def _build_result(
        pair: str, tf: str, trades: List[TradeResult],
        holds: int, blocked: Dict, curriculum: int,
        pipeline: str, total_reward: float,
    ) -> ReplayResult:
        n = len(trades)
        if n == 0:
            return ReplayResult(
                symbol=pair, timeframe=tf, n_decisions=0, n_wins=0,
                wr=0.0, avg_reward=0.0, curriculum=curriculum,
                holds=holds, blocked_reasons=blocked,
                pipeline_used=pipeline, error="no_trades",
            )
        wins     = sum(1 for t in trades if t.won)
        pnl_net  = sum(t.pnl_pips for t in trades)
        pos      = sum(t.pnl_pips for t in trades if t.pnl_pips > 0)
        neg      = abs(sum(t.pnl_pips for t in trades if t.pnl_pips < 0))
        pf       = round(pos / neg, 4) if neg > 0 else float("inf")
        pnls     = [t.pnl_pips for t in trades]
        avg_p    = float(np.mean(pnls))
        std_p    = float(np.std(pnls)) or 1.0
        # M30 = 252*48, H1 = 252*24
        bars_yr  = 252 * 48 if tf == "M30" else 252 * 24
        sharpe   = round(avg_p / std_p * float(np.sqrt(bars_yr)), 4)
        equity   = np.cumsum(pnls)
        mdd      = round(float(np.max(np.maximum.accumulate(equity) - equity)), 4)
        sessions = {
            s: sum(1 for t in trades if t.context_snap.get("session") == s)
            for s in ["london", "london_ny", "new_york", "asia", "off"]
        }
        modules = [pipeline]
        return ReplayResult(
            symbol=pair, timeframe=tf,
            n_decisions=n, n_wins=wins,
            wr=round(wins / n, 4),
            avg_reward=round(total_reward / n, 4),
            curriculum=curriculum,
            decisions=[{
                "ts": t.bar_time, "direction": t.direction,
                "win": t.won, "pnl_pips": t.pnl_pips,
                "session": t.context_snap.get("session"),
                "regime":  t.context_snap.get("regime"),
                "score":   t.signal_score,
                "drift_wr": t.context_snap.get("drift_wr"),
                "horizon":  t.horizon,
                "pipeline": t.pipeline_used,
            } for t in trades],
            pnl_net=round(pnl_net, 2),
            profit_factor=pf, sharpe=sharpe, max_drawdown=mdd,
            holds=holds, blocked_reasons=blocked,
            modules_coverage=modules, sessions=sessions,
            pipeline_used=pipeline,
        )

    # ── curriculum ────────────────────────────────────────────────────────────
    def _curriculum(self, key: str, wr: float) -> int:
        cur = self._curriculum_map.get(key, CURRICULUM_BASE)
        if wr > CURRICULUM_WR_THR:
            cur = min(cur + CURRICULUM_STEP, MAX_BARS)
        self._curriculum_map[key] = cur
        return cur

    # ── run() ─────────────────────────────────────────────────────────────────
    def run(
        self,
        return_decisions: bool = False,
        pairs:       Optional[List[str]] = None,
        timeframes:  Optional[List[str]] = None,
        limit:       int = MAX_BARS,
    ) -> Dict:
        """Lance le replay parallèle. Signature compatible ascendante."""
        _pairs = pairs or self.pairs
        _tfs   = timeframes or self.timeframes
        combos = [(p, t) for p in _pairs for t in _tfs]
        logger.info(f"[ReplayEngine.run] {len(combos)} combos, {self.max_workers} workers")

        results: List[ReplayResult] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {
                pool.submit(
                    self._replay_pair, p, t,
                    self._curriculum(f"{p}_{t}", 0.5)
                ): (p, t)
                for p, t in combos
            }
            for fut in as_completed(futures):
                p, t = futures[fut]
                try:
                    res = fut.result(timeout=90)
                    self._curriculum(f"{p}_{t}", res.wr)
                    if not return_decisions:
                        res.decisions = []
                    results.append(res)
                    logger.info(
                        f"  [{p}/{t}] n={res.n_decisions} WR={res.wr:.2%} "
                        f"PnL={res.pnl_net:.1f}p pipeline={res.pipeline_used}"
                    )
                except Exception as exc:
                    logger.error(f"[{p}/{t}] {exc}")
                    results.append(ReplayResult(
                        symbol=p, timeframe=t, n_decisions=0, n_wins=0,
                        wr=0.0, avg_reward=0.0, curriculum=CURRICULUM_BASE,
                        error=str(exc),
                    ))

        # Persistance
        if self.persistence:
            try: self.persistence.save_all()
            except Exception as e: logger.warning(f"persistence: {e}")

        valid   = [r for r in results if not r.error]
        total_n = sum(r.n_decisions for r in valid)
        total_w = sum(r.n_wins for r in valid)
        total_p = sum(r.pnl_net for r in valid)
        global_wr = total_w / max(1, total_n)

        # Pipelines utilisés
        pipeline_stats: Dict[str, int] = {}
        for r in valid:
            k = r.pipeline_used
            pipeline_stats[k] = pipeline_stats.get(k, 0) + r.n_decisions

        summary = {
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "pairs_tested":   len(valid),
            "total_decisions":total_n,
            "global_wr":      round(global_wr, 4),
            "global_pnl_net": round(total_p, 2),
            "avg_sharpe":     round(float(np.mean([r.sharpe for r in valid])) if valid else 0.0, 4),
            "pipeline_stats": pipeline_stats,
            "n_errors":       len(results) - len(valid),
            "verdict": (
                "RENTABLE ✅"
                if total_p > 0 and global_wr > 0.55
                else "NON_RENTABLE ❌ — calibration requise"
            ),
            "status": "FULLSTACK_V10_v2",
        }
        if valid:
            best  = max(valid, key=lambda r: r.pnl_net)
            worst = min(valid, key=lambda r: r.pnl_net)
            summary["best_combo"]  = f"{best.symbol}/{best.timeframe} WR={best.wr:.2%} PnL={best.pnl_net:.1f}p"
            summary["worst_combo"] = f"{worst.symbol}/{worst.timeframe} WR={worst.wr:.2%} PnL={worst.pnl_net:.1f}p"

        learner_state = {}
        if self.learner:
            try: learner_state = self.learner.state.as_dict()
            except Exception: pass

        return {
            "timestamp":         summary["timestamp"],
            "n_tasks":           len(combos),
            "n_valid":           len(valid),
            "n_errors":          summary["n_errors"],
            "global_wr":         summary["global_wr"],
            "global_avg_reward": round(
                sum(r.avg_reward * r.n_decisions for r in valid) / max(1, total_n), 4
            ),
            "total_decisions":   total_n,
            "learner":           learner_state,
            "results":           [r.as_dict() for r in sorted(
                valid, key=lambda r: r.wr * r.n_decisions, reverse=True
            )[:20]],
            "summary":           summary,
        }

    # ── run_all() ─────────────────────────────────────────────────────────────
    def run_all(
        self,
        pairs:      Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        workers:    int = MAX_WORKERS,
        limit:      int = MAX_BARS,
    ) -> Dict:
        """Alias run() + sauvegarde JSON automatique."""
        self.max_workers = workers
        report = self.run(
            return_decisions=True,
            pairs=pairs, timeframes=timeframes, limit=limit,
        )
        ts  = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = REPORTS_DIR / f"replay_fullstack_v2_{ts}.json"
        try:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"[ReplayEngine] Rapport → {out}")
            report["report_path"] = str(out)
        except Exception as e:
            logger.warning(f"[ReplayEngine] JSON write: {e}")
        return report
