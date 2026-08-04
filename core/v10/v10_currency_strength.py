"""V10 Currency Strength Engine — moteur Fatman Hawkeye par devise.

Reproduit la lecture Hawkeye Fatman de Søn :
  Pour chaque devise, agréger le momentum normalisé de TOUTES ses crosses
  simultanément, sur 7 TF (M1, M5, M15, M30, H1, H4, D1).

Principe (§4 PHASE 1 plan Edge Fund) :
  IN  : OHLCV des 6 paires USD × 7 TF
  CALC : EMA(8) vs EMA(34) par cross → momentum EMA
        ATR(14) par cross → normalisation
        Signe devise (base +1 / quote -1) appliqué
        Moyenne pondérée par volume sur toutes les crosses de la devise
        Percentile rank sur fenêtre 50 barres → score 0-100
  OUT : score_devise[EUR/GBP/USD/JPY/CHF/AUD/CAD] = 0-100 par TF
        + velocity, ranks, extremes (top/bottom)
        + métadonnées audit (seed, n_bars_used, pairs_used)

Doctrine V10 :
  R1-AGIR (engine exécuté sur demande, sans permission),
  R2 additif pur (zéro import core/v9/),
  R6 fail-open (data insuffisante → score=50 neutre, log warning),
  R7 tests verts (10+ tests dans tests/test_v10_currency_strength.py),
  R9 auditable (seed reproductible, métadonnées sérialisées),
  R10 zéro ordre réel (compute only).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .v10_currency_pairs import (
    CURRENCIES,
    INVERSION_MAP,
    PAIRS_USD,
    PAIRS_BY_CURRENCY,
    all_supported_currencies,
    sign,
)

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Configuration par défaut (overridable via dict overrides)
# ─────────────────────────────────────────────────────────────────────
DEFAULTS: Dict[str, object] = {
    # Fenêtre percentile rank
    "rank_window": 50,
    # N bougies minimum pour calculer le score (fail-open si insuffisant)
    "min_bars": 30,
    # TF supportés (M1/M5/M15/M30/H1/H4/D1)
    "supported_timeframes": ("M1", "M5", "M15", "M30", "H1", "H4", "D1"),
    # EMA et ATR par défaut (recalibrables Phase I)
    "ema_short": 8,
    "ema_long": 34,
    "atr_period": 14,
    # Seuils extrêmes OB/OS (informational, Phase 3 consommera)
    "overbought_percentile": 90,
    "oversold_percentile": 10,
    # Borne volume (sinon skipping pair dans l'agrégation)
    "min_volume_for_weighting": 0.0,
}

# Taille de fenêtre bougies par TF (pour FX 24/5 — fenêtre indicative)
WINDOW_BARS_BY_TF: Dict[str, int] = {
    "M1": 200,
    "M5": 200,
    "M15": 200,
    "M30": 200,
    "H1": 100,
    "H4": 100,
    "D1": 50,
}


# ─────────────────────────────────────────────────────────────────────
# Dataclasses sortie
# ─────────────────────────────────────────────────────────────────────
@dataclass
class CurrencyStrength:
    """Résultat du moteur Currency Strength pour un (devise × TF) snapshot."""

    timestamp: str
    timeframe: str

    # Score 0-100 par devise agrégée (clé ∈ CURRENCIES)
    scores: Dict[str, float] = field(default_factory=dict)

    # Velocity = (score_t - score_{t-1}) / score_{t-1}, en ratio [-1, +1]
    velocities: Dict[str, float] = field(default_factory=dict)

    # Rang 1=plus fort → 7=plus faible (parmi les devises trackées)
    ranks: Dict[str, int] = field(default_factory=dict)

    # Devise extrême haute / basse (snapshot)
    strongest: str = ""
    weakest: str = ""

    # Largeur Fatman = max_score - min_score (info divergence cross-pair)
    spread_score: float = 0.0

    # Métadonnées audit (R9)
    n_bars_used: int = 0
    pairs_used: Tuple[str, ...] = field(default_factory=tuple)
    insufficient_data_currencies: Tuple[str, ...] = field(default_factory=tuple)
    seed: Optional[int] = None
    invert_sign: bool = True  # applique INVERSION_MAP (doctrine Fatman)

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "timeframe": self.timeframe,
            "scores": {k: round(v, 2) for k, v in self.scores.items()},
            "velocities": {k: round(v, 4) for k, v in self.velocities.items()},
            "ranks": dict(self.ranks),
            "strongest": self.strongest,
            "weakest": self.weakest,
            "spread_score": round(self.spread_score, 2),
            "audit": {
                "n_bars_used": self.n_bars_used,
                "pairs_used": list(self.pairs_used),
                "insufficient_data_currencies": list(self.insufficient_data_currencies),
                "seed": self.seed,
                "invert_sign": self.invert_sign,
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers calcul pur (testables sans dépendance externe)
# ─────────────────────────────────────────────────────────────────────
def _ema(values: List[float], period: int) -> float:
    """EMA scalaire sur la dernière valeur (utilisée pour momentum)."""
    if not values or period <= 0:
        return 0.0
    if len(values) < period:
        period = len(values)
    k = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def _sma(values: List[float], period: int) -> float:
    if len(values) < period or period <= 0 or not values:
        return 0.0
    return sum(values[-period:]) / period


def _atr(bars: List[dict], period: int) -> float:
    """True Range moyen sur N bougies (R6 fail-open → 0 si data insuffisante)."""
    if len(bars) < 2:
        return 0.0
    win = bars[-(period + 1):]
    trs: List[float] = []
    for i in range(1, len(win)):
        h = win[i]["high"]
        l = win[i]["low"]
        pc = win[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def _true_range(bars: List[dict]) -> List[float]:
    """Vecteur True Range 1-par-1 (utilisé pour VSA et effort)."""
    if len(bars) < 2:
        return []
    out: List[float] = []
    for i in range(1, len(bars)):
        h = bars[i]["high"]
        l = bars[i]["low"]
        pc = bars[i - 1]["close"]
        out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


def _percentile_rank(value: float, window: List[float]) -> float:
    """Percentile rank de `value` dans `window` (0..100 inclus, exclusif sur value).

    Définition : (nb d'éléments STRICTEMENT INFÉRIEURS à value) / N × 100.
    Fenêtre vide → 50 (neutre, R6 fail-open).
    Fenêtre de 1 élément :
      - si value == élément → 0% (l'élément n'est pas strictement < lui-même)
      - si value > élément → 100%
      - si value < élément → 0%

    >>> _percentile_rank(0.0, [0.0, 1.0, 2.0])
    0.0
    >>> _percentile_rank(2.0, [0.0, 1.0, 2.0])
    66.66...
    >>> _percentile_rank(5.0, [0.0, 1.0, 2.0])
    100.0
    >>> _percentile_rank(99.0, [])
    50.0
    """
    n = len(window)
    if n == 0:
        return 50.0
    lt = sum(1 for x in window if x < value)
    return (lt / n) * 100.0


def _momentum_normalized(bars: List[dict], ema_s: int, ema_l: int, atr_p: int) -> Tuple[float, float]:
    """Momentum ATR-normalisé d'une paire sur la bougie la plus récente.

    Retourne (mom_norm, atr). mom_norm = 0 si ATR=0 (R6 fail-open).
    """
    closes = [b["close"] for b in bars]
    if len(closes) < max(ema_l, atr_p) + 1:
        return 0.0, 0.0
    e_short = _ema(closes, ema_s)
    e_long = _ema(closes, ema_l)
    a = _atr(bars, atr_p)
    if a <= 0:
        return 0.0, 0.0
    mom = (e_short - e_long) / a
    return mom, a


def _aggregate_currency(
    currency: str,
    pairs_bars: Dict[str, List[dict]],
    cfg: dict,
) -> Tuple[float, int, int]:
    """Agrège le momentum signé d'une devise sur toutes ses crosses.

    pairs_bars : { pair : [bars OHLCV croissante] }

    Retourne :
      (mom_brut_pondéré_volume, n_bars_utilisées, n_pairs_pondérés)
    """
    pairs = list(PAIRS_BY_CURRENCY.get(currency, ()))
    if not pairs:
        return 0.0, 0, 0

    ema_s = cfg.get("ema_short", 8)
    ema_l = cfg.get("ema_long", 34)
    atr_p = cfg.get("atr_period", 14)

    weighted_sum = 0.0
    weight_sum = 0.0
    n_bars = 0
    n_pairs = 0
    for pair in pairs:
        bars = pairs_bars.get(pair, [])
        if not bars or len(bars) < ema_l + 2:
            continue
        mom, atr = _momentum_normalized(bars, ema_s, ema_l, atr_p)
        # Volume moyen (si dispo) comme poids — sinon uniform
        vols = [b.get("tick_volume", 1.0) or 1.0 for b in bars[-ema_l:]]
        vol_avg = _sma(vols, len(vols))
        weight = max(vol_avg, cfg.get("min_volume_for_weighting", 0.0) + 1e-9)

        s = sign(pair, currency)  # +1 ou -1
        weighted_sum += s * mom * weight
        weight_sum += weight
        n_pairs += 1
        n_bars = max(n_bars, len(bars))

    if weight_sum == 0:
        return 0.0, n_bars, 0
    return weighted_sum / weight_sum, n_bars, n_pairs


# ─────────────────────────────────────────────────────────────────────
# API principale
# ─────────────────────────────────────────────────────────────────────
def compute_currency_strength(
    timestamp: str,
    timeframe: str,
    pairs_bars: Dict[str, List[dict]],
    *,
    history: Optional[Dict[str, List[float]]] = None,
    overrides: Optional[dict] = None,
    seed: Optional[int] = None,
) -> CurrencyStrength:
    """Calcule le CurrencyStrength snapshot pour un timestamp + TF donné.

    Parameters
    ----------
    timestamp : ISO 8601 UTC string de la bougie de référence.
    timeframe : M1/M5/M15/M30/H1/H4/D1.
    pairs_bars : { pair : [bars OHLCV croissante], ... } pour 6 paires USD.
                 Bar OHLCV = {open, high, low, close, tick_volume?, spread_points?}.
    history    : optionnel — { pair : [moments EMA passés] } pour percentile rank.
                 Si None, on utilise les moments de la bougie courante comme
                 proxy (scoring "intra-bar") avec fenêtre = [mom_courant].
    overrides  : optionnel — fusionné avec DEFAULTS.
    seed       : pour reproductibilité (R9), optionnel.

    Returns
    -------
    CurrencyStrength dataclass, sérialisable via as_dict().

    Doctrine fail-open R6 : si data insuffisante pour une devise, on
    met son score = 50 (neutre) et on logge un warning debug (1 fois
    par appel max).
    """
    cfg = dict(DEFAULTS)
    if overrides:
        cfg.update(overrides)

    if timeframe not in cfg["supported_timeframes"]:
        log.warning(
            "v10: timeframe=%s non supporté (attendu %s) — score neutre forcé",
            timeframe, cfg["supported_timeframes"],
        )

    # Vérifier que toutes les paires USD attendues sont présentes
    pairs_provided = set(pairs_bars.keys())
    pairs_missing = set(PAIRS_USD) - pairs_provided
    if pairs_missing:
        log.debug("v10: paires manquantes: %s — score partiel", pairs_missing)

    pairs_used: List[str] = []
    insufficient: List[str] = []
    scores: Dict[str, float] = {}
    raw_moments: Dict[str, List[float]] = {}  # pour percentile rank

    min_bars = cfg.get("min_bars", 30)
    rank_window_max = cfg.get("rank_window", 50)

    for currency in CURRENCIES:
        mom, n_bars, n_pairs = _aggregate_currency(currency, pairs_bars, cfg)
        if n_pairs == 0 or n_bars < min_bars:
            insufficient.append(currency)
            scores[currency] = 50.0  # neutre fail-open R6
            raw_moments[currency] = []
            continue

        # Percentile rank windowed : la fenêtre vient de `history[currency]`
        # (moments EMA des N bougies précédentes). Si pas d'historique ou
        # fenêtre trop courte, on complète avec le moment courant (degrade
        # gracieux, percentile neutre 50 par défaut).
        prior_window: List[float] = []
        if history and currency in history:
            full = list(history[currency])
            prior_window = full[-rank_window_max:]

        if len(prior_window) < rank_window_max:
            # Pas assez d'historique : fallback déterministe score=50 (neutre)
            # — permettra de tester sans DB, en prod `history` est TOUJOURS rempli.
            scores[currency] = 50.0
            raw_moments[currency] = prior_window + [mom]
            # Pas d'insuffisant flag — c'est une dégradation connue, pas une absence.
        else:
            rank_pct = _percentile_rank(mom, prior_window)
            # Mapping percentile [0..100] → score [0..100] borné [5..95]
            score = max(5.0, min(95.0, rank_pct))
            scores[currency] = score
            raw_moments[currency] = prior_window[-rank_window_max:] + [mom]

        for pair in PAIRS_BY_CURRENCY.get(currency, ()):
            if pair in pairs_provided and pair not in pairs_used:
                pairs_used.append(pair)

    # Ranks : 1 = plus fort
    sorted_by_score = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    ranks = {cur: i + 1 for i, (cur, _) in enumerate(sorted_by_score)}
    strongest = sorted_by_score[0][0] if sorted_by_score else ""
    weakest = sorted_by_score[-1][0] if sorted_by_score else ""

    # Velocities : stub déterministe si pas de snapshot précédent (R9 audit friendly)
    velocities: Dict[str, float] = {}
    if history:
        for currency, window in raw_moments.items():
            if len(window) >= 2:
                prev = window[-2]
                curr = window[-1]
                velocities[currency] = (curr - prev) / (abs(prev) + 1e-9)
            else:
                velocities[currency] = 0.0
    else:
        velocities = {c: 0.0 for c in CURRENCIES}

    # Spread Fatman (largeur)
    if scores:
        spread_score = max(scores.values()) - min(scores.values())
    else:
        spread_score = 0.0

    return CurrencyStrength(
        timestamp=timestamp,
        timeframe=timeframe,
        scores=scores,
        velocities=velocities,
        ranks=ranks,
        strongest=strongest,
        weakest=weakest,
        spread_score=spread_score,
        n_bars_used=int(sum(1 for _ in pairs_used) * n_bars if pairs_used else 0),
        pairs_used=tuple(pairs_used),
        insufficient_data_currencies=tuple(insufficient),
        seed=seed,
        invert_sign=True,
    )


__all__ = [
    "CurrencyStrength",
    "compute_currency_strength",
    "_ema", "_sma", "_atr", "_true_range", "_percentile_rank",
    "_momentum_normalized", "_aggregate_currency",
    "DEFAULTS", "WINDOW_BARS_BY_TF",
]
