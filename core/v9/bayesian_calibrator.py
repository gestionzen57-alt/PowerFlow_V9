"""bayesian_calibrator.py — Calibration bayésienne formelle V9 (Axe 1.1 / J1).

Transforme les observations WIN/LOSS en distributions **Beta(α,β)** (modèle
Beta-Binomial conjugué, prior uniforme Beta(1,1)) pour :

1. Estimer P(WR) postérieure par contexte (principle × symbol × tf × session × regime).
2. Produire des intervalles crédibles 95 %.
3. Tester si un edge est réel (H0 : WR ≤ seuil) vs le bruit.
4. Sizer Kelly fractionnel avec garde-fous (floor / cap / kill si n<20).

**Dépendances** : stdlib uniquement (`math`). `scipy.stats.beta` est utilisé
comme accélérateur **si disponible** (import optionnel), sinon on retombe sur
une implémentation pure de la fonction beta incomplète régularisée (continued
fraction, Numerical Recipes — précision ~1e-12). Le module fonctionne donc à
l'identique avec ou sans scipy (R6 défensif, garde-fou « scipy indisponible »).

Doctrine : R2 (additif), R6 (défensif — ne lève jamais côté lecture), R18
(code pur, zéro LLM), R25' (OFF par défaut, kill switch V9_BAYESIAN_CALIBRATOR_ENABLED).
"""
from __future__ import annotations

import logging
import math
import os
from pathlib import Path

from core.v9._bayesian_db import (
    ContextKey,
    read_confidence_outcomes,
    read_context_aggregates,
)

logger = logging.getLogger("v9.bayesian_calibrator")

# Accélérateur scipy — détecté mais **désactivé par défaut**. Le calcul par
# défaut est l'implémentation pure (beta incomplète régularisée ci-dessous),
# accurate ~1e-12 et sans dépendance. Rationnel (R6) : sur cet hôte, scipy
# s'appuie sur OpenBLAS qui peut échouer par OOM (`abort()` non rattrapable)
# → routing scipy risqué en production. On l'active seulement sur opt-in
# explicite `V9_BAYESIAN_USE_SCIPY=1` (bench / validation croisée).
try:  # pragma: no cover - dépend de l'environnement
    from scipy.stats import beta as _scipy_beta  # type: ignore

    _HAS_SCIPY = True
except Exception:  # pragma: no cover
    _scipy_beta = None  # type: ignore
    _HAS_SCIPY = False

_USE_SCIPY = _HAS_SCIPY and os.environ.get("V9_BAYESIAN_USE_SCIPY") == "1"


# ── Fonction beta incomplète régularisée (fallback pur, sans scipy) ──────
def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction pour la beta incomplète (Numerical Recipes §6.4)."""
    MAXIT = 300
    EPS = 3.0e-16
    FPMIN = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Beta incomplète régularisée I_x(a,b) == CDF de Beta(a,b) en x."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(ln_beta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _beta_cdf(x: float, a: float, b: float) -> float:
    """CDF de Beta(a,b). Pure par défaut ; scipy sur opt-in (_USE_SCIPY)."""
    if _USE_SCIPY:
        return float(_scipy_beta.cdf(x, a, b))
    return _betai(a, b, x)


def _beta_ppf(q: float, a: float, b: float) -> float:
    """Quantile (inverse CDF) de Beta(a,b). Pure par défaut (bisection monotone
    sur la CDF, ~100 itérations → précision ~1e-15) ; scipy sur opt-in."""
    if _USE_SCIPY:
        return float(_scipy_beta.ppf(q, a, b))
    if q <= 0.0:
        return 0.0
    if q >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if _betai(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


class BetaPosterior:
    """Distribution Beta(α, β) pour un contexte de décision.

    α = PRIOR_ALPHA + wins, β = PRIOR_BETA + losses (prior uniforme Beta(1,1)).
    `n` = nombre d'observations réelles (wins + losses), indépendant du prior —
    sert aux garde-fous de taille d'échantillon (kill si n<20).
    """

    __slots__ = ("alpha", "beta", "n")

    def __init__(self, alpha: float, beta: float, n: int) -> None:
        if alpha <= 0.0 or beta <= 0.0:
            raise ValueError(f"paramètres Beta invalides: alpha={alpha}, beta={beta}")
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.n = int(n)

    @property
    def mean(self) -> float:
        """E[WR] = α / (α + β)."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        """Var[WR] = α·β / ((α+β)²·(α+β+1)). Décroît en 1/n."""
        s = self.alpha + self.beta
        return (self.alpha * self.beta) / (s * s * (s + 1.0))

    def credible_interval_95(self) -> tuple[float, float]:
        """Intervalle crédible 95 % (quantiles 2.5 % et 97.5 %)."""
        return (_beta_ppf(0.025, self.alpha, self.beta),
                _beta_ppf(0.975, self.alpha, self.beta))

    def prob_above(self, threshold: float = 0.5) -> float:
        """P(WR > threshold) = 1 − CDF_Beta(threshold)."""
        return 1.0 - _beta_cdf(threshold, self.alpha, self.beta)

    def __repr__(self) -> str:  # pragma: no cover - confort debug
        return (f"BetaPosterior(alpha={self.alpha:.1f}, beta={self.beta:.1f}, "
                f"n={self.n}, mean={self.mean:.3f})")


class BayesianCalibrator:
    """Calibration bayésienne des contextes de décision (lecture DB seule)."""

    PRIOR_ALPHA = 1.0  # Prior uniforme Beta(1,1) — aucune préférence a priori
    PRIOR_BETA = 1.0

    #: Seuil minimal d'observations pour sizer (kill switch statistique).
    MIN_N_KELLY = 20
    #: Confiance postérieure minimale P(WR>0.5) pour confirmer un edge sizable.
    MIN_PROB_EDGE = 0.6

    def __init__(self, db_path: Path | str, window_days: int = 30) -> None:
        self.db_path = Path(db_path)
        self.window_days = window_days
        self._cache: dict[ContextKey, BetaPosterior] = {}
        self._aggregates_cache: dict[ContextKey, dict[str, int]] | None = None

    def _aggregates(self) -> dict[ContextKey, dict[str, int]]:
        if self._aggregates_cache is None:
            self._aggregates_cache = read_context_aggregates(
                self.db_path, min_n=1, window_days=self.window_days
            )
        return self._aggregates_cache

    def _posterior_from_counts(self, wins: int, losses: int) -> BetaPosterior:
        return BetaPosterior(
            self.PRIOR_ALPHA + wins, self.PRIOR_BETA + losses, wins + losses
        )

    def fit_context(self, context_key: ContextKey) -> BetaPosterior:
        """Lit la DB (agrégée + cache) et calcule Beta(α,β) pour un contexte.

        Contexte inconnu → posterior du prior seul Beta(1,1), n=0 (R6 : jamais
        d'exception ; l'appelant décide via `.n` s'il fait confiance)."""
        key = tuple(context_key)  # type: ignore[assignment]
        if key in self._cache:
            return self._cache[key]
        counts = self._aggregates().get(key, {"wins": 0, "losses": 0, "n": 0})
        posterior = self._posterior_from_counts(counts["wins"], counts["losses"])
        self._cache[key] = posterior
        return posterior

    def fit_all_contexts(self, min_n: int = 20) -> dict[ContextKey, BetaPosterior]:
        """Posteriors pour tous les contextes avec n ≥ min_n."""
        out: dict[ContextKey, BetaPosterior] = {}
        for key, counts in self._aggregates().items():
            if counts["n"] >= min_n:
                out[key] = self._posterior_from_counts(counts["wins"], counts["losses"])
        return out

    def is_edge_real(
        self, posterior: BetaPosterior, threshold: float = 0.5, conf: float = 0.95
    ) -> tuple[bool, float]:
        """Test d'edge réel — H0 : WR ≤ threshold.

        Returns:
            `(is_edge, p_value)` où
            - `is_edge = posterior.prob_above(threshold) >= conf`
            - `p_value = P(WR ≤ threshold) = CDF_Beta(threshold)` (masse
              postérieure sous H0 ; petit = edge crédible).
        """
        p_value = _beta_cdf(threshold, posterior.alpha, posterior.beta)
        is_edge = (1.0 - p_value) >= conf
        return is_edge, p_value

    def kelly_fraction(
        self,
        posterior: BetaPosterior,
        rr: float = 1.0,
        fraction: float = 0.25,
        floor: float = 0.3,
        cap: float = 2.0,
    ) -> float | None:
        """Sizing Kelly fractionnel → **multiplicateur de taille** borné.

        Kelly complet : `f_full = (p·b − q) / b` avec `p = posterior.mean`,
        `q = 1−p`, `b = rr` (reward:risk). Le multiplicateur renvoyé est
        `f_full / fraction` borné à `[floor, cap]` : `fraction` est la
        référence de Kelly-complet cartographiée sur 1.0× (fractional Kelly
        « inversé » — un edge égal à `fraction` de Kelly complet = taille de
        base). Comme `f_full < 1` toujours, borner le Kelly brut par un cap 2.0
        n'aurait aucun sens ; le multiplicateur, lui, peut légitimement
        dépasser 1.0 (d'où cap 2.0 / floor 0.3). Divergence assumée vs la
        formule littérale de la spec — cf. DECISIONS_LOG §J1.

        Garde-fous (R6) :
            - `n < MIN_N_KELLY` (20)                → None (échantillon trop court)
            - `prob_above(0.5) < MIN_PROB_EDGE` (0.6) → None (edge non confirmé)
            - `f_full ≤ 0` (pas d'edge / rr invalide) → None
        """
        if posterior.n < self.MIN_N_KELLY:
            return None
        if posterior.prob_above(0.5) < self.MIN_PROB_EDGE:
            return None
        if rr <= 0.0:
            return None
        p = posterior.mean
        q = 1.0 - p
        f_full = (p * rr - q) / rr
        if f_full <= 0.0:
            return None
        if fraction <= 0.0:
            return None
        multiplier = f_full / fraction
        return max(floor, min(cap, multiplier))


class BrierScorer:
    """Calibration plot + Brier score sur historique de décisions."""

    @staticmethod
    def brier_score(predictions: list[float], outcomes: list[int]) -> float:
        """Brier = mean((p − y)²). 0 = parfait, 0.25 = aléatoire (p≡0.5)."""
        if not predictions:
            return float("nan")
        if len(predictions) != len(outcomes):
            raise ValueError("predictions et outcomes de longueurs différentes")
        return sum((p - y) ** 2 for p, y in zip(predictions, outcomes)) / len(predictions)

    @staticmethod
    def reliability_table(
        predictions: list[float], outcomes: list[int], n_bins: int = 10
    ) -> list[dict]:
        """Table de fiabilité par bin de probabilité prédite (calibration plot).

        Retourne **toujours** `n_bins` entrées (bins vides inclus, count=0),
        pour un tracé 1:1 régulier. Chaque entrée :
        `{bin_index, bin_lower, bin_upper, count, mean_pred, mean_outcome}`.
        Un bin bien calibré vérifie `mean_pred ≈ mean_outcome`.
        """
        if n_bins <= 0:
            raise ValueError("n_bins doit être > 0")
        table: list[dict] = []
        for i in range(n_bins):
            lower = i / n_bins
            upper = (i + 1) / n_bins
            table.append({
                "bin_index": i,
                "bin_lower": lower,
                "bin_upper": upper,
                "count": 0,
                "mean_pred": None,
                "mean_outcome": None,
                "_sum_pred": 0.0,
                "_sum_out": 0.0,
            })
        for p, y in zip(predictions, outcomes):
            pc = max(0.0, min(1.0, p))
            idx = min(n_bins - 1, int(pc * n_bins))  # borne haute 1.0 → dernier bin
            b = table[idx]
            b["count"] += 1
            b["_sum_pred"] += pc
            b["_sum_out"] += y
        for b in table:
            if b["count"]:
                b["mean_pred"] = b["_sum_pred"] / b["count"]
                b["mean_outcome"] = b["_sum_out"] / b["count"]
            del b["_sum_pred"]
            del b["_sum_out"]
        return table

    @staticmethod
    def platt_scale(
        raw_confidences: list[float], outcomes: list[int],
        iters: int = 500, lr: float = 0.1,
    ) -> tuple[float, float]:
        """Platt scaling : ajuste `sigmoid(A·x + B)` (régression logistique 1-D)
        sur l'historique, par descente de gradient (stdlib pure, sans scipy/sklearn).

        Retourne `(A, B)` pour transformer une confiance brute `x` en
        probabilité calibrée `1 / (1 + exp(-(A·x + B)))`. `A > 0` indique que
        la confiance brute est positivement corrélée au gain observé.
        """
        if not raw_confidences or len(raw_confidences) != len(outcomes):
            return 1.0, 0.0
        a, b = 1.0, 0.0
        n = len(raw_confidences)
        for _ in range(iters):
            grad_a = 0.0
            grad_b = 0.0
            for x, y in zip(raw_confidences, outcomes):
                z = a * x + b
                # sigmoïde numériquement stable
                if z >= 0:
                    pred = 1.0 / (1.0 + math.exp(-z))
                else:
                    ez = math.exp(z)
                    pred = ez / (1.0 + ez)
                err = pred - y
                grad_a += err * x
                grad_b += err
            a -= lr * grad_a / n
            b -= lr * grad_b / n
        return a, b

    @staticmethod
    def apply_platt(x: float, a: float, b: float) -> float:
        """Applique le Platt scaling ajusté : `sigmoid(A·x + B)`."""
        z = a * x + b
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        ez = math.exp(z)
        return ez / (1.0 + ez)
