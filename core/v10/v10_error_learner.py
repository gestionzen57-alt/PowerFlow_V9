"""V10 Error Learner — apprentissage des erreurs + drift + re-calibration (Sprint 5).

Boucle d'apprentissage des erreurs (R4/R8) : après chaque trade clôturé,
le module :
  1. **Enregistre** le résultat (win/loss, setup, kill_zone, contexte).
  2. **Détecte le drift/decay** (ADWIN simplifié sur WR rolling + perte
     durable par setup).
  3. **Déclenche la re-calibration** R8 si un KPI passe sous le seuil
     (retourne une recommandation de recalibrage, ne mute pas les
     constantes — additif pur R2).
  4. **Archive les leçons** apprises (R9 audit) pour coT et post-mortem.

Aligné sur `v10_rl_adapter.ADWINDriftDetector` mais orienté *apprentissage
des erreurs* (perte par setup × kill_zone) plutôt que bandit RL.

Doctrine : R1-AGIR, R2 additif pur, R4 online learning, R6 fail-open,
R7 tests, R8 auto-recalibration, R9 audit, R10 zéro ordre réel.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Seuils (défauts) — overridables
DEFAULT_DRIFT_WINDOW = 50
DEFAULT_DRIFT_DELTA = 0.10       # chute de WR ≥ 10pts → drift
DEFAULT_LOSING_STREAK = 5        # 5 pertes consécutives → attention
DEFAULT_RECALIBRATE_WR = 0.40    # WR setup < 40% → recommander recalibrage


@dataclass
class TradeOutcome:
    symbol: str = ""
    setup: str = "NONE"           # A1/A2/A3 ou nom du setup
    kill_zone: str = "UNKNOWN"
    win: bool = False
    pnl: float = 0.0
    timestamp: str = ""
    context: str = ""             # descriptif coT (post-mortem)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol, "setup": self.setup,
            "kill_zone": self.kill_zone, "win": self.win,
            "pnl": round(self.pnl, 4), "timestamp": self.timestamp,
            "context": self.context,
        }


@dataclass
class ErrorLearnerState:
    n_trades: int = 0
    n_wins: int = 0
    n_losses: int = 0
    current_streak: int = 0          # + wins, - losses
    max_losing_streak: int = 0
    drift_detected: bool = False
    drift_count: int = 0
    recalibrate_recommended: bool = False
    recalibrate_setups: List[str] = field(default_factory=list)
    per_setup: Dict[str, Dict] = field(default_factory=dict)
    lessons: List[Dict] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "n_trades": self.n_trades, "n_wins": self.n_wins,
            "n_losses": self.n_losses, "current_streak": self.current_streak,
            "max_losing_streak": self.max_losing_streak,
            "drift_detected": self.drift_detected,
            "drift_count": self.drift_count,
            "recalibrate_recommended": self.recalibrate_recommended,
            "recalibrate_setups": self.recalibrate_setups,
            "per_setup": self.per_setup,
            "lessons": list(self.lessons[-10:]),  # 10 dernières leçons
        }


class ADWINLikeDrift:
    """Drift detector simple (fenêtre glissante + seuil de chute)."""

    def __init__(self, window: int = DEFAULT_DRIFT_WINDOW,
                 delta: float = DEFAULT_DRIFT_DELTA):
        self.window = window
        self.delta = delta
        self._recent = deque(maxlen=window)

    def add(self, win: bool) -> bool:
        """Ajoute une observation, retourne True si drift détecté."""
        self._recent.append(1 if win else 0)
        if len(self._recent) < self.window:
            return False
        # WR de la 1ère moitié vs 2ème moitié
        mid = len(self._recent) // 2
        left = list(self._recent)[:mid]
        right = list(self._recent)[mid:]
        wr_left = sum(left) / len(left) if left else 0.0
        wr_right = sum(right) / len(right) if right else 0.0
        if wr_left - wr_right >= self.delta:
            return True
        return False


@dataclass
class ErrorLearner:
    """Apprentissage des erreurs — état persistant in-memory + méthode record."""

    drift_window: int = DEFAULT_DRIFT_WINDOW
    drift_delta: float = DEFAULT_DRIFT_DELTA
    losing_streak: int = DEFAULT_LOSING_STREAK
    recalibrate_wr: float = DEFAULT_RECALIBRATE_WR

    def __post_init__(self):
        self.state = ErrorLearnerState()
        self._drift = ADWINLikeDrift(self.drift_window, self.drift_delta)
        self._setup_stats: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=100))

    def record(self, outcome: TradeOutcome) -> Dict:
        """Enregistre un trade clôturé + détecte drift/recalibrage/leçon.

        Returns
        -------
        dict d'événements appris (R9 audit) : drift, recalibrate, lesson.
        """
        ev = {"drift": False, "recalibrate": False, "lesson": None}
        self.state.n_trades += 1
        if outcome.win:
            self.state.n_wins += 1
            self.state.current_streak = max(1, self.state.current_streak + 1)
        else:
            self.state.n_losses += 1
            self.state.current_streak = -abs(self.state.current_streak) - 1
            self.state.max_losing_streak = max(
                self.state.max_losing_streak, abs(self.state.current_streak))

        # Per-setup stats
        s = self._setup_stats[outcome.setup]
        s.append(1 if outcome.win else 0)
        self.state.per_setup[outcome.setup] = {
            "n": len(s), "wr": round(sum(s) / len(s), 4),
            "recent_streak": self._streak_of(s),
        }

        # Drift global
        if self._drift.add(outcome.win):
            self.state.drift_detected = True
            self.state.drift_count += 1
            ev["drift"] = True

        # Recalibration recommandée : WR setup < seuil OU losing streak
        wr = self.state.per_setup.get(outcome.setup, {}).get("wr", 0.0)
        if abs(self.state.current_streak) >= self.losing_streak or \
           (wr < self.recalibrate_wr and len(s) >= 10):
            if outcome.setup not in self.state.recalibrate_setups:
                self.state.recalibrate_setups.append(outcome.setup)
            self.state.recalibrate_recommended = True
            ev["recalibrate"] = True
            ev["lesson"] = self._make_lesson(outcome, wr)
            self.state.lessons.append(ev["lesson"])

        return ev

    def _streak_of(self, window: deque) -> int:
        """Streak actuel d'un setup (fin de fenêtre)."""
        lst = list(window)
        if not lst:
            return 0
        streak = 0
        last = lst[-1]
        for v in reversed(lst):
            if v == last:
                streak += 1 if last == 1 else -1
            else:
                break
        return streak

    def _make_lesson(self, outcome: TradeOutcome, wr: float) -> Dict:
        """Formule une leçon (coT post-mortem, R5/R9)."""
        return {
            "setup": outcome.setup,
            "kill_zone": outcome.kill_zone,
            "symbol": outcome.symbol,
            "win": outcome.win,
            "pnl": round(outcome.pnl, 4),
            "wr_at": round(wr, 4),
            "lesson": (
                f"{outcome.setup}@{outcome.kill_zone} WR={wr:.2f} → "
                f"recalibrer si < {self.recalibrate_wr:.2f} "
                f"ou losing_streak>={self.losing_streak}"
            ),
        }

    def reset(self) -> None:
        self.state = ErrorLearnerState()
        self._drift = ADWINLikeDrift(self.drift_window, self.drift_delta)
        self._setup_stats.clear()


__all__ = [
    "TradeOutcome",
    "ErrorLearnerState",
    "LearnerState",
    "ErrorLearner",
    "ADWINLikeDrift",
]

# Alias additif (R2) — rétro-compatibilité __init__.py + learning_persistence
LearnerState = ErrorLearnerState
