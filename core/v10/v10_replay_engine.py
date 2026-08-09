"""V10 Replay Engine — S25-OMEGA Full-Stack.

Simule fidèlement le pipeline V10 COMPLET sur données historiques.
Chaque barre est traitée exactement comme en live :

  forces_snapshots
    └─► ForceNative (F1-F5)
        ├─► StructureAnalyzer (S1-S9)
        ├─► ContextAnalyzer (C1-C7)
        ├─► VSAAnalyzer + WyckoffAnalyzer
        ├─► FractalContext (M1/M5/M30/H1/H4)
        ├─► MarketContextGlobal (Cycle/Coalition/Antagonisme)
        ├─► RegimeHMM
        ├─► SMCAnalyzer (BOS/MSS/OB/FVG)
        ├─► ICTOTEAnalyzer
        ├─► BayesianRecalibrator (prior 3D/4D)
        ├─► SessionFilter + SpreadGuard
        └─► Orchestrator.compose_signal() → A1/A2/A3
                 │
             RiskShield + NetExposure
                 │
             _simulate_trade() (pip-factor JPY-aware)
                 │
             ErrorLearner + RLAdapter + BayesUpdate
             + MetaOptimizer + LearningContinuum
                 │
             LearningPersistence.save_all()
                 └─► reports/replay_fullstack_<ts>.json

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit, R10 zéro ordre.
Tout module manquant → fallback CS proxy, aucune exception fatale.
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

# ── imports V10 complets (fail-open R6) ──────────────────────────────────────
try:
    from .v10_orchestrator import Orchestrator
    _HAS_ORCHESTRATOR = True
except ImportError:
    _HAS_ORCHESTRATOR = False

try:
    from .v10_structure import StructureAnalyzer
    _HAS_STRUCTURE = True
except ImportError:
    _HAS_STRUCTURE = False

try:
    from .v10_context import ContextAnalyzer
    _HAS_CONTEXT = True
except ImportError:
    _HAS_CONTEXT = False

try:
    from .v10_vsa import VSAAnalyzer
    _HAS_VSA = True
except ImportError:
    _HAS_VSA = False

try:
    from .v10_wyckoff_consolidated import WyckoffAnalyzer
    _HAS_WYCKOFF = True
except ImportError:
    _HAS_WYCKOFF = False

try:
    from .v10_fractal_context import FractalContext
    _HAS_FRACTAL = True
except ImportError:
    _HAS_FRACTAL = False

try:
    from .v10_market_context_global import MarketContextGlobal
    _HAS_MCG = True
except ImportError:
    _HAS_MCG = False

try:
    from .v10_regime_hmm import RegimeHMM
    _HAS_HMM = True
except ImportError:
    _HAS_HMM = False

try:
    from .v10_smc import SMCAnalyzer
    _HAS_SMC = True
except ImportError:
    _HAS_SMC = False

try:
    from .v10_ict_ote import ICTOTEAnalyzer
    _HAS_ICT = True
except ImportError:
    _HAS_ICT = False

try:
    from .v10_bayesian_recalibrator import BayesianRecalibrator
    _HAS_BAYES = True
except ImportError:
    _HAS_BAYES = False

try:
    from .v10_rl_adapter import RLAdapter
    _HAS_RL = True
except ImportError:
    _HAS_RL = False

try:
    from .v10_risk_shield import RiskShield
    _HAS_RISK = True
except ImportError:
    _HAS_RISK = False

try:
    from .v10_net_exposure import NetExposure
    _HAS_NET = True
except ImportError:
    _HAS_NET = False

try:
    from .v10_error_learner import ErrorLearner, TradeOutcome
    _HAS_EL = True
except ImportError:
    _HAS_EL = False
    ErrorLearner = None  # type: ignore
    TradeOutcome = None  # type: ignore

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
    from .v10_force_native import ForceNativeCalculator
    _HAS_FN = True
except ImportError:
    _HAS_FN = False

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

# ── Constantes ────────────────────────────────────────────────────────────────
DEFAULT_PAIRS: List[str] = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "USDCHF", "NZDUSD", "USDCAD", "EURJPY",
]
DEFAULT_TIMEFRAMES: List[str] = ["M30", "H1"]
MAX_WORKERS:   int   = 4
MAX_BARS:      int   = 2000
WINDOW_BARS:   int   = 50       # fenêtre glissante analyses structurelles
SPREAD_PIPS:   float = 2.0      # coût spread + commission
CURRICULUM_BASE: int = 150
CURRICULUM_STEP: int = 50
CURRICULUM_WR_THR: float = 0.52
ATR_Q33: float = 0.33
ATR_Q67: float = 0.67
REPORTS_DIR: Path = Path("reports")

SESSION_QUALITY: Dict[str, float] = {
    "london":     1.0,
    "new_york":   1.0,
    "london_ny":  1.2,
    "asia":       0.6,
    "pre_london": 0.7,
    "off":        0.4,
}

# Map paire → (base_ccy, quote_ccy) pour CS delta et pip factor
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
class BarContext:
    """Contexte enrichi V10 complet d'une barre pour décision."""
    pair:        str
    tf:          str
    bar_time:    int
    open:        float
    high:        float
    low:         float
    close:       float
    tick_volume: float
    forces:      Dict[str, float] = field(default_factory=dict)
    cs_delta:    float = 0.0
    atr_proxy:   float = 0.0
    session:     str   = "off"
    spread_ok:   bool  = True
    structure:   Dict  = field(default_factory=dict)
    context:     Dict  = field(default_factory=dict)
    vsa:         Dict  = field(default_factory=dict)
    wyckoff:     Dict  = field(default_factory=dict)
    fractal:     Dict  = field(default_factory=dict)
    mcg:         Dict  = field(default_factory=dict)
    regime:      str   = "unknown"
    smc:         Dict  = field(default_factory=dict)
    ict:         Dict  = field(default_factory=dict)
    bayes_prior: float = 0.5


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
    modules_used: List[str] = field(default_factory=list)
    context_snap: Dict      = field(default_factory=dict)


@dataclass
class ReplayResult:
    """Résultat agrégé d'un replay pair/TF — compatible avec l'ancien as_dict()."""
    symbol:      str
    timeframe:   str
    n_decisions: int
    n_wins:      int
    wr:          float
    avg_reward:  float
    curriculum:  int
    decisions:   List[Dict] = field(default_factory=list)
    error:       Optional[str] = None
    # champs Full-Stack additionnels
    pnl_net:          float = 0.0
    profit_factor:    float = 0.0
    sharpe:           float = 0.0
    max_drawdown:     float = 0.0
    holds:            int   = 0
    blocked_reasons:  Dict  = field(default_factory=dict)
    modules_coverage: List[str] = field(default_factory=list)
    sessions:         Dict  = field(default_factory=dict)

    def as_dict(self) -> Dict:
        base = {
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
            "status":           "FULLSTACK_V10",
        }
        if self.error:
            base["error"] = self.error
        return base


# ── EWM Drift Tracker O(1) ────────────────────────────────────────────────────
class _EWMDriftTracker:
    """Drift WR via EWM sans fenêtre glissante — O(1) mémoire."""

    def __init__(self, alpha: float = 0.05) -> None:
        self.alpha   = alpha
        self.ewm_wr  = 0.5
        self.n       = 0

    def update(self, win: bool) -> bool:
        self.n      += 1
        self.ewm_wr  = self.alpha * int(win) + (1 - self.alpha) * self.ewm_wr
        return self.n >= 20 and self.ewm_wr < 0.44


# ── Replay Engine ─────────────────────────────────────────────────────────────
class ReplayEngine:
    """
    Replay Engine V10 Full-Stack.

    Usage minimal :
        engine = ReplayEngine(db_path="data/powerflow.db")
        report = engine.run()          # 8 paires × 2 TF, 4 workers
        report = engine.run_all()      # alias run() avec rapport JSON auto

    Compatibilité ascendante : signatures identiques à la version S25-OMEGA.
    """

    def __init__(
        self,
        db_path:     str             = "data/powerflow.db",
        pairs:       Optional[List[str]] = None,
        timeframes:  Optional[List[str]] = None,
        max_workers: int             = MAX_WORKERS,
    ) -> None:
        self.db_path    = db_path
        self.pairs      = pairs      or DEFAULT_PAIRS
        self.timeframes = timeframes or DEFAULT_TIMEFRAMES
        self.max_workers = max_workers
        self._curriculum_map: Dict[str, int] = {}
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self._init_modules()

    # ── init modules ─────────────────────────────────────────────────────────
    def _init_modules(self) -> None:
        self.orchestrator  = Orchestrator()          if _HAS_ORCHESTRATOR else None
        self.structure     = StructureAnalyzer()     if _HAS_STRUCTURE    else None
        self.context_mod   = ContextAnalyzer()       if _HAS_CONTEXT      else None
        self.vsa           = VSAAnalyzer()           if _HAS_VSA          else None
        self.wyckoff       = WyckoffAnalyzer()       if _HAS_WYCKOFF      else None
        self.fractal       = FractalContext()        if _HAS_FRACTAL      else None
        self.mcg           = MarketContextGlobal()   if _HAS_MCG          else None
        self.hmm           = RegimeHMM()             if _HAS_HMM          else None
        self.smc           = SMCAnalyzer()           if _HAS_SMC          else None
        self.ict           = ICTOTEAnalyzer()        if _HAS_ICT          else None
        self.bayes         = BayesianRecalibrator()  if _HAS_BAYES        else None
        self.rl            = RLAdapter()             if _HAS_RL           else None
        self.risk_shield   = RiskShield()            if _HAS_RISK         else None
        self.net_exposure  = NetExposure()           if _HAS_NET          else None
        self.learner       = ErrorLearner()          if _HAS_EL           else None
        self.meta_opt      = MetaOptimizer()         if _HAS_MO           else None
        self.lc            = LearningContinuum()     if _HAS_LC           else None
        self.persistence   = LearningPersistence()   if _HAS_LP           else None
        self.force_native  = ForceNativeCalculator() if _HAS_FN           else None
        self.session_filt  = SessionFilter()         if _HAS_SF           else None
        self.spread_guard  = SpreadGuard()           if _HAS_SG           else None

        active = [k for k, v in {
            "Orchestrator": self.orchestrator, "Structure": self.structure,
            "Context": self.context_mod, "VSA": self.vsa,
            "Wyckoff": self.wyckoff, "Fractal": self.fractal,
            "MCG": self.mcg, "RegimeHMM": self.hmm,
            "SMC": self.smc, "ICT/OTE": self.ict,
            "Bayesian": self.bayes, "RLAdapter": self.rl,
            "RiskShield": self.risk_shield, "NetExposure": self.net_exposure,
            "ErrorLearner": self.learner, "MetaOptimizer": self.meta_opt,
            "LearningContinuum": self.lc, "ForceNative": self.force_native,
            "SessionFilter": self.session_filt, "SpreadGuard": self.spread_guard,
        }.items() if v is not None]
        logger.info(f"[ReplayEngine] Modules actifs ({len(active)}/20): {active}")

    # ── lecture DB ────────────────────────────────────────────────────────────
    def _fetch_bars(
        self, symbol: str, tf: str, limit: int = MAX_BARS
    ) -> Any:  # returns pd.DataFrame
        """Charge toutes les colonnes disponibles de forces_snapshots."""
        import pandas as pd
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5)
            probe = pd.read_sql("SELECT * FROM forces_snapshots LIMIT 1", conn)
            avail = set(probe.columns)

            force_cols = [c for c in avail if c.startswith("forces_")]
            base_cols  = [c for c in [
                "bar_time", "open", "high", "low", "close", "tick_volume",
                "pair", "timeframe", "direction", "vitesse",
                "spread_points", "cvd_delta", "cvd_cumul",
            ] if c in avail]
            select = list(set(base_cols + force_cols))

            where_parts, params = [], []
            if "pair" in avail:
                where_parts.append("pair = ?")
                params.append(symbol)
            if "timeframe" in avail:
                where_parts.append("timeframe = ?")
                params.append(tf)
            where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

            df = pd.read_sql(
                f"SELECT {', '.join(select)} FROM forces_snapshots "
                f"{where} ORDER BY bar_time DESC LIMIT {limit}",
                conn, params=params,
            )
            conn.close()
            return df.sort_values("bar_time").reset_index(drop=True)
        except Exception as exc:
            logger.error(f"[ReplayEngine._fetch_bars] {symbol}/{tf}: {exc}")
            import pandas as pd
            return pd.DataFrame()

    # ── session ───────────────────────────────────────────────────────────────
    def _get_session(self, bar_time: int) -> str:
        if self.session_filt:
            try:
                return self.session_filt.get_session(bar_time)
            except Exception:
                pass
        dt = datetime.fromtimestamp(bar_time, tz=timezone.utc)
        h  = dt.hour
        if   7 <= h < 13:  return "london"
        elif 13 <= h < 16: return "london_ny"
        elif 16 <= h < 22: return "new_york"
        elif 0  <= h < 7:  return "asia"
        return "off"

    # ── enrichissement barre ──────────────────────────────────────────────────
    def _enrich_bar(
        self, row: Any, window: Any, pair: str, tf: str
    ) -> BarContext:
        """Construit un BarContext enrichi via tous les modules V10."""
        forces = {
            c.replace("forces_", ""): float(row.get(c, 0.0))
            for c in row.index if c.startswith("forces_")
        }
        base_ccy, quote_ccy = CURRENCY_MAP.get(pair, ("eur", "usd"))
        cs_delta   = forces.get(base_ccy, 0.0) - forces.get(quote_ccy, 0.0)
        atr_proxy  = float(row.get("high", 0.0)) - float(row.get("low", 0.0))
        session    = self._get_session(int(row.get("bar_time", 0)))
        spread_ok  = True

        if self.spread_guard:
            try:
                sp = float(row.get("spread_points", SPREAD_PIPS))
                spread_ok = self.spread_guard.is_acceptable(pair, sp)
            except Exception:
                pass

        bc = BarContext(
            pair=pair, tf=tf,
            bar_time=int(row.get("bar_time", 0)),
            open=float(row.get("open", 0.0)),
            high=float(row.get("high", 0.0)),
            low=float(row.get("low", 0.0)),
            close=float(row.get("close", 0.0)),
            tick_volume=float(row.get("tick_volume", 0.0)),
            forces=forces, cs_delta=cs_delta,
            atr_proxy=atr_proxy, session=session, spread_ok=spread_ok,
        )

        if self.structure:
            try: bc.structure = self.structure.analyze(window) or {}
            except Exception as e: logger.debug(f"structure: {e}")

        if self.context_mod:
            try: bc.context = self.context_mod.analyze(window, pair=pair) or {}
            except Exception as e: logger.debug(f"context: {e}")

        if self.vsa:
            try: bc.vsa = self.vsa.analyze(window) or {}
            except Exception as e: logger.debug(f"vsa: {e}")

        if self.wyckoff:
            try: bc.wyckoff = self.wyckoff.analyze(window) or {}
            except Exception as e: logger.debug(f"wyckoff: {e}")

        if self.fractal:
            try: bc.fractal = self.fractal.analyze(window, pair=pair, tf=tf) or {}
            except Exception as e: logger.debug(f"fractal: {e}")

        if self.mcg:
            try: bc.mcg = self.mcg.compute(window, pair=pair) or {}
            except Exception as e: logger.debug(f"mcg: {e}")

        if self.hmm:
            try:
                r = self.hmm.predict(window)
                bc.regime = str(r) if r else "unknown"
            except Exception as e: logger.debug(f"hmm: {e}")

        if self.smc:
            try: bc.smc = self.smc.analyze(window, pair=pair) or {}
            except Exception as e: logger.debug(f"smc: {e}")

        if self.ict:
            try: bc.ict = self.ict.analyze(window, pair=pair) or {}
            except Exception as e: logger.debug(f"ict: {e}")

        if self.bayes:
            try:
                bc.bayes_prior = float(
                    self.bayes.get_prior(
                        pair=pair, tf=tf, session=session, regime=bc.regime
                    )
                )
            except Exception as e: logger.debug(f"bayes: {e}")

        return bc

    # ── signal ────────────────────────────────────────────────────────────────
    def _compose_signal(
        self, bc: BarContext, window: Any
    ) -> Tuple[str, float, List[str]]:
        """Orchestrator.compose_signal() ou fallback CS proxy (R6)."""
        if self.orchestrator:
            try:
                payload = {
                    "pair": bc.pair, "tf": bc.tf, "bar_time": bc.bar_time,
                    "forces": bc.forces, "cs_delta": bc.cs_delta,
                    "atr": bc.atr_proxy, "session": bc.session,
                    "structure": bc.structure, "context": bc.context,
                    "vsa": bc.vsa, "wyckoff": bc.wyckoff,
                    "fractal": bc.fractal, "mcg": bc.mcg,
                    "regime": bc.regime, "smc": bc.smc, "ict": bc.ict,
                    "bayes_prior": bc.bayes_prior, "bars": window,
                    "spread_ok": bc.spread_ok,
                }
                res = self.orchestrator.compose_signal(payload)
                d   = str(res.get("direction", "HOLD")).upper()
                if d not in ("BUY", "SELL", "HOLD"):
                    d = "HOLD"
                return d, float(res.get("score", 0.0)), list(res.get("modules", []))
            except Exception as e:
                logger.debug(f"orchestrator: {e}")

        # fallback CS proxy
        if bc.cs_delta > 0:   return "BUY",  abs(bc.cs_delta), ["cs_proxy"]
        if bc.cs_delta < 0:   return "SELL", abs(bc.cs_delta), ["cs_proxy"]
        return "HOLD", 0.0, ["cs_proxy"]

    # ── filtre risque ─────────────────────────────────────────────────────────
    def _risk_filter(
        self, bc: BarContext, direction: str, score: float
    ) -> Tuple[str, str]:
        if direction == "HOLD":  return "HOLD", "signal_hold"
        if not bc.spread_ok:     return "HOLD", "spread_too_wide"
        if self.risk_shield:
            try:
                if not self.risk_shield.check(
                    pair=bc.pair, direction=direction,
                    score=score, session=bc.session
                ):
                    return "HOLD", "risk_shield"
            except Exception as e: logger.debug(f"risk_shield: {e}")
        if self.net_exposure:
            try:
                if not self.net_exposure.can_open(bc.pair, direction):
                    return "HOLD", "net_exposure"
            except Exception as e: logger.debug(f"net_exposure: {e}")
        return direction, "ok"

    # ── horizon adaptatif ─────────────────────────────────────────────────────
    @staticmethod
    def _adaptive_horizon(window: Any) -> int:
        try:
            ranges = window["high"] - window["low"]
            if len(ranges) < 3: return 1
            cur = float(ranges.iloc[-1])
            q33, q67 = float(np.percentile(ranges, 33)), float(np.percentile(ranges, 67))
            if cur <= q33: return 1
            if cur <= q67: return 2
            return 3
        except Exception:
            return 2

    # ── simulation trade ──────────────────────────────────────────────────────
    def _simulate_trade(
        self, bars: Any, idx: int, direction: str, horizon: int, pair: str
    ) -> float:
        entry = float(bars.iloc[idx]["close"])
        exit_idx = min(idx + horizon, len(bars) - 1)
        exit_price = float(bars.iloc[exit_idx]["close"])
        pip_factor = 100.0 if "JPY" in pair else 10_000.0
        raw = (exit_price - entry) * pip_factor
        if direction == "SELL": raw = -raw
        return round(raw - SPREAD_PIPS, 4)

    # ── apprentissage ─────────────────────────────────────────────────────────
    def _learn(self, trade: TradeResult, bc: BarContext) -> None:
        outcome = "win" if trade.won else "loss"

        if self.learner and TradeOutcome:
            try:
                self.learner.record(TradeOutcome(
                    symbol=bc.pair, setup="v10_fullstack",
                    kill_zone=bc.session, win=trade.won,
                    pnl=trade.pnl_pips,
                    timestamp=bc.bar_time,
                ))
            except Exception as e: logger.debug(f"learner: {e}")

        if self.rl:
            try:
                atr_norm = max(bc.atr_proxy * 10_000, 1.0)
                self.rl.update(
                    arm=trade.direction,
                    reward=trade.pnl_pips / atr_norm,
                    context={"pair": bc.pair, "tf": bc.tf, "session": bc.session},
                )
            except Exception as e: logger.debug(f"rl: {e}")

        if self.bayes:
            try:
                self.bayes.update(
                    pair=bc.pair, tf=bc.tf,
                    session=bc.session, regime=bc.regime, outcome=outcome,
                )
            except Exception as e: logger.debug(f"bayes_update: {e}")

        if self.meta_opt:
            try:
                self.meta_opt.record(
                    pair=bc.pair, tf=bc.tf,
                    metrics={"pnl": trade.pnl_pips, "won": int(trade.won),
                             "score": trade.signal_score},
                )
            except Exception as e: logger.debug(f"meta_opt: {e}")

        if self.lc:
            try:
                self.lc.learn_from_outcome(
                    behavior_key=f"{bc.pair}_{bc.tf}_{bc.session}",
                    outcome=outcome, pnl=trade.pnl_pips,
                )
            except Exception as e: logger.debug(f"lc: {e}")

    # ── curriculum ────────────────────────────────────────────────────────────
    def _curriculum(self, key: str, wr: float) -> int:
        cur = self._curriculum_map.get(key, CURRICULUM_BASE)
        if wr > CURRICULUM_WR_THR:
            cur = min(cur + CURRICULUM_STEP, MAX_BARS)
        self._curriculum_map[key] = cur
        return cur

    # ── replay pair/TF ────────────────────────────────────────────────────────
    def _replay_pair(
        self, pair: str, tf: str, limit: int
    ) -> ReplayResult:
        import pandas as pd
        bars = self._fetch_bars(pair, tf, limit)
        if bars.empty or len(bars) < WINDOW_BARS + 2:
            return ReplayResult(
                symbol=pair, timeframe=tf, n_decisions=0, n_wins=0,
                wr=0.0, avg_reward=0.0, curriculum=limit,
                error="insufficient_data",
            )

        drift_tracker  = _EWMDriftTracker()
        trades: List[TradeResult] = []
        holds   = 0
        blocked: Dict[str, int] = {}
        all_mods: set = set()
        total_reward = 0.0

        for idx in range(WINDOW_BARS, len(bars) - 1):
            row    = bars.iloc[idx]
            window = bars.iloc[max(0, idx - WINDOW_BARS): idx + 1].copy()

            bc                    = self._enrich_bar(row, window, pair, tf)
            raw_dir, score, mods  = self._compose_signal(bc, window)
            direction, reason     = self._risk_filter(bc, raw_dir, score)
            all_mods.update(mods)

            if direction == "HOLD":
                holds += 1
                blocked[reason] = blocked.get(reason, 0) + 1
                continue

            horizon  = self._adaptive_horizon(window)
            pnl_pips = self._simulate_trade(bars, idx, direction, horizon, pair)
            won      = pnl_pips > 0

            sq       = SESSION_QUALITY.get(bc.session, 0.5)
            reward   = pnl_pips * sq * (1 + abs(bc.cs_delta) * 0.1)
            total_reward += reward

            drift_tracker.update(won)

            trade = TradeResult(
                pair=pair, tf=tf, bar_time=bc.bar_time,
                direction=direction, horizon=horizon,
                pnl_pips=pnl_pips, won=won,
                signal_score=score, modules_used=mods,
                context_snap={
                    "session":     bc.session,
                    "regime":      bc.regime,
                    "cs_delta":    bc.cs_delta,
                    "bayes_prior": bc.bayes_prior,
                    "spread_ok":   bc.spread_ok,
                    "drift_wr":    round(drift_tracker.ewm_wr, 4),
                },
            )
            trades.append(trade)
            self._learn(trade, bc)

        return self._build_result(
            pair, tf, trades, holds, blocked, limit,
            sorted(list(all_mods)), total_reward
        )

    # ── métriques ─────────────────────────────────────────────────────────────
    @staticmethod
    def _build_result(
        pair: str, tf: str, trades: List[TradeResult],
        holds: int, blocked: Dict, curriculum: int,
        modules: List[str], total_reward: float,
    ) -> ReplayResult:
        n = len(trades)
        if n == 0:
            return ReplayResult(
                symbol=pair, timeframe=tf, n_decisions=0, n_wins=0,
                wr=0.0, avg_reward=0.0, curriculum=curriculum,
                holds=holds, blocked_reasons=blocked, error="no_trades",
            )
        wins    = sum(1 for t in trades if t.won)
        pnl_net = sum(t.pnl_pips for t in trades)
        pos     = sum(t.pnl_pips for t in trades if t.pnl_pips > 0)
        neg     = abs(sum(t.pnl_pips for t in trades if t.pnl_pips < 0))
        pf      = round(pos / neg, 4) if neg > 0 else float("inf")
        pnls    = [t.pnl_pips for t in trades]
        avg     = float(np.mean(pnls))
        std     = float(np.std(pnls)) or 1.0
        # annualisé M30 = 252 jours × 48 barres/jour
        sharpe  = round(avg / std * float(np.sqrt(252 * 48)), 4)
        equity  = np.cumsum(pnls)
        mdd     = round(float(np.max(np.maximum.accumulate(equity) - equity)), 4)
        sessions = {
            s: sum(1 for t in trades if t.context_snap.get("session") == s)
            for s in ["london", "london_ny", "new_york", "asia", "off"]
        }
        return ReplayResult(
            symbol=pair, timeframe=tf,
            n_decisions=n, n_wins=wins,
            wr=round(wins / n, 4),
            avg_reward=round(total_reward / n, 4),
            curriculum=curriculum,
            decisions=[{
                "ts":        t.bar_time, "direction": t.direction,
                "win":       t.won,     "pnl_pips":  t.pnl_pips,
                "session":   t.context_snap.get("session"),
                "regime":    t.context_snap.get("regime"),
                "score":     t.signal_score,
                "drift_wr":  t.context_snap.get("drift_wr"),
                "horizon":   t.horizon,
            } for t in trades],
            pnl_net=round(pnl_net, 2),
            profit_factor=pf, sharpe=sharpe, max_drawdown=mdd,
            holds=holds, blocked_reasons=blocked,
            modules_coverage=modules, sessions=sessions,
        )

    # ── run (alias historique) ────────────────────────────────────────────────
    def run(
        self,
        return_decisions: bool = False,
        pairs:       Optional[List[str]] = None,
        timeframes:  Optional[List[str]] = None,
        limit:       int = MAX_BARS,
    ) -> Dict:
        """Lance le replay parallèle. Compatible avec l'ancienne signature."""
        _pairs = pairs or self.pairs
        _tfs   = timeframes or self.timeframes
        combos = [(p, t) for p in _pairs for t in _tfs]
        logger.info(f"[ReplayEngine.run] {len(combos)} combos — {self.max_workers} workers")

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
                    res = fut.result(timeout=60)
                    self._curriculum(f"{p}_{t}", res.wr)
                    if not return_decisions:
                        res.decisions = []
                    results.append(res)
                    logger.info(
                        f"[{p}/{t}] decisions={res.n_decisions} "
                        f"WR={res.wr:.2%} PnL={res.pnl_net:.1f} pips"
                    )
                except Exception as exc:
                    logger.error(f"[{p}/{t}] {exc}")
                    results.append(ReplayResult(
                        symbol=p, timeframe=t, n_decisions=0, n_wins=0,
                        wr=0.0, avg_reward=0.0, curriculum=CURRICULUM_BASE,
                        error=str(exc),
                    ))

        if self.persistence:
            try:
                self.persistence.save_all()
                logger.info("[ReplayEngine] LearningPersistence saved ✅")
            except Exception as e:
                logger.warning(f"[ReplayEngine] persistence: {e}")

        valid = [r for r in results if not r.error]
        total_n = sum(r.n_decisions for r in valid)
        total_w = sum(r.n_wins for r in valid)
        total_pnl = sum(r.pnl_net for r in valid)

        all_mods: set = set()
        for r in valid:
            all_mods.update(r.modules_coverage)

        summary = {
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "pairs_tested":     len(valid),
            "total_decisions":  total_n,
            "global_wr":        round(total_w / max(1, total_n), 4),
            "global_pnl_net":   round(total_pnl, 2),
            "avg_sharpe":       round(float(np.mean([r.sharpe for r in valid])) if valid else 0.0, 4),
            "modules_active":   sorted(list(all_mods)),
            "n_errors":         len(results) - len(valid),
            "verdict": (
                "RENTABLE ✅"
                if total_pnl > 0 and total_w / max(1, total_n) > 0.55
                else "NON_RENTABLE ❌ — calibration requise"
            ),
            "status": "FULLSTACK_V10",
        }
        if valid:
            best  = max(valid, key=lambda r: r.pnl_net)
            worst = min(valid, key=lambda r: r.pnl_net)
            summary["best_combo"]  = f"{best.symbol}/{best.timeframe} PnL={best.pnl_net:.1f}"
            summary["worst_combo"] = f"{worst.symbol}/{worst.timeframe} PnL={worst.pnl_net:.1f}"

        learner_state = {}
        if self.learner:
            try: learner_state = self.learner.state.as_dict()
            except Exception: pass

        return {
            "timestamp":  summary["timestamp"],
            "n_tasks":    len(combos),
            "n_valid":    len(valid),
            "n_errors":   summary["n_errors"],
            "global_wr":  summary["global_wr"],
            "global_avg_reward": round(
                sum(r.avg_reward * r.n_decisions for r in valid)
                / max(1, total_n), 4
            ),
            "total_decisions": total_n,
            "learner":    learner_state,
            "results":    [r.as_dict() for r in sorted(
                valid, key=lambda r: r.wr * r.n_decisions, reverse=True
            )[:20]],
            "summary":    summary,
        }

    # ── run_all (alias + rapport JSON) ────────────────────────────────────────
    def run_all(
        self,
        pairs:      Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        workers:    int = MAX_WORKERS,
        limit:      int = MAX_BARS,
    ) -> Dict:
        """run_all() : alias run() avec sauvegarde JSON automatique."""
        self.max_workers = workers
        report = self.run(
            return_decisions=True,
            pairs=pairs, timeframes=timeframes, limit=limit,
        )
        ts  = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = REPORTS_DIR / f"replay_fullstack_{ts}.json"
        try:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"[ReplayEngine] Rapport → {out}")
            report["report_path"] = str(out)
        except Exception as e:
            logger.warning(f"[ReplayEngine] JSON write: {e}")
        return report
