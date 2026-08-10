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
from pathlib import Path
from dataclasses import dataclass, field
from pathlib import Path
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

    # ── Compatibilité API (tests) ──────────────────────────────────────────────────
    # learn_from_outcome appelé par _learn dans replay_engine
    def learn_from_outcome(
        self,
        behavior_key: str,
        outcome: str,
        pnl: float,
    ) -> None:
        """Wrapper de compatibilité pour learn_from_outcome.
        
        Appelé depuis replay_engine._learn() pour chaque trade.
        Met à jour le continuum avec le résultat du trade.
        
        Args:
            behavior_key: clé de comportement (ex: "EURUSD_M30_london")
            outcome: "win" ou "loss"
            pnl: PnL en pips
        """
        win = 1 if outcome == "win" else 0
        loss = 1 if outcome == "loss" else 0
        # Use update with win/loss counts and pnl as Sharpe proxy
        self.update(
            wins=win,
            losses=loss,
            sharpe=pnl / 100.0,  # proxy Sharpe from PnL
            pnl_series=[pnl],
        )


# ── Fonctions de compatibilité API (tests) ──────────────────────────────────────────────────
# Ces fonctions sont attendues par les tests et __init__.py

def learn_from_outcome(
    *,
    behavior_id: int,
    is_win: bool,
    pnl: float = 0.0,
    db_path: Optional[str] = None,
) -> Dict:
    """
    Résout le résultat d'un comportement (win/loss) par son ID.
    
    Wrapper de compatibilité pour l'API attendue par les tests et __init__.py.
    Utilise v10_behavior_registry.resolve_outcome en interne.
    
    Returns:
        dict avec clés: learned (bool), reason (str), behavior_id (int)
    """
    try:
        from .v10_behavior_registry import resolve_outcome, DEFAULT_DB
    except ImportError:
        return {"learned": False, "reason": "registry_unavailable", "behavior_id": behavior_id}

    target_db = Path(db_path) if db_path else DEFAULT_DB
    if not target_db.exists():
        return {"learned": False, "reason": "no_registry", "behavior_id": behavior_id}

    ok = resolve_outcome(behavior_id=behavior_id, is_win=int(is_win), pnl_pips=pnl, db_path=target_db)
    return {"learned": ok, "reason": "ok" if ok else "not_found", "behavior_id": behavior_id}


def drift_by_behavior(
    *,
    observation_qualification: str,
    regime_hmm: str = "",
    coalition: str = "",
    antagonisme: str = "",
    timeframes: Optional[List[str]] = None,
    min_n: int = 5,
    db_path: Optional[str] = None,
    behavior_registry: Optional[object] = None,  # inutilisé, compat signature
) -> Dict:
    """
    Détecte le drift d'un comportement donné sa qualification.
    
    Wrapper de compatibilité pour l'API attendue par les tests et __init__.py.
    Utilise v10_behavior_registry.query_coherence en interne.
    
    Returns:
        dict avec clés: drifted (bool), wr (float), n (int), n_wins (int), reason (str)
    """
    try:
        from .v10_behavior_registry import query_coherence, DEFAULT_DB
    except ImportError:
        return {"drifted": False, "wr": 0.0, "n": 0, "n_wins": 0, "reason": "registry_unavailable"}

    target_db = Path(db_path) if db_path else DEFAULT_DB
    if not target_db.exists():
        return {"drifted": False, "wr": 0.0, "n": 0, "n_wins": 0, "reason": "no_registry"}

    # Seuil de drift : WR < 40% (DEFAULT_RECALIBRATE_WR du ErrorLearner)
    DRIFT_WR_THRESHOLD = 0.40

    coh = query_coherence(
        observation_qualification=observation_qualification,
        regime_hmm=regime_hmm,
        coalition=coalition,
        antagonisme=antagonisme,
        timeframes=timeframes,
        min_n=min_n,
        db_path=target_db,
    )

    n = coh.get("n", 0)
    wr = coh.get("wr", 0.0)
    n_wins = coh.get("n_wins", 0)
    reason = coh.get("reason", "unknown")

    if n < min_n:
        return {"drifted": False, "wr": wr, "n": n, "n_wins": n_wins, "reason": f"insufficient_{reason}"}

    # Si n=0, c'est comme "no registry" pour ce contexte
    if n == 0:
        return {"drifted": False, "wr": 0.0, "n": 0, "n_wins": 0, "reason": "no_registry"}

    drifted = wr < DRIFT_WR_THRESHOLD
    return {"drifted": drifted, "wr": wr, "n": n, "n_wins": n_wins, "reason": "drift" if drifted else "ok"}


__all__ = [
    "ContinuumState",
    "LearningContinuum",
    "PHASE_WARMING",
    "PHASE_LEARNING",
    "PHASE_CONVERGE",
    "PHASE_DRIFTING",
    "PHASE_DEGRADED",
    "EWM_FAST",
    "EWM_SLOW",
    "SHARPE_THR",
    "WR_DRIFT",
    "CONV_BAND",
    "MIN_WARMUP",
    "DRIFT_WR_THRESHOLD",
    "MIN_N_FOR_DRIFT",
    "learn_from_outcome",
    "drift_by_behavior",
]
