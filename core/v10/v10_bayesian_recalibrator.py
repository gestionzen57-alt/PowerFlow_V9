"""
V10 Bayesian Recalibrator — CYCLE 9 PATCH (09/08/2026)

CYCLE 9 — patches additifs en tête (R2 — zéro import core/v9/) :

  BAYES-C9-FIX1 — apply_thresholds : KeyError "_global" manquante
    Si thresholds ne contient pas "_global" ET pas la clé pair
    → utiliser valeurs C9 par défaut au lieu de lever KeyError.
    context_score_min=45, anta_score_min=20, aligned_count_min=1

  BAYES-C9-FIX2 — apply_thresholds : retourner True (fail-open) si exception
    try/except global dans apply_thresholds → return True + log.debug (R6)

  BAYES-C9-OPT1 — apply_thresholds session-aware
    Param optionnel session="LONDON" dans apply_thresholds_c9().
    LONDON/NY=45, OVERLAP=42, TOKYO=55, SYDNEY=55, OFF=60

  BAYES-C9-OPT2 — DEFAULT_THRESHOLDS mis à jour C9
    context_score_min=45 (était 60), aligned_count_min=1 (était 2)

Note : Le code original Bayesian reste inchangé en dessous.
Doctrine : R2 additif, R6 fail-open, R9 audit, R10 compute-only.
"""
from __future__ import annotations

import logging
import math
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
#  C9 — DEFAULT_THRESHOLDS mis à jour (BAYES-C9-OPT2)
# ══════════════════════════════════════════════════════════════════════════

DEFAULT_THRESHOLDS: Dict[str, Any] = {
    "_global": {
        "context_score_min":  45.0,   # C9: abaissé de 60 → 45
        "anta_score_min":     20.0,
        "aligned_count_min":  1,       # C9: abaissé de 2 → 1
        "min_confidence":     0.40,
    },
    "A1": {"context_score_min": 55.0, "anta_score_min": 15.0, "aligned_count_min": 1},
    "A2": {"context_score_min": 45.0, "anta_score_min": 20.0, "aligned_count_min": 1},
    "A3": {"context_score_min": 38.0, "anta_score_min": 25.0, "aligned_count_min": 1},
}

# BAYES-C9-OPT1 : seuils ctx par session
_SESSION_CTX_MIN: Dict[str, float] = {
    "LONDON":  45.0,
    "NY":      45.0,
    "OVERLAP": 42.0,
    "TOKYO":   55.0,
    "SYDNEY":  55.0,
    "OFF":     60.0,
    "UNKNOWN": 45.0,
}


def _get_ctx_min_for_session(session: Optional[str], base_min: float = 45.0) -> float:
    """BAYES-C9-OPT1 : retourne le seuil ctx adapté à la session."""
    if not session:
        return base_min
    return _SESSION_CTX_MIN.get(str(session).upper(), base_min)


def apply_thresholds_c9(
    score_context: float,
    score_anta: float,
    aligned_count: int,
    *,
    thresholds: Optional[Dict] = None,
    signal_level: str = "A3",
    session: Optional[str] = None,
) -> bool:
    """
    BAYES-C9-FIX1+FIX2+OPT1+OPT2 : évaluation seuils robuste et session-aware.

    Retourne True si le signal passe les seuils (peut entrer), False sinon.
    Fail-open : toute exception → True (R6).
    """
    try:
        th = thresholds or DEFAULT_THRESHOLDS

        # BAYES-C9-FIX1 : résolution sécurisée des seuils
        # Priorité : clé pair/level → _global → hardcoded C9
        base = th.get("_global", {})
        level_th = th.get(signal_level, {})

        # context_score_min : session-aware (BAYES-C9-OPT1)
        base_ctx = float(
            level_th.get("context_score_min",
            base.get("context_score_min", 45.0))
        )
        ctx_min = _get_ctx_min_for_session(session, base_ctx)

        anta_min = float(
            level_th.get("anta_score_min",
            base.get("anta_score_min", 20.0))
        )
        aligned_min = int(
            level_th.get("aligned_count_min",
            base.get("aligned_count_min", 1))
        )

        passes = (
            score_context >= ctx_min and
            score_anta    >= anta_min and
            aligned_count >= aligned_min
        )
        log.debug(
            "[BAYES-C9] level=%s session=%s ctx=%.1f/%.1f anta=%.1f/%.1f align=%d/%d → %s",
            signal_level, session or "NONE",
            score_context, ctx_min, score_anta, anta_min,
            aligned_count, aligned_min,
            "PASS" if passes else "HOLD",
        )
        return passes

    except Exception as exc:
        # BAYES-C9-FIX2 : fail-open
        log.debug("[BAYES-C9] apply_thresholds_c9 fail-open (R6): %s", exc)
        return True


# ══════════════════════════════════════════════════════════════════════════
#  CODE ORIGINAL BAYESIAN RECALIBRATOR (conservé intégralement)
# ══════════════════════════════════════════════════════════════════════════

_DB_DEFAULT = Path("data") / "powerflow_v10.db"


@dataclass
class BayesianPrior:
    """Prior Beta(alpha, beta) pour une paire/TF/level."""
    alpha: float = 1.0
    beta:  float = 1.0
    n:     int   = 0
    last_updated: float = field(default_factory=time.time)

    def update(self, reward: float) -> None:
        self.alpha       += max(0.0, reward)
        self.beta        += max(0.0, 1.0 - reward)
        self.n           += 1
        self.last_updated = time.time()

    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def as_dict(self) -> Dict:
        return {
            "alpha": round(self.alpha, 4),
            "beta":  round(self.beta,  4),
            "n":     self.n,
            "mean":  round(self.mean(), 4),
        }


@dataclass
class RecalibratorResult:
    symbol:         str  = ""
    timeframe:      str  = ""
    signal_level:   str  = "A3"
    prior_mean:     float = 0.5
    posterior_mean: float = 0.5
    n_updates:      int   = 0
    context_score:  float = 0.0
    anta_score:     float = 0.0
    aligned_count:  int   = 0
    passes:         bool  = False
    audit:          Dict  = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "symbol":         self.symbol,
            "timeframe":      self.timeframe,
            "signal_level":   self.signal_level,
            "prior_mean":     round(self.prior_mean, 4),
            "posterior_mean": round(self.posterior_mean, 4),
            "n_updates":      self.n_updates,
            "context_score":  round(self.context_score, 2),
            "anta_score":     round(self.anta_score, 2),
            "aligned_count":  self.aligned_count,
            "passes":         self.passes,
            "audit":          dict(self.audit),
        }


class BayesianRecalibrator:
    """
    Recalibrateur Bayésien par paire/TF/level.

    Maintient un prior Beta(α, β) mis à jour par chaque outcome.
    Interface : evaluate() + update() + apply_thresholds() + load/save.
    C9 : apply_thresholds() délègue à apply_thresholds_c9() (fail-open).
    """

    def __init__(
        self,
        db_path=None,
        symbol: str = "EURUSD",
        timeframe: str = "M15",
        forgetting_factor: float = 0.99,
    ):
        self.db_path          = str(db_path or _DB_DEFAULT)
        self.symbol           = symbol
        self.timeframe        = timeframe
        self.forgetting_factor = forgetting_factor
        self.priors: Dict[str, BayesianPrior] = {}
        self._load_state()

    def _key(self, signal_level: str) -> str:
        return f"{self.symbol}|{self.timeframe}|{signal_level}"

    def _get_prior(self, signal_level: str) -> BayesianPrior:
        k = self._key(signal_level)
        if k not in self.priors:
            self.priors[k] = BayesianPrior()
        return self.priors[k]

    def evaluate(
        self,
        signal_level: str = "A3",
        context_score: float = 50.0,
        anta_score: float = 25.0,
        aligned_count: int = 1,
        session: Optional[str] = None,
    ) -> RecalibratorResult:
        """Évalue si le signal passe les seuils Bayésiens C9."""
        prior = self._get_prior(signal_level)
        result = RecalibratorResult(
            symbol=self.symbol, timeframe=self.timeframe,
            signal_level=signal_level,
            prior_mean=prior.mean(), posterior_mean=prior.mean(),
            n_updates=prior.n,
            context_score=context_score,
            anta_score=anta_score,
            aligned_count=aligned_count,
        )
        # C9 : délègue à apply_thresholds_c9 (fail-open, session-aware)
        result.passes = apply_thresholds_c9(
            context_score, anta_score, aligned_count,
            thresholds=DEFAULT_THRESHOLDS,
            signal_level=signal_level,
            session=session,
        )
        result.audit = {
            "prior": prior.as_dict(),
            "session": session or "NONE",
            "c9_thresholds": True,
        }
        return result

    def update(self, signal_level: str, reward: float) -> None:
        """Met à jour le prior après un outcome."""
        try:
            prior = self._get_prior(signal_level)
            # forgetting : shrink vers (1,1)
            prior.alpha = 1.0 + (prior.alpha - 1.0) * self.forgetting_factor
            prior.beta  = 1.0 + (prior.beta  - 1.0) * self.forgetting_factor
            prior.update(max(0.0, min(1.0, reward)))
            self._save_state()
        except Exception as exc:
            log.warning("[BAYES] update fail-open (R6): %s", exc)

    def apply_thresholds(
        self,
        score_context: float,
        score_anta: float,
        aligned_count: int,
        thresholds: Optional[Dict] = None,
        signal_level: str = "A3",
        session: Optional[str] = None,
    ) -> bool:
        """BAYES-C9 : délègue à apply_thresholds_c9 (fail-open, session-aware)."""
        return apply_thresholds_c9(
            score_context, score_anta, aligned_count,
            thresholds=thresholds or DEFAULT_THRESHOLDS,
            signal_level=signal_level,
            session=session,
        )

    def as_dict(self) -> Dict:
        return {
            "symbol": self.symbol, "timeframe": self.timeframe,
            "priors": {k: v.as_dict() for k, v in self.priors.items()},
        }

    # ── persistence ──────────────────────────────────────────────────────
    def _load_state(self) -> None:
        try:
            con = sqlite3.connect(self.db_path, timeout=5)
            rows = con.execute(
                "SELECT state_key, alpha, beta, n FROM bayesian_priors "
                "WHERE symbol=? AND timeframe=? ORDER BY saved_at DESC",
                (self.symbol, self.timeframe),
            ).fetchall()
            con.close()
            for key, alpha, beta, n in rows:
                self.priors[key] = BayesianPrior(
                    alpha=float(alpha), beta=float(beta), n=int(n)
                )
        except Exception as exc:
            log.debug("[BAYES] _load_state fail (no state yet): %s", exc)

    def _save_state(self) -> None:
        try:
            con = sqlite3.connect(self.db_path, timeout=5)
            con.execute("""
                CREATE TABLE IF NOT EXISTS bayesian_priors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, timeframe TEXT, state_key TEXT,
                    alpha REAL, beta REAL, n INTEGER,
                    saved_at TEXT
                )
            """)
            ts = __import__('datetime').datetime.utcnow().isoformat()
            for key, prior in self.priors.items():
                con.execute(
                    "INSERT INTO bayesian_priors "
                    "(symbol,timeframe,state_key,alpha,beta,n,saved_at) VALUES (?,?,?,?,?,?,?)",
                    (self.symbol, self.timeframe, key,
                     prior.alpha, prior.beta, prior.n, ts),
                )
            con.commit()
            con.close()
        except Exception as exc:
            log.debug("[BAYES] _save_state fail: %s", exc)


__all__ = [
    "DEFAULT_THRESHOLDS", "BayesianPrior", "RecalibratorResult",
    "BayesianRecalibrator", "apply_thresholds_c9", "_get_ctx_min_for_session",
]
