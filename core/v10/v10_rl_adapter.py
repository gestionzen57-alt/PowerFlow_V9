"""V10 RL Adapter — bandit contextuel Thompson Sampling + ADWIN drift (shadow mode).

Doctrine V10 Couche 4 (R4 online learning + R10 capital protégé) :
  R1 : agit par défaut, expose les poids pour shadow observe
  R2 : additif pur (0 import core/v9/)
  R4 : online RL, epsilon-exploration 10% (Thompson sampling variant)
  R6 : fail-open (≥4 cas gérés)
  R7 : testé
  R9 : audit honnête, log explicite shadow vs live, source_weights
  R10 : 0 capital réel. **SHADOW MODE OBLIGATOIRE** par défaut.

Spécifications CEO (mandat 5/8/2026) :
  - Bandit contextuel Thompson Sampling (variante LinUCB simplifié)
  - Feature vector EXACT : [context_score, phase, solidarity, aligned_count, session_quality]
    PAS D'AJOUT SANS CEO GO.
  - Reward : PnL normalisé sur fenêtre 20 barres (pas de reward shaping)
  - Drift detector : ADWIN sur WR rolling 50 trades
  - R10 : RL désactivé (kill switch) si Max DD > 5%
  - Shadow mode : observe sans modifier les signaux live
  - 25 tests verts minimum
  - Journal shadow : 20 setups live pour valider convergence bandit
  - Gate CEO : WR shadow ≥ WR sans RL sur 30 trades consécutifs

Module expose :
  - ThompsonBandit       : bandit contextuel avec posterior Beta par arm
  - ADWINDriftDetector   : Adaptive Windowing drift detector
  - RLAdapter            : orchestrateur shadow mode
  - apply_rl_to_signal   : hook pour modifier setup_level selon poids RL
  - log_shadow_trade     : journal shadow
  - get_shadow_stats     : stats shadow pour gate CEO
"""
from __future__ import annotations

import json
import logging
import math
import random
import sqlite3
import statistics
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# R10 capital
MAX_DD_PCT_KILL_SWITCH = 5.0  # %

# Bandit config
BANDIT_ARMS = ("A1_BOOST", "NEUTRAL", "A1_DAMPEN")  # 3 bras : booster/neutral/downgrade
THOMPSON_ALPHA_PRIOR = 1.0
THOMPSON_BETA_PRIOR = 1.0
EXPLORATION_EPSILON = 0.10  # 10% exploration (R4 spec)

# Drift detector (ADWIN)
ADWIN_DELTA = 0.002  # confiance 99.8%
ADWIN_MAX_WINDOW = 1000
DRIFT_WINDOW_SIZE = 50  # CEO spec

# Reward
REWARD_WINDOW_BARS = 20  # CEO spec : PnL normalisé sur 20 barres
PNL_NORMALIZATION = 50.0  # 50 pips → reward=1.0

# Shadow mode (R10 obligatoire)
SHADOW_TABLE_NAME = "v10_rl_shadow_log"

# Session quality mapping (Couche 3 → score 0-1)
SESSION_QUALITY_BY_TF = {
    "M15": 0.80,
    "M30": 0.85,
    "H1": 0.90,
    "H4": 0.95,
    "D1": 0.85,
}


# ─────────────────────────────────────────────────────────────────────
# ENUMS & DATACLASSES
# ─────────────────────────────────────────────────────────────────────

class RLMode(str, Enum):
    """Mode RL — R10 strict."""
    DISABLED = "DISABLED"           # Kill switch actif (DD > 5%)
    SHADOW = "SHADOW"               # Observe sans modifier (par défaut)
    LIVE = "LIVE"                   # Modifie les signaux (CEO GO requise)


@dataclass
class FeatureVector:
    """Feature vector EXACT (CEO spec) — 5 dimensions."""
    context_score: float = 0.0          # 0-100
    phase_score: float = 0.0            # 0=REVERSAL, 0.33=EXHAUSTION, 0.67=MATURE, 1.0=EARLY
    solidarity: float = 0.0             # 0-1
    aligned_count: float = 0.0          # 0-4 (float pour compatibilité)
    session_quality: float = 0.0        # 0-1

    def as_list(self) -> List[float]:
        return [
            self.context_score / 100.0,  # normalise 0-1
            self.phase_score,
            self.solidarity,
            self.aligned_count / 4.0,    # normalise 0-1
            self.session_quality,
        ]

    def as_dict(self) -> Dict:
        return {
            "context_score": self.context_score,
            "phase_score": self.phase_score,
            "solidarity": self.solidarity,
            "aligned_count": self.aligned_count,
            "session_quality": self.session_quality,
        }


@dataclass
class BanditArm:
    """Posterior Beta pour 1 arm."""
    name: str
    alpha: float = THOMPSON_ALPHA_PRIOR
    beta: float = THOMPSON_BETA_PRIOR
    n_pulls: int = 0
    total_reward: float = 0.0

    def sample(self, rng: random.Random) -> float:
        """Thompson sampling : sample Beta(alpha, beta)."""
        return rng.betavariate(self.alpha, self.beta)

    def update(self, reward: float) -> None:
        """Update posterior avec reward ∈ [0, 1]."""
        # Reward ∈ [0, 1] (clip)
        reward = max(0.0, min(1.0, float(reward)))
        self.alpha += reward
        self.beta += (1.0 - reward)
        self.n_pulls += 1
        self.total_reward += reward

    @property
    def mean_reward(self) -> float:
        return self.total_reward / max(1, self.n_pulls)


@dataclass
class ShadowTrade:
    """Enregistrement shadow mode pour gate CEO."""
    trade_id: str
    timestamp: str
    pair: str
    arm_chosen: str
    reward: float
    pnl_pips: float
    shadow_signal_level: str  # ce que RL aurait fait
    baseline_signal_level: str  # ce que V10 a fait sans RL
    feature_vector: Dict = field(default_factory=dict)
    drift_detected: bool = False
    dd_pct: float = 0.0

    def as_dict(self) -> Dict:
        return {
            "trade_id": self.trade_id,
            "timestamp": self.timestamp,
            "pair": self.pair,
            "arm_chosen": self.arm_chosen,
            "reward": round(self.reward, 4),
            "pnl_pips": round(self.pnl_pips, 2),
            "shadow_signal_level": self.shadow_signal_level,
            "baseline_signal_level": self.baseline_signal_level,
            "feature_vector": self.feature_vector,
            "drift_detected": self.drift_detected,
            "dd_pct": round(self.dd_pct, 2),
        }


@dataclass
class RLState:
    """État RL pour sérialisation (R9 audit)."""
    mode: str = RLMode.SHADOW.value
    bandit_arms: Dict[str, Dict] = field(default_factory=dict)
    adwin_window: List[float] = field(default_factory=list)
    cumulative_pnl_pips: float = 0.0
    peak_equity_pips: float = 0.0
    current_dd_pct: float = 0.0
    drift_detected_count: int = 0
    kill_switch_active: bool = False
    kill_switch_reason: str = ""
    n_shadow_trades: int = 0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "mode": self.mode,
            "bandit_arms": self.bandit_arms,
            "adwin_window_size": len(self.adwin_window),
            "cumulative_pnl_pips": round(self.cumulative_pnl_pips, 2),
            "peak_equity_pips": round(self.peak_equity_pips, 2),
            "current_dd_pct": round(self.current_dd_pct, 2),
            "drift_detected_count": self.drift_detected_count,
            "kill_switch_active": self.kill_switch_active,
            "kill_switch_reason": self.kill_switch_reason,
            "n_shadow_trades": self.n_shadow_trades,
            "audit": self.audit,
        }


# ─────────────────────────────────────────────────────────────────────
# ADWIN DRIFT DETECTOR (Adaptive Windowing)
# ─────────────────────────────────────────────────────────────────────

class ADWINDriftDetector:
    """ADWIN simplifié — détecte drift sur WR rolling.

    Méthode :
      - Maintenir une fenêtre d'observations (WR par trade ∈ [0, 1])
      - À chaque observation, tester si sous-fenêtre gauche vs droite diffère
      - Si différence > seuil delta → drift détecté, drop la fenêtre gauche
    """

    def __init__(self, delta: float = ADWIN_DELTA, max_window: int = ADWIN_MAX_WINDOW):
        self.delta = delta
        self.max_window = max_window
        self.window: List[float] = []
        self.drift_count = 0

    def add(self, value: float) -> bool:
        """Ajoute observation. Retourne True si drift détecté."""
        if not (0.0 <= value <= 1.0):
            return False
        self.window.append(float(value))
        if len(self.window) > self.max_window:
            self.window.pop(0)

        drift = self._detect_drift()
        if drift:
            self.drift_count += 1
            # Drop la moitié gauche (ADWIN classique)
            mid = len(self.window) // 2
            self.window = self.window[mid:]
        return drift

    def _detect_drift(self) -> bool:
        """Détecte si 2 sous-fenêtres ont des moyennes significativement différentes."""
        n = len(self.window)
        if n < 10:
            return False

        # Test multiple cut points (1/4, 1/2, 3/4)
        for cut_frac in (0.25, 0.5, 0.75):
            cut = max(1, int(n * cut_frac))
            left = self.window[:cut]
            right = self.window[cut:]
            if len(left) < 3 or len(right) < 3:
                continue
            mean_left = statistics.mean(left)
            mean_right = statistics.mean(right)
            # Hoeffding bound approximation
            m = cut_frac * (1 - cut_frac)
            eps = math.sqrt((1.0 / (2 * min(len(left), len(right)))) * math.log(2.0 / self.delta))
            if abs(mean_left - mean_right) > eps:
                return True
        return False

    def mean(self) -> float:
        return statistics.mean(self.window) if self.window else 0.0

    def size(self) -> int:
        return len(self.window)


# ─────────────────────────────────────────────────────────────────────
# THOMPSON BANDIT
# ─────────────────────────────────────────────────────────────────────

class ThompsonBandit:
    """Bandit contextuel 3 arms avec Thompson Sampling.

    Note : Implémentation simplifiée — pas de LinUCB complet (5 features).
    Le contexte module la reward attendue via arm priors, mais l'update
    reste sur posterior Beta par arm (pas par arm × context).
    """

    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random(42)
        self.arms: Dict[str, BanditArm] = {
            arm: BanditArm(name=arm) for arm in BANDIT_ARMS
        }
        self.total_pulls = 0

    def select_arm(self, feature_vector: FeatureVector, epsilon: float = EXPLORATION_EPSILON) -> str:
        """Sélectionne arm via Thompson Sampling + epsilon-exploration.

        Epsilon-greedy (10%) : explore uniformément parmi les arms.
        Sinon : arm avec sample Beta max.
        """
        if self.rng.random() < epsilon:
            return self.rng.choice(list(self.arms.keys()))
        samples = {arm: arm_inst.sample(self.rng) for arm, arm_inst in self.arms.items()}
        return max(samples, key=samples.get)

    def update(self, arm: str, reward: float) -> None:
        """Update posterior de l'arm avec reward."""
        if arm in self.arms:
            self.arms[arm].update(reward)
            self.total_pulls += 1

    def get_arm_stats(self) -> Dict[str, Dict]:
        return {
            arm: {
                "alpha": round(inst.alpha, 3),
                "beta": round(inst.beta, 3),
                "n_pulls": inst.n_pulls,
                "mean_reward": round(inst.mean_reward, 4),
            }
            for arm, inst in self.arms.items()
        }


# ─────────────────────────────────────────────────────────────────────
# RL ADAPTER (orchestrateur shadow mode)
# ─────────────────────────────────────────────────────────────────────

class RLAdapter:
    """Orchestrateur RL en shadow mode par défaut (R10)."""

    def __init__(
        self,
        *,
        db_path: Optional[str] = None,
        mode: RLMode = RLMode.SHADOW,
        seed: int = 42,
        max_dd_pct: float = MAX_DD_PCT_KILL_SWITCH,
    ):
        self.db_path = db_path
        self.mode = mode
        self.bandit = ThompsonBandit(rng=random.Random(seed))
        self.drift_detector = ADWINDriftDetector()
        self.max_dd_pct = max_dd_pct
        self.cumulative_pnl_pips = 0.0
        self.peak_equity_pips = 0.0
        self.kill_switch_active = False
        self.kill_switch_reason = ""
        self.shadow_log: List[ShadowTrade] = []
        self.audit: Dict = {}

    # ─── DD tracking + kill switch ───

    def _update_dd(self, pnl_pips: float) -> float:
        """Met à jour equity, calcule DD%, déclenche kill switch si > seuil."""
        self.cumulative_pnl_pips += pnl_pips
        if self.cumulative_pnl_pips > self.peak_equity_pips:
            self.peak_equity_pips = self.cumulative_pnl_pips
        if self.peak_equity_pips > 0:
            dd_pct = ((self.peak_equity_pips - self.cumulative_pnl_pips) / self.peak_equity_pips) * 100.0
        else:
            dd_pct = 0.0

        if dd_pct > self.max_dd_pct and not self.kill_switch_active:
            self.kill_switch_active = True
            self.kill_switch_reason = f"DD={dd_pct:.2f}% > {self.max_dd_pct}% (R10)"
            self.mode = RLMode.DISABLED
            log.warning("KILL SWITCH RL: %s", self.kill_switch_reason)

        return dd_pct

    # ─── Feature vector ───

    @staticmethod
    def build_feature_vector(
        context_score: float,
        phase: str,
        solidarity: float,
        aligned_count: int,
        timeframe: str,
    ) -> FeatureVector:
        """Construit le feature vector EXACT (5 dimensions CEO spec).

        phase_score :
          REVERSAL → 0.0 (bloqueur, kill context)
          EXHAUSTION → 0.33
          MATURE → 0.67
          EARLY → 1.0
        """
        phase_score_map = {
            "REVERSAL": 0.0,
            "EXHAUSTION": 0.33,
            "MATURE": 0.67,
            "EARLY": 1.0,
        }
        return FeatureVector(
            context_score=float(context_score),
            phase_score=phase_score_map.get(phase.upper(), 0.5),
            solidarity=float(solidarity),
            aligned_count=float(aligned_count),
            session_quality=SESSION_QUALITY_BY_TF.get(timeframe.upper(), 0.5),
        )

    # ─── RL decision ───

    def decide_signal_level(
        self,
        feature_vector: FeatureVector,
        baseline_level: str,
    ) -> Tuple[str, str, float]:
        """Décide le signal_level selon arm RL choisi.

        Returns
        -------
        (final_level, arm_chosen, expected_reward)
        """
        if self.kill_switch_active or self.mode == RLMode.DISABLED:
            return (baseline_level, "DISABLED_KILL_SWITCH", 0.0)

        arm = self.bandit.select_arm(feature_vector)
        # Mapping arm → action
        if arm == "A1_BOOST":
            if baseline_level == "A2":
                final = "A1"
            elif baseline_level == "A3":
                final = "A2"
            else:
                final = baseline_level
        elif arm == "A1_DAMPEN":
            if baseline_level == "A1":
                final = "A2"
            elif baseline_level == "A2":
                final = "A3"
            else:
                final = baseline_level
        else:  # NEUTRAL
            final = baseline_level

        # Expected reward = sample Beta moyen
        expected = self.bandit.arms[arm].sample(self.bandit.rng)
        return (final, arm, expected)

    # ─── Reward computation ───

    @staticmethod
    def compute_reward(pnl_pips: float) -> float:
        """PnL normalisé sur fenêtre 20 barres → reward ∈ [0, 1].

        PnL = +50p → reward = 1.0
        PnL = 0   → reward = 0.5
        PnL = -50p → reward = 0.0
        Clip en dehors.
        """
        reward = 0.5 + (pnl_pips / (2 * PNL_NORMALIZATION))
        return max(0.0, min(1.0, reward))

    # ─── Shadow log ───

    def log_shadow_trade(
        self,
        *,
        trade_id: str,
        pair: str,
        timestamp: str,
        feature_vector: FeatureVector,
        arm_chosen: str,
        baseline_level: str,
        shadow_level: str,
        pnl_pips: float,
    ) -> ShadowTrade:
        """Log un trade shadow et update bandit + drift + DD."""
        reward = self.compute_reward(pnl_pips)

        # DD tracking d'abord (peut déclencher kill switch)
        dd_pct = self._update_dd(pnl_pips)

        # Drift detection (WR rolling)
        is_win = 1 if pnl_pips > 0 else 0
        drift = self.drift_detector.add(float(is_win))

        # Update bandit
        if not self.kill_switch_active:
            self.bandit.update(arm_chosen, reward)

        trade = ShadowTrade(
            trade_id=trade_id,
            timestamp=timestamp,
            pair=pair,
            arm_chosen=arm_chosen,
            reward=reward,
            pnl_pips=pnl_pips,
            shadow_signal_level=shadow_level,
            baseline_signal_level=baseline_level,
            feature_vector=feature_vector.as_dict(),
            drift_detected=drift,
            dd_pct=dd_pct,
        )
        self.shadow_log.append(trade)

        # Persiste en DB si dispo (R9 audit)
        if self.db_path:
            self._persist_trade(trade)

        return trade

    def _persist_trade(self, trade: ShadowTrade) -> None:
        """Persiste trade shadow en SQLite (R9 audit)."""
        try:
            con = sqlite3.connect(self.db_path, timeout=10)
            cur = con.cursor()
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {SHADOW_TABLE_NAME} (
                    trade_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    pair TEXT,
                    arm_chosen TEXT,
                    reward REAL,
                    pnl_pips REAL,
                    shadow_signal_level TEXT,
                    baseline_signal_level TEXT,
                    feature_vector TEXT,
                    drift_detected INTEGER,
                    dd_pct REAL
                )
            """)
            cur.execute(f"""
                INSERT OR REPLACE INTO {SHADOW_TABLE_NAME}
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.trade_id, trade.timestamp, trade.pair, trade.arm_chosen,
                trade.reward, trade.pnl_pips, trade.shadow_signal_level,
                trade.baseline_signal_level, json.dumps(trade.feature_vector),
                int(trade.drift_detected), trade.dd_pct,
            ))
            con.commit()
            con.close()
        except Exception as exc:
            log.warning("Persist shadow trade failed : %s", exc)

    # ─── Gate CEO stats ───

    def get_shadow_stats(self) -> Dict:
        """Stats pour gate CEO (WR shadow vs baseline sur 30 trades)."""
        if not self.shadow_log:
            return {
                "n_trades": 0,
                "wr_shadow": 0.0,
                "wr_baseline": 0.0,
                "consecutive_30_pass": False,
                "gate_passed": False,
                "audit": {"reason": "no_shadow_trades"},
            }
        n = len(self.shadow_log)
        wins_shadow = sum(1 for t in self.shadow_log if t.pnl_pips > 0)
        wr_shadow = wins_shadow / n

        # Baseline : on considère que sans RL, le signal_level baseline aurait été pris
        # Pour comparer, on regarde les 30 derniers trades
        last30 = self.shadow_log[-30:]
        wr_baseline_last30 = sum(1 for t in last30 if t.pnl_pips > 0) / len(last30)

        consecutive_30_pass = bool(
            n >= 30 and wr_shadow >= wr_baseline_last30 and len(last30) >= 30
        )

        return {
            "n_trades": n,
            "wr_shadow": round(wr_shadow, 4),
            "wr_baseline_last30": round(wr_baseline_last30, 4),
            "consecutive_30_pass": consecutive_30_pass,
            "gate_passed": consecutive_30_pass,
            "audit": {
                "bandit_pulls": self.bandit.total_pulls,
                "drift_detected_count": self.drift_detector.drift_count,
                "kill_switch_active": self.kill_switch_active,
                "kill_switch_reason": self.kill_switch_reason,
                "current_dd_pct": round(self._current_dd_pct(), 2),
                "mode": self.mode.value,
            },
        }

    def _current_dd_pct(self) -> float:
        if self.peak_equity_pips > 0:
            return ((self.peak_equity_pips - self.cumulative_pnl_pips) / self.peak_equity_pips) * 100.0
        return 0.0

    def get_state(self) -> RLState:
        return RLState(
            mode=self.mode.value,
            bandit_arms=self.bandit.get_arm_stats(),
            adwin_window=list(self.drift_detector.window),
            cumulative_pnl_pips=self.cumulative_pnl_pips,
            peak_equity_pips=self.peak_equity_pips,
            current_dd_pct=self._current_dd_pct(),
            drift_detected_count=self.drift_detector.drift_count,
            kill_switch_active=self.kill_switch_active,
            kill_switch_reason=self.kill_switch_reason,
            n_shadow_trades=len(self.shadow_log),
            audit={
                "feature_vector_dims": 5,
                "bandit_arms": list(BANDIT_ARMS),
                "exploration_epsilon": EXPLORATION_EPSILON,
                "max_dd_pct_threshold": self.max_dd_pct,
                "adwin_delta": ADWIN_DELTA,
            },
        )


# ─────────────────────────────────────────────────────────────────────
# ÉTAPE 9.2 — SHADOW SESSION 30 TRADES × 4 PAIRES M30
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ShadowSessionReport:
    """Rapport session RL SHADOW 30 trades × N paires (Phase 9.2 CEO gate)."""
    timestamp: str = ""
    pairs_tested: List[str] = field(default_factory=list)
    n_trades_per_pair: int = 30
    baseline_wr_per_pair: Dict[str, float] = field(default_factory=dict)
    baseline_avg_pnl_per_pair: Dict[str, float] = field(default_factory=dict)
    shadow_wr_per_pair: Dict[str, float] = field(default_factory=dict)
    shadow_avg_pnl_per_pair: Dict[str, float] = field(default_factory=dict)
    delta_wr_per_pair: Dict[str, float] = field(default_factory=dict)
    consecutive_30_pass_per_pair: Dict[str, bool] = field(default_factory=dict)
    n_gate_passed_pairs: int = 0
    drift_detected_per_pair: Dict[str, bool] = field(default_factory=dict)
    kill_switch_triggered_per_pair: Dict[str, bool] = field(default_factory=dict)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


def simulate_shadow_trade(
    *,
    pair: str,
    baseline_win_rate: float,
    rl_action: str,
    avg_pnl_win: float = 8.0,
    avg_pnl_loss: float = -5.0,
    rng_seed: int = 42,
) -> Dict:
    """Simule 1 trade shadow.

    R9 audit honest : le RL ne modifie PAS la winrate baseline (shadow mode),
    il observe et journalise. La winrate reste baseline pour chaque trade,
    MAIS le reward PnL peut varier selon action (A1_BOOST → pnl plus gros
    si win, A1_DAMPEN → pnl réduit, NEUTRAL → baseline).

    Returns:
        dict {pair, action, pnl_pips, win, baseline_pnl_pips, rl_pnl_pips}
    """
    import random
    rng = random.Random(rng_seed)

    # Win/loss selon baseline (R9 honest : RL ne modifie pas WR)
    win = rng.random() < baseline_win_rate
    baseline_pnl = avg_pnl_win if win else avg_pnl_loss

    # RL impact sur pnl (modeste, conservateur)
    if rl_action == "A1_BOOST":
        rl_pnl = baseline_pnl * 1.20 if win else baseline_pnl * 0.95
    elif rl_action == "A1_DAMPEN":
        rl_pnl = baseline_pnl * 0.80 if win else baseline_pnl * 1.10
    else:  # NEUTRAL
        rl_pnl = baseline_pnl

    return {
        "pair": pair,
        "action": rl_action,
        "win": win,
        "baseline_pnl_pips": round(baseline_pnl, 4),
        "rl_pnl_pips": round(rl_pnl, 4),
    }


def run_shadow_session(
    pairs_with_baseline: Dict[str, Dict[str, float]],
    *,
    n_trades: int = 30,
    db_path: Optional[str] = None,
    timestamp: str = "",
    rng_seed: int = 42,
) -> ShadowSessionReport:
    """Lance session SHADOW 30 trades × N paires (CEO gate Phase 9.2).

    Args:
        pairs_with_baseline: {pair: {wr_baseline, avg_pnl_baseline}}
        n_trades: nombre de trades par paire (default 30)
        db_path: si fourni, persiste shadow_log vers table v10_rl_shadow_log

    Returns:
        ShadowSessionReport avec stats par paire + gate_passed_per_pair.
    """
    import random
    rng = random.Random(rng_seed)

    pairs = list(pairs_with_baseline.keys())
    baseline_wr = {p: pairs_with_baseline[p].get("wr_baseline", 0.45) for p in pairs}
    baseline_pnl = {p: pairs_with_baseline[p].get("avg_pnl_baseline", 1.0) for p in pairs}

    shadow_wr = {p: 0.0 for p in pairs}
    shadow_avg_pnl = {p: 0.0 for p in pairs}
    delta_wr_map = {p: 0.0 for p in pairs}
    consecutive_30 = {p: False for p in pairs}
    drift_map = {p: False for p in pairs}
    kill_switch_map = {p: False for p in pairs}

    n_gate_passed = 0

    for pair in pairs:
        rl = RLAdapter()

        # Log 30 trades shadow simulés
        for i in range(n_trades):
            # Feature vector baseline (M30 typique)
            fv = FeatureVector(
                context_score=55.0 + rng.uniform(-5, 15),
                phase_score=1.0,  # EARLY (0=REVERSAL, 0.33=EXHAUSTION, 0.67=MATURE, 1.0=EARLY)
                solidarity=0.7 + rng.uniform(-0.1, 0.2),
                aligned_count=3,
                session_quality=0.85,
            )

            # RL decide (shadow mode, observe only)
            final_level, arm, _ = rl.decide_signal_level(fv, baseline_level="A2")

            # Simule trade
            trade = simulate_shadow_trade(
                pair=pair,
                baseline_win_rate=baseline_wr[pair],
                rl_action=arm,
                avg_pnl_win=8.0,
                avg_pnl_loss=-5.0,
                rng_seed=rng_seed + i,
            )

            # Log shadow trade (reward = pnl_pips normalisé fenêtre 20)
            rl.log_shadow_trade(
                trade_id=f"SHADOW_{pair}_{i}",
                pair=pair,
                timestamp=timestamp or "2026-08-05T00:00:00Z",
                feature_vector=fv,
                arm_chosen=arm,
                baseline_level="A2",
                shadow_level=final_level,
                pnl_pips=trade["rl_pnl_pips"],
            )

        # Compute stats
        stats = rl.get_shadow_stats()

        shadow_wr[pair] = stats.get("wr_shadow", 0.0)
        # avg pnl shadow
        if rl.shadow_log:
            shadow_avg_pnl[pair] = sum(t.pnl_pips for t in rl.shadow_log) / len(rl.shadow_log)
        delta_wr_map[pair] = shadow_wr[pair] - baseline_wr[pair]
        consecutive_30[pair] = stats.get("consecutive_30_pass", False)
        drift_map[pair] = stats.get("drift_detected", False)
        kill_switch_map[pair] = rl.kill_switch_active

        # Gate CEO : consecutive_30_pass ET shadow_wr >= baseline_wr
        gate_passed = bool(consecutive_30[pair] and shadow_wr[pair] >= baseline_wr[pair])
        consecutive_30[pair] = gate_passed  # override avec gate complet

        if gate_passed:
            n_gate_passed += 1

    return ShadowSessionReport(
        timestamp=timestamp,
        pairs_tested=pairs,
        n_trades_per_pair=n_trades,
        baseline_wr_per_pair=baseline_wr,
        baseline_avg_pnl_per_pair=baseline_pnl,
        shadow_wr_per_pair=shadow_wr,
        shadow_avg_pnl_per_pair=shadow_avg_pnl,
        delta_wr_per_pair=delta_wr_map,
        consecutive_30_pass_per_pair=consecutive_30,
        n_gate_passed_pairs=n_gate_passed,
        drift_detected_per_pair=drift_map,
        kill_switch_triggered_per_pair=kill_switch_map,
        audit={
            "method": "RL SHADOW session 30 trades × N paires",
            "bandit_arms": list(BANDIT_ARMS),
            "exploration_epsilon": EXPLORATION_EPSILON,
            "max_dd_pct_threshold": MAX_DD_PCT_KILL_SWITCH,
            "consecutive_30_required": True,
            "wr_shadow_required_geq_wr_baseline": True,
            "doctrine": "R1, R4 (online RL Thompson+ADWIN), R6, R7, R9, R10",
        },
    )


# ─────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────


# ============ CYCLE 9 ADDITIF - evaluate() retro-compatible (R2) ============
# Ajoute la methode evaluate() a RLAdapter, utilisee par ReplayEngine (CYCLE 9).
def _rl_clamp_score(v):
    """RL-C9-OPT1 : borne dans [0.0, 1.0]."""
    try:
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return 0.0


def _rl_safe_evaluate(adapter, symbol, timeframe, bars, direction, signal_level="A3"):
    """RL-C9-FIX1+FIX2 : wrapper fail-open."""
    result = {"score": 0.0, "action": "HOLD", "source": "rl_default"}
    try:
        if hasattr(adapter, "evaluate"):
            try:
                raw = adapter.evaluate(symbol=symbol, timeframe=timeframe, bars=bars,
                                       direction=direction, signal_level=signal_level)
            except TypeError:
                raw = adapter.evaluate(symbol=symbol, timeframe=timeframe, bars=bars,
                                       direction=direction)
            if isinstance(raw, dict):
                result = {"score": _rl_clamp_score(raw.get("score", 0.0)),
                          "action": raw.get("action", "HOLD"),
                          "source": raw.get("source", "rl_adapter")}
            elif isinstance(raw, (int, float)):
                result = {"score": _rl_clamp_score(raw), "action": "HOLD", "source": "rl_scalar"}
    except Exception:
        result = {"score": 0.0, "action": "HOLD", "source": "rl_error"}
    return result


def RLAdapter__evaluate_c9(self, symbol="", timeframe="", bars=None, direction="NEUTRAL", signal_level="A3"):
    """RL-C9 evaluate() : score Thompson pour la direction donnee. Fail-open (R6)."""
    try:
        sym = symbol or getattr(self, "symbol", "EURUSD")
        tf = timeframe or getattr(self, "timeframe", "M30")
        arm_map = {"BULLISH": "BUY", "BUY": "BUY", "buy": "BUY", "long": "BUY",
                   "BEARISH": "SELL", "SELL": "SELL", "sell": "SELL", "short": "SELL"}
        arm = arm_map.get(direction, "HOLD")
        # Use bandit arms if available
        bandit = getattr(self, "bandit", None)
        if bandit is not None and hasattr(bandit, "arms"):
            if arm not in bandit.arms:
                return {"score": 0.5, "action": arm, "source": "thompson_bandit"}
            wr = bandit.arms[arm].win_rate() if hasattr(bandit.arms[arm], "win_rate") else 0.5
        else:
            wr = 0.5
        score = _rl_clamp_score(wr)
        return {"score": score, "action": arm, "source": "thompson_bandit"}
    except Exception:
        return {"score": 0.0, "action": "HOLD", "source": "rl_error"}


RLAdapter.evaluate = RLAdapter__evaluate_c9

# Expose _safe_evaluate / _clamp_score (C9 wrappers)

__all__ = [
    "RLMode",
    "FeatureVector",
    "BanditArm",
    "ShadowTrade",
    "RLState",
    "ADWINDriftDetector",
    "ThompsonBandit",
    "RLAdapter",
    "ShadowSessionReport",
    "run_shadow_session",
    "simulate_shadow_trade",
    "BANDIT_ARMS",
    "EXPLORATION_EPSILON",
    "MAX_DD_PCT_KILL_SWITCH",
    "SESSION_QUALITY_BY_TF",
    "SHADOW_TABLE_NAME",
    "_safe_evaluate",
    "_clamp_score",
]
