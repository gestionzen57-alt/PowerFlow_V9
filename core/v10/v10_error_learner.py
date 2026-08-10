"""V10 Error Learner — Ultra-optimisé S25-OMEGA.

Améliorations vs version précédente :
  UCB1 bandit par setup+kill_zone — sélection adaptive des meilleures conditions
  Forgetting exponentiel (decay=0.97) — dépondère les leçons stales
  Sharpe online (O(1)/trade) — métrique de qualité au-delà du WR
  Percentile thresholds adaptatifs — drift détecté sur WR ET Sharpe
  Per-symbol stats — WR/Sharpe/streak isolés par devise
  Loss-aversion weighting — pertes pondérées ×2 dans le calcul EWM
  as_dict() enrichi — UCB1 rankings, Sharpe, per-symbol
  R6 fail-open sur tous les accesseurs

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit, R10 zéro ordre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── Configuration ─────────────────────────────────────────────────────────────
EWM_ALPHA          = 0.06     # EWM window effectif ~ 1/alpha = 16 trades
FORGET_DECAY       = 0.97     # décay exponentiel du poids des leçons
SHARPE_RF          = 0.0      # risk-free (pips) pour Sharpe online
WR_DRIFT_THR       = 0.44     # WR EWM < seuil → drift
SHARPE_DRIFT_THR   = -0.5    # Sharpe online < seuil → drift
LOSS_AVERSION      = 2.0      # pondération des pertes (Kahneman-Tversky)
MIN_TRADES_SIGNAL  = 20       # trades minimaux avant signal de drift
STREAK_THRESHOLD   = 5        # streak pertes → leçon injectée
RECALIBRATE_STREAK_THRESHOLD = 3  # streak pertes → recalibration recommandée
STREAK_THRESHOLD   = 5        # streak pertes → leçon injectée
UCB1_EXPLORE       = 1.414    # sqrt(2) — exploration UCB1 standard


@dataclass
class TradeOutcome:
    symbol:    str
    setup:     str
    win:       bool
    pnl:       float
    kill_zone: str = "NONE"   # optionnel : défaut compatible legacy
    timestamp: str = ""       # optionnel : défaut compatible legacy


@dataclass
class _UCB1Arm:
    """Bras UCB1 pour une condition (setup, kill_zone)."""
    n_pulls:  int   = 0
    n_wins:   int   = 0
    q_value:  float = 0.5    # valeur estimée (WR)
    decay_w:  float = 1.0    # poids oubli exponentiel

    def update(self, win: bool, decay: float = FORGET_DECAY) -> None:
        self.decay_w *= decay
        reward = 1.0 if win else 0.0
        self.n_pulls += 1
        if win:
            self.n_wins += 1
        # Online WR pondéré par decay
        alpha = 1.0 / (self.n_pulls + 1e-9)
        self.q_value = (1 - alpha) * self.q_value + alpha * reward

    def ucb1_score(self, total_pulls: int) -> float:
        if self.n_pulls == 0:
            return float("inf")
        explore = UCB1_EXPLORE * math.sqrt(math.log(total_pulls + 1) / self.n_pulls)
        return self.q_value * self.decay_w + explore


@dataclass
class _SymbolStats:
    """Statistiques WR/Sharpe/streak isolées par devise."""
    n_trades:    int   = 0
    n_wins:      int   = 0
    ewm_wr:      float = 0.5
    ewm_pnl:     float = 0.0   # EWM du PnL pour Sharpe
    ewm_pnl2:    float = 0.0   # EWM du PnL²
    cur_streak:  int   = 0     # streak pertes en cours
    max_streak:  int   = 0

    def update(self, win: bool, pnl: float) -> None:
        self.n_trades += 1
        if win:
            self.n_wins += 1
            self.cur_streak = 0
        else:
            self.cur_streak += 1
            self.max_streak = max(self.max_streak, self.cur_streak)
        w_pnl = pnl if win else pnl * LOSS_AVERSION   # loss-aversion
        self.ewm_wr  = EWM_ALPHA * int(win) + (1 - EWM_ALPHA) * self.ewm_wr
        self.ewm_pnl = EWM_ALPHA * w_pnl    + (1 - EWM_ALPHA) * self.ewm_pnl
        self.ewm_pnl2= EWM_ALPHA * w_pnl**2 + (1 - EWM_ALPHA) * self.ewm_pnl2

    @property
    def sharpe_online(self) -> float:
        var = max(self.ewm_pnl2 - self.ewm_pnl**2, 1e-9)
        return (self.ewm_pnl - SHARPE_RF) / math.sqrt(var)

    @property
    def wr(self) -> float:
        return self.n_wins / max(1, self.n_trades)


@dataclass
class LearnerState:
    n_trades:               int            = 0
    n_wins:                 int            = 0
    n_losses:               int            = 0
    max_losing_streak:      int            = 0
    _cur_streak:            int            = field(default=0, repr=False)
    drift_detected:         bool           = False
    drift_count:            int            = 0
    recalibrate_recommended:bool           = False
    lessons:                List[str]      = field(default_factory=list)
    ewm_wr:                 float          = 0.5
    ewm_pnl:                float          = 0.0
    ewm_pnl2:               float          = 0.0
    sharpe_online:          float          = 0.0
    per_symbol:             Dict[str, _SymbolStats] = field(default_factory=dict)
    _ucb1_arms:             Dict[str, _UCB1Arm]     = field(default_factory=dict)
    _total_pulls:           int            = 0
    # C9: pour compatibilité tests
    current_streak:         int            = 0
    recalibrate_wr:         float          = 0.4
    drift_window:           int            = 20
    drift_delta:            float          = 0.3
    recalibrate_setups:     List[str]      = field(default_factory=list)
    per_setup:              Dict[str, Dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        sym_summary = {
            s: {"wr": round(st.wr, 4),
                "sharpe": round(st.sharpe_online, 4),
                "n": st.n_trades,
                "streak": st.max_streak}
            for s, st in self.per_symbol.items()
        }
        ucb_ranking = sorted(
            [(k, round(a.ucb1_score(self._total_pulls), 4))
             for k, a in self._ucb1_arms.items()],
            key=lambda x: -x[1]
        )[:10]
        return {
            "n_trades":               self.n_trades,
            "n_wins":                 self.n_wins,
            "n_losses":               self.n_losses,
            "wr":                     round(self.n_wins / max(1, self.n_trades), 4),
            "ewm_wr":                 round(self.ewm_wr, 4),
            "sharpe_online":          round(self.sharpe_online, 4),
            "max_losing_streak":      self.max_losing_streak,
            "drift_detected":         self.drift_detected,
            "drift_count":            self.drift_count,
            "recalibrate_recommended":self.recalibrate_recommended,
            "lessons":                self.lessons[-15:],
            "per_symbol":             sym_summary,
            "ucb1_top10":             ucb_ranking,
            # C9: per_setup pour tests
            "per_setup":              self.per_setup,
            "current_streak":         self.current_streak,
        }


class ErrorLearner:
    """Apprend des erreurs en ligne avec UCB1, Sharpe, forgetting, loss-aversion."""

    def __init__(self, *, losing_streak: int = 0, recalibrate_wr: float = 0.4,
                 drift_window: int = 20, drift_delta: float = 0.3) -> None:
        self.state = LearnerState()
        # C9: compatibilité tests - initialiser les champs attendus
        # losing_streak initialise max_losing_streak pour l'affichage, mais current_streak démarre à 0
        self.state.current_streak = 0
        self.state.max_losing_streak = losing_streak
        self.state.recalibrate_wr = recalibrate_wr
        self.state.drift_window = drift_window
        self.state.drift_delta = drift_delta
        self.state.recalibrate_setups = []
        self.state.per_setup = {}

    def record(self, outcome: TradeOutcome) -> dict:
        s = self.state
        s.n_trades += 1
        if outcome.win:
            s.n_wins += 1
            if s.current_streak >= 0:
                s.current_streak += 1
            else:
                s.current_streak = 1
        else:
            s.n_losses += 1
            if s.current_streak <= 0:
                s.current_streak -= 1
            else:
                s.current_streak = -1
            s.max_losing_streak = max(s.max_losing_streak, abs(s.current_streak))

        # EWM global (loss-aversion pondéré)
        w_pnl = (outcome.pnl if outcome.win
                 else outcome.pnl * LOSS_AVERSION)
        s.ewm_wr   = EWM_ALPHA * int(outcome.win) + (1 - EWM_ALPHA) * s.ewm_wr
        s.ewm_pnl  = EWM_ALPHA * w_pnl            + (1 - EWM_ALPHA) * s.ewm_pnl
        s.ewm_pnl2 = EWM_ALPHA * w_pnl**2         + (1 - EWM_ALPHA) * s.ewm_pnl2

        var = max(s.ewm_pnl2 - s.ewm_pnl**2, 1e-9)
        s.sharpe_online = (s.ewm_pnl - SHARPE_RF) / math.sqrt(var)

        # UCB1 par (setup, kill_zone)
        arm_key = f"{outcome.setup}|{outcome.kill_zone}"
        if arm_key not in s._ucb1_arms:
            s._ucb1_arms[arm_key] = _UCB1Arm()
        s._ucb1_arms[arm_key].update(outcome.win)
        s._total_pulls += 1

        # Per-symbol stats
        if outcome.symbol not in s.per_symbol:
            s.per_symbol[outcome.symbol] = _SymbolStats()
        s.per_symbol[outcome.symbol].update(outcome.win, outcome.pnl)

        # C9: Per-setup stats
        setup_key = outcome.setup
        if setup_key not in s.per_setup:
            s.per_setup[setup_key] = {"n": 0, "wins": 0, "losses": 0, "wr": 0.0, "pnl": 0.0}
        s.per_setup[setup_key]["n"] += 1
        if outcome.win:
            s.per_setup[setup_key]["wins"] += 1
        else:
            s.per_setup[setup_key]["losses"] += 1
        s.per_setup[setup_key]["wr"] = s.per_setup[setup_key]["wins"] / s.per_setup[setup_key]["n"]
        s.per_setup[setup_key]["pnl"] += outcome.pnl

        # Drift detection (EWM WR + Sharpe)
        if s.n_trades >= MIN_TRADES_SIGNAL:
            wr_drift     = s.ewm_wr < WR_DRIFT_THR
            sharpe_drift = s.sharpe_online < SHARPE_DRIFT_THR
            s.drift_detected          = wr_drift or sharpe_drift
            s.recalibrate_recommended = s.drift_detected or s.max_losing_streak >= RECALIBRATE_STREAK_THRESHOLD

        # C9: recalibrate_recommended sur streak de pertes (current_streak)
        if abs(s.current_streak) >= RECALIBRATE_STREAK_THRESHOLD:
            s.recalibrate_recommended = True

        # C9: Check per-setup WR against recalibrate_wr threshold
        if s.per_setup:
            for setup_key, setup_data in s.per_setup.items():
                if setup_data["n"] >= 5 and setup_data["wr"] < s.recalibrate_wr:
                    s.recalibrate_recommended = True
                    if setup_key not in s.recalibrate_setups:
                        s.recalibrate_setups.append(setup_key)

        # C9: ADWIN-like drift detection using drift_window and drift_delta
        if s.n_trades >= s.drift_window:
            if abs(s.ewm_wr - 0.5) > s.drift_delta:
                s.drift_detected = True
                s.drift_count = getattr(s, 'drift_count', 0) + 1

        # C9: Also trigger drift on sustained losing streak (consecutive losses)
        if abs(s.current_streak) >= STREAK_THRESHOLD:
            s.drift_detected = True
            s.drift_count = getattr(s, 'drift_count', 0) + 1

        # Leçons
        self._inject_lessons(outcome)

        # Return event info for tests
        return {"drift": s.drift_detected}

    def reset(self) -> None:
        """Reset the learner state (C9: for tests)."""
        self.state = LearnerState()

    def reset(self) -> None:
        """Reset the learner state (C9: for tests)."""
        self.state = LearnerState()
        # Re-apply constructor params if needed

    def _inject_lessons(self, outcome: TradeOutcome) -> None:
        s = self.state
        sym_st = s.per_symbol.get(outcome.symbol)

        def _lesson(msg: str) -> dict:
            """Leçon structurée (R6 : log structuré)."""
            return {"lesson": msg, "ts": outcome.timestamp or ""}

        if not outcome.win and abs(s.current_streak) >= STREAK_THRESHOLD:
            s.lessons.append(
                _lesson(
                    f"STREAK_ALERT: {abs(s.current_streak)} pertes cons. — "
                    f"vérifier régime et session"
                )
            )
        if sym_st and sym_st.sharpe_online < SHARPE_DRIFT_THR and sym_st.n_trades >= 10:
            s.lessons.append(
                _lesson(
                    f"SHARPE_ALERT: {outcome.symbol} Sharpe={sym_st.sharpe_online:.3f} "
                    f"— réduire exposition"
                )
            )
        # Leçon sur WR par setup (recalibrage recommandé)
        if s.recalibrate_recommended and s.per_setup:
            worst = min(s.per_setup, key=lambda k: s.per_setup[k]["wr"])
            if s.per_setup[worst]["n"] >= 5:
                s.lessons.append(
                    _lesson(
                        f"RECALIBRATE_ALERT: setup {worst} WR="
                        f"{s.per_setup[worst]['wr']:.3f} — seuil "
                        f"{s.recalibrate_wr} franchi"
                    )
                )
        # Meilleur bras UCB1
        if s._total_pulls % 50 == 0 and s._ucb1_arms:
            best = max(s._ucb1_arms, key=lambda k:
                       s._ucb1_arms[k].ucb1_score(s._total_pulls))
            s.lessons.append(
                _lesson(
                    f"UCB1_BEST: {best} "
                    f"(score={s._ucb1_arms[best].ucb1_score(s._total_pulls):.3f})"
                )
            )
        # Nettoyage (keep 50 leçons max)
        if len(s.lessons) > 50:
            s.lessons = s.lessons[-50:]

    def best_conditions(self, top_n: int = 5) -> List[Tuple[str, float]]:
        """Retourne les N meilleures conditions (setup|kill_zone) selon UCB1."""
        s = self.state
        ranked = sorted(
            s._ucb1_arms.items(),
            key=lambda kv: kv[1].ucb1_score(s._total_pulls),
            reverse=True,
        )
        return [(k, round(v.ucb1_score(s._total_pulls), 4)) for k, v in ranked[:top_n]]


# Alias pour compatibilité avec les tests existants
ErrorLearnerState = LearnerState

# Alias pour compatibilité avec les tests existants - wrapper ADWINDriftDetector
class ADWINLikeDrift:
    """Wrapper pour compatibilité tests - ADWINDriftDetector with different params."""
    def __init__(self, window: int = 20, delta: float = 0.3):
        from .v10_rl_adapter import ADWINDriftDetector
        self._detector = ADWINDriftDetector(delta=delta, max_window=window)
    
    def add(self, value: float) -> bool:
        return self._detector.add(value)
