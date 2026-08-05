"""V10 Regime Detection — Hidden Markov Model + Bayesian change-point (Sprint 2).

Implémente la détection de régimes de marché via HMM (hmmlearn) et la
détection de ruptures via ruptures (PELT), en pure additif V10 (R2).

Objectifs (mandat autopilote quant Hermes §2.7/§2.8) :
  - HMM sur les returns pour classifier le marché en 5 états :
      TRENDING_UP / TRENDING_DOWN / RANGING / VOLATILE / NEWS_LOCK
    (aligné sur v10_market_regime).
  - Change-point detection (ruptures PELT) sur la série de returns pour
    détecter le decay (R8 auto-decay) et les changements de régime.
  - API fail-open (R6) : si les libs ne sont pas disponibles ou les
    données insuffisantes → régime UNKNOWN, score conservateur 0.5.

Doctrine V10 : R1-AGIR, R2 additif pur, R6 fail-open, R7 tests verts,
R9 audit sérialisable, R10 zéro ordre réel (compute only).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


class Regime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    NEWS_LOCK = "NEWS_LOCK"
    UNKNOWN = "UNKNOWN"  # R6 fail-open


@dataclass
class RegimeResult:
    symbol: str = ""
    timestamp: str = ""
    regime: Regime = Regime.UNKNOWN
    regime_confidence: float = 0.0  # [0,1] proba de l'état dominant
    state_probs: Dict[str, float] = field(default_factory=dict)
    n_states: int = 0
    change_points: List[int] = field(default_factory=list)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "regime": self.regime.value,
            "regime_confidence": round(self.regime_confidence, 3),
            "state_probs": {k: round(v, 3) for k, v in self.state_probs.items()},
            "n_states": self.n_states,
            "change_points": self.change_points,
            "audit": dict(self.audit),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers R6
# ─────────────────────────────────────────────────────────────────────
def _returns_from_closes(closes: List[float]) -> np.ndarray:
    """Log-returns depuis une série de closes. R6 : vide/short → array vide."""
    if not closes or len(closes) < 2:
        return np.array([])
    arr = np.asarray(closes, dtype=float)
    return np.diff(np.log(np.where(arr > 0, arr, 1e-9)))


def _available() -> bool:
    """Les libs quant sont-elles importables ? R6 fail-open."""
    try:
        import hmmlearn  # noqa: F401
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────
# HMM régimes
# ─────────────────────────────────────────────────────────────────────
def detect_hmm_regime(
    closes: List[float],
    *,
    symbol: str = "",
    timestamp: str = "",
    n_states: int = 5,
    n_iter: int = 50,
    min_samples: int = 30,
) -> RegimeResult:
    """Détecte le régime dominant via HMM GaussianMixture sur les returns.

    Les états HMM sont classés par leur mean de returns :
      état le plus haut mean   → TRENDING_UP
      état le plus bas mean    → TRENDING_DOWN
      états intermédiaires     → RANGING / VOLATILE selon la variance
    R6 : données < min_samples ou lib manquante → UNKNOWN, conf 0.0.
    """
    result = RegimeResult(symbol=symbol, timestamp=timestamp)
    result.n_states = n_states
    result.audit["method"] = "hmm_gaussian"

    returns = _returns_from_closes(closes)
    if len(returns) < min_samples:
        result.audit["reason"] = f"insufficient_data:{len(returns)}"
        return result
    if not _available():
        result.audit["reason"] = "hmmlearn_missing"
        return result

    try:
        from hmmlearn.hmm import GaussianHMM

        model = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=n_iter,
            random_state=42,
        )
        # reshape (n, 1) pour un GaussianHMM 1D
        X = returns.reshape(-1, 1)
        model.fit(X)
        hidden = model.predict(X)
        # mean de chaque état
        state_means: Dict[int, float] = {}
        state_vars: Dict[int, float] = {}
        for s in range(n_states):
            idx = np.where(hidden == s)[0]
            if len(idx) > 0:
                state_means[s] = float(np.mean(returns[idx]))
                state_vars[s] = float(np.var(returns[idx]))
            else:
                state_means[s] = 0.0
                state_vars[s] = 0.0

        # État dominant = dernier état observé
        last_state = int(hidden[-1])
        # proba de l'état dominant (fréquence)
        probs = {s: float(np.sum(hidden == s)) / len(hidden)
                 for s in range(n_states)}
        result.state_probs = {f"S{s}": p for s, p in probs.items()}
        result.regime_confidence = round(probs[last_state], 3)

        # Classification du dernier état par mean/variance relative
        all_means = sorted(state_means.values())
        # volatilité relative : variance de l'état vs moyenne globale
        global_var = float(np.var(returns))
        last_var = state_vars.get(last_state, 0.0)
        high_vol = global_var > 0 and (last_var / (global_var + 1e-12)) > 1.5

        mean = state_means[last_state]
        # seuil de tendance : |mean| > 1 sigma / sqrt(n) (t-test simplifié)
        sd = float(np.std(returns))
        threshold = (sd / np.sqrt(len(returns)) + 1e-12) * 1.0
        if high_vol and abs(mean) < threshold:
            result.regime = Regime.VOLATILE
        elif mean > threshold:
            result.regime = Regime.TRENDING_UP
        elif mean < -threshold:
            result.regime = Regime.TRENDING_DOWN
        elif high_vol:
            result.regime = Regime.VOLATILE
        else:
            result.regime = Regime.RANGING
        # NEWS_LOCK : variance extrême (top 5% historique)
        if global_var > 0 and (last_var / (global_var + 1e-12)) > 3.0:
            result.regime = Regime.NEWS_LOCK

        result.audit["reason"] = "ok"
        result.audit["state_means"] = {f"S{s}": round(m, 6)
                                       for s, m in state_means.items()}
        result.audit["last_state"] = last_state
        result.audit["global_var"] = round(global_var, 10)
        result.audit["last_var"] = round(last_var, 10)
        return result
    except Exception as exc:
        log.warning("HMM regime detection failed (R6 fail-open): %s", exc)
        result.audit["reason"] = f"error:{type(exc).__name__}"
        return result


# ─────────────────────────────────────────────────────────────────────
# Changepoint (ruptures PELT)
# ─────────────────────────────────────────────────────────────────────
def detect_change_points(
    closes: List[float],
    *,
    pen: Optional[float] = None,
    min_samples: int = 30,
) -> Tuple[List[int], Dict]:
    """Détecte les ruptures de régime via ruptures (PELT, cost rbf).

    Returns
    -------
    (change_points, audit) — indices de rupture dans la série de returns.
    R6 : données insuffisantes ou lib manquante → ([], {reason:...}).
    """
    if len(closes) < min_samples:
        return [], {"reason": f"insufficient_data:{len(closes)}"}
    try:
        import ruptures as rpt

        returns = _returns_from_closes(closes)
        if len(returns) < min_samples:
            return [], {"reason": f"insufficient_returns:{len(returns)}"}
        algo = rpt.Pelt(model="rbf", min_size=5, jump=1).fit(returns)
        if pen is None:
            pen = len(returns) * 0.5  # heuristique
        bkps = algo.predict(pen=pen)
        # ruptures renvoie les index de fin de segments ; on retire le dernier
        # (= len(returns))
        cps = [int(b) for b in bkps[:-1]]
        return cps, {"method": "pelt_rbf", "pen": pen,
                     "n_change_points": len(cps)}
    except Exception as exc:
        log.warning("Change-point detection failed (R6 fail-open): %s", exc)
        return [], {"reason": f"error:{type(exc).__name__}"}


def compose_regime_signal(
    closes: List[float],
    *,
    symbol: str = "",
    timestamp: str = "",
    n_states: int = 5,
) -> RegimeResult:
    """Compose un régime HMM + changepoints en un RegimeResult unique."""
    result = detect_hmm_regime(
        closes, symbol=symbol, timestamp=timestamp, n_states=n_states)
    cps, audit_cp = detect_change_points(closes)
    result.change_points = cps
    result.audit["change_point_audit"] = audit_cp
    # bonus confiance si un changepoint récent (dans les 5 dernières bougies)
    if cps:
        last_cp = max(cps)
        if len(closes) - 1 - last_cp <= 5:
            result.audit["recent_change_point"] = True
            result.regime_confidence = round(
                min(1.0, result.regime_confidence + 0.1), 3)
    return result


__all__ = [
    "Regime",
    "RegimeResult",
    "detect_hmm_regime",
    "detect_change_points",
    "compose_regime_signal",
    "_returns_from_closes",
    "_available",
]
