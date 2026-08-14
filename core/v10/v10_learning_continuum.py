"""V10 Learning Continuum — S25-OMEGA (mise à jour drift + Sharpe).

Suivi continu de l'évolution de l'apprentissage :
  Drift EWM double-signal (WR + Sharpe) — détection précoce
  Convergence score — mesure si l'apprentissage se stabilise
  Sharpe rolling online O(1) — sans fenêtre glissante
  Momentum WR — tendance court terme vs long terme
  Phase detector — WARMING_UP / LEARNING / CONVERGED / DRIFTING / DEGRADED
  as_dict() complet pour audit R9

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R9 audit, R10 zéro ordre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Config ────────────────────────────────────────────────────────────────────
EWM_FAST   = 0.10   # fenêtre rapide ~10 trades
EWM_SLOW   = 0.03   # fenêtre lente  ~33 trades
SHARPE_THR = -0.4   # Sharpe < seuil → alerte
WR_DRIFT   = 0.44   # WR EWM slow < seuil → drift
CONV_BAND  = 0.03   # |fast - slow| < band → convergé
MIN_WARMUP = 20     # trades avant sortie WARMING_UP

# Phases d'apprentissage
PHASE_WARMING  = "WARMING_UP"
PHASE_LEARNING = "LEARNING"
PHASE_CONVERGE = "CONVERGED"
PHASE_DRIFTING = "DRIFTING"
PHASE_DEGRADED = "DEGRADED"


@dataclass
class ContinuumState:
    n_total:        int   = 0
    ewm_wr_fast:    float = 0.5
    ewm_wr_slow:    float = 0.5
    ewm_pnl:        float = 0.0
    ewm_pnl2:       float = 0.0
    sharpe_online:  float = 0.0
    convergence:    float = 0.0    # 0=divergent, 1=convergé
    momentum:       float = 0.0    # fast - slow (>0 = amélioration)
    phase:          str   = PHASE_WARMING
    drift_count:    int   = 0      # nb de mises à jour en drift
    best_wr:        float = 0.0
    best_sharpe:    float = 0.0

    def as_dict(self) -> dict:
        return {
            "n_total":       self.n_total,
            "ewm_wr_fast":   round(self.ewm_wr_fast, 4),
            "ewm_wr_slow":   round(self.ewm_wr_slow, 4),
            "sharpe_online": round(self.sharpe_online, 4),
            "convergence":   round(self.convergence, 4),
            "momentum":      round(self.momentum, 4),
            "phase":         self.phase,
            "drift_count":   self.drift_count,
            "best_wr":       round(self.best_wr, 4),
            "best_sharpe":   round(self.best_sharpe, 4),
        }


class LearningContinuum:
    """Suivi continu de la qualité de l'apprentissage avec double EWM + Sharpe."""

    def __init__(self) -> None:
        self.state = ContinuumState()

    def update(
        self,
        wins:       int,
        losses:     int,
        sharpe:     float = 0.0,
        pnl_series: Optional[List[float]] = None,
    ) -> dict:
        """Met à jour le continuum avec les stats du dernier cycle de replay.

        Args:
            wins:       nombre total de wins (depuis ErrorLearner)
            losses:     nombre total de losses
            sharpe:     Sharpe online depuis ErrorLearner
            pnl_series: liste PnL du cycle courant (optionnel, enrichit le Sharpe)
        Returns:
            dict complet de l'état continuum
        """
        s = self.state
        n_cycle = wins + losses
        if n_cycle == 0:
            return s.as_dict()

        wr_cycle = wins / max(1, n_cycle)
        s.n_total += n_cycle

        # Double EWM (fast + slow)
        s.ewm_wr_fast = EWM_FAST * wr_cycle + (1 - EWM_FAST) * s.ewm_wr_fast
        s.ewm_wr_slow = EWM_SLOW * wr_cycle + (1 - EWM_SLOW) * s.ewm_wr_slow

        # Sharpe : priorité à ErrorLearner, enrichi si pnl_series fourni
        if pnl_series and len(pnl_series) > 1:
            for p in pnl_series:
                s.ewm_pnl  = 0.05 * p     + 0.95 * s.ewm_pnl
                s.ewm_pnl2 = 0.05 * p**2  + 0.95 * s.ewm_pnl2
            var = max(s.ewm_pnl2 - s.ewm_pnl**2, 1e-9)
            s.sharpe_online = s.ewm_pnl / math.sqrt(var)
        else:
            s.sharpe_online = sharpe

        # Convergence et momentum
        s.momentum    = s.ewm_wr_fast - s.ewm_wr_slow
        s.convergence = max(0.0, 1.0 - abs(s.momentum) / (CONV_BAND * 10))
        s.best_wr     = max(s.best_wr, s.ewm_wr_fast)
        s.best_sharpe = max(s.best_sharpe, s.sharpe_online)

        # Phase detector
        wr_drift   = s.ewm_wr_slow < WR_DRIFT
        shp_drift  = s.sharpe_online < SHARPE_THR

        if s.n_total < MIN_WARMUP:
            s.phase = PHASE_WARMING
        elif wr_drift or shp_drift:
            s.drift_count += 1
            s.phase = PHASE_DEGRADED if s.drift_count > 5 else PHASE_DRIFTING
        elif s.convergence > 0.80:
            s.phase = PHASE_CONVERGE
            s.drift_count = 0
        else:
            s.phase = PHASE_LEARNING
            if not (wr_drift or shp_drift):
                s.drift_count = max(0, s.drift_count - 1)

        return s.as_dict()

    def is_healthy(self) -> bool:
        """True si le système est en phase LEARNING ou CONVERGED."""
        return self.state.phase in (PHASE_LEARNING, PHASE_CONVERGE)

    def reset(self) -> None:
        """Réinitialise après une recalibration HARD."""
        self.state = ContinuumState()


# R2 additif (Mission 1 prep)
def learn_from_outcome(*args, **kwargs):
    return {'learned': False, 'reason': 'stub_R6_failopen'}
def drift_by_behavior(*args, **kwargs):
    return {'drift': False, 'n': 0}
DRIFT_WR_THRESHOLD = 0.40
MIN_N_FOR_DRIFT = 30
