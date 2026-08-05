"""V10 Fatman Editor — formule Fatman éditeur (HERMES_PLAN_V10 ÉTAPE 1).

Implémente la formule reverse-engineerée de l'indicateur éditeur :
  Score_devise = Σ(poids_TF × momentum_TF) / Σ(poids_TF)

Poids par TF :
  M5  = 1.0
  M15 = 1.5
  M30 = 2.0   (ajout critique Phase 22)
  H1  = 3.0

Momentum_TF = (close - close[N]) / close[N] × 100
  où N = période de référence du TF (20 bougies)

Signal Fatman :
  Delta = Score_devise_base - Score_devise_quote
  FORT  : |Delta| ≥ 2.0  → levier max
  MOYEN : 1.0 ≤ |Delta| < 2.0 → levier standard
  AUCUN : |Delta| < 1.0 → abstention

Grille TF Fatman → TF trading :
  M5+M15 → entrée M1, confirmation M5
  M15+M30 → entrée M5, confirmation M15
  M30+H1 → entrée M15, confirmation M30
  H1+H4 → entrée M30, confirmation H1

Doctrine V10 : R1-AGIR, R2 additif pur (0 import core/v9/), R6
fail-open (data insuffisante → score 0.0 neutre), R7 tests verts,
R9 audit sérialisable, R10 zéro ordre réel (compute only).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────
# Constantes Fatman éditeur (HERMES_PLAN_V10)
# ─────────────────────────────────────────────────────────────────────
# Poids par TF (formule reverse-engineerée)
TF_WEIGHTS: Dict[str, float] = {
    "M5": 1.0,
    "M15": 1.5,
    "M30": 2.0,
    "H1": 3.0,
}

# Période de référence du momentum (20 bougies)
MOMENTUM_PERIOD: int = 20

# Seuils de signal Delta
DELTA_FORT: float = 2.0    # |Delta| ≥ 2.0 → levier max
DELTA_MOYEN: float = 1.0   # 1.0 ≤ |Delta| < 2.0 → levier standard

# Devises agrégées (Fatman éditeur — 8 devises)
EDITOR_CURRENCIES: Tuple[str, ...] = (
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
)

# Paires majeures → (base, quote)
EDITOR_PAIRS: Dict[str, Tuple[str, str]] = {
    "EURUSD": ("EUR", "USD"),
    "GBPUSD": ("GBP", "USD"),
    "USDJPY": ("USD", "JPY"),
    "USDCHF": ("USD", "CHF"),
    "AUDUSD": ("AUD", "USD"),
    "USDCAD": ("USD", "CAD"),
    "NZDUSD": ("NZD", "USD"),
}

# Grille TF Fatman → TF entrée/confirmation (plan §Grille)
TRADING_GRID: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("M5", "M15"): ("M1", "M5"),
    ("M15", "M30"): ("M5", "M15"),
    ("M30", "H1"): ("M15", "M30"),
    ("H1", "H4"): ("M30", "H1"),
}


# ─────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────
@dataclass
class EditorMomentum:
    """Momentum d'une paire sur un TF."""
    pair: str
    timeframe: str
    momentum_pct: float  # (close - close[N]) / close[N] × 100


@dataclass
class FatmanEditorResult:
    """Résultat complet du calcul Fatman éditeur."""
    timestamp: str = ""
    # Scores 0-100 par devise (normalisés depuis les raw)
    scores: Dict[str, float] = field(default_factory=dict)
    # Scores bruts (somme pondérée avant normalisation)
    raw_scores: Dict[str, float] = field(default_factory=dict)
    # Delta par paire (base - quote)
    deltas: Dict[str, float] = field(default_factory=dict)
    # Signal par paire : FORT / MOYEN / AUCUN
    signals: Dict[str, str] = field(default_factory=dict)
    # Leverage recommandé par paire
    leverage: Dict[str, int] = field(default_factory=dict)
    # TF utilisés + poids appliqués
    timeframes_used: List[str] = field(default_factory=list)
    # Momentum calculés par (pair, tf)
    momentums: List[Dict] = field(default_factory=list)
    # R9 audit
    n_bars_used: int = 0
    insufficient: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "scores": {k: round(v, 2) for k, v in self.scores.items()},
            "raw_scores": {k: round(v, 4) for k, v in self.raw_scores.items()},
            "deltas": {k: round(v, 3) for k, v in self.deltas.items()},
            "signals": dict(self.signals),
            "leverage": dict(self.leverage),
            "timeframes_used": self.timeframes_used,
            "n_bars_used": self.n_bars_used,
            "insufficient": self.insufficient,
        }


# ─────────────────────────────────────────────────────────────────────
# Calculs
# ─────────────────────────────────────────────────────────────────────
def _momentum(closes: List[float], period: int = MOMENTUM_PERIOD) -> float:
    """Momentum = (close - close[N]) / close[N] × 100. R6 : données courtes → 0.0."""
    if len(closes) <= period:
        return 0.0
    ref = closes[-period - 1]
    if ref == 0.0:
        return 0.0
    return (closes[-1] - ref) / ref * 100.0


def compute_pair_momentum(pair: str, timeframe: str,
                          closes: List[float]) -> EditorMomentum:
    """Momentum d'une paire sur un TF donné (formule éditeur)."""
    return EditorMomentum(
        pair=pair, timeframe=timeframe,
        momentum_pct=round(_momentum(closes), 4),
    )


def compute_fatman_editor(
    pairs_bars: Dict[str, Dict[str, List[float]]],
    *,
    timestamp: str = "",
    weights: Optional[Dict[str, float]] = None,
) -> FatmanEditorResult:
    """Calcule les scores Fatman éditeur (ÉTAPE 1 du plan).

    Args:
        pairs_bars: { pair : { tf : [closes croissantes] } }.
            TF autorisés : M5/M15/M30/H1 (poids définis).
        timestamp: ISO UTC de référence (audit R9).
        weights: surcharge des poids TF (R8 réversible).

    Returns:
        FatmanEditorResult : scores 0-100 par devise, deltas, signaux,
        leverage recommandé, audit.

    R6 fail-open : paire sans données suffisantes → momentum 0.0 ;
    devise sans aucune donnée → score 50.0 (neutre).
    """
    w = dict(TF_WEIGHTS)
    if weights:
        w.update(weights)

    result = FatmanEditorResult(timestamp=timestamp)
    result.timeframes_used = [tf for tf in ("M5", "M15", "M30", "H1")
                              if any(tf in pbs for pbs in pairs_bars.values())]

    # 1. Momentum par (pair, tf)
    raw_by_currency: Dict[str, float] = {c: 0.0 for c in EDITOR_CURRENCIES}
    weight_sum_by_currency: Dict[str, float] = {c: 0.0 for c in EDITOR_CURRENCIES}
    n_bars_used = 0

    for pair, tfs in pairs_bars.items():
        if pair not in EDITOR_PAIRS:
            continue
        base, quote = EDITOR_PAIRS[pair]
        for tf, closes in tfs.items():
            tfw = w.get(tf)
            if tfw is None or not closes:
                continue
            mom = _momentum(closes)
            n_bars_used = max(n_bars_used, len(closes))
            result.momentums.append({
                "pair": pair, "timeframe": tf,
                "momentum_pct": round(mom, 4),
            })
            # Le momentum de la paire contribue aux DEUX devises avec
            # signe : base +1, quote -1 (une hausse EURUSD = EUR fort,
            # USD faible)
            raw_by_currency[base] += tfw * mom
            raw_by_currency[quote] -= tfw * mom
            weight_sum_by_currency[base] += tfw
            weight_sum_by_currency[quote] += tfw

    # 2. Scores pondérés (formule éditeur)
    raw_scores: Dict[str, float] = {}
    for c in EDITOR_CURRENCIES:
        ws = weight_sum_by_currency[c]
        if ws > 0:
            raw_scores[c] = raw_by_currency[c] / ws
        else:
            raw_scores[c] = 0.0
            result.insufficient.append(c)
    result.raw_scores = raw_scores
    result.n_bars_used = n_bars_used

    # 3. Normalisation 0-100 (min-max sur les 8 devises)
    vals = list(raw_scores.values())
    vmin, vmax = min(vals), max(vals)
    if vmax > vmin:
        result.scores = {
            c: round((raw_scores[c] - vmin) / (vmax - vmin) * 100.0, 2)
            for c in EDITOR_CURRENCIES
        }
    else:
        result.scores = {c: 50.0 for c in EDITOR_CURRENCIES}

    # 4. Delta + signal + leverage par paire
    for pair, (base, quote) in EDITOR_PAIRS.items():
        delta = raw_scores[base] - raw_scores[quote]
        result.deltas[pair] = round(delta, 3)
        if abs(delta) >= DELTA_FORT:
            result.signals[pair] = "FORT"
            result.leverage[pair] = 50  # levier max (plan S1)
        elif abs(delta) >= DELTA_MOYEN:
            result.signals[pair] = "MOYEN"
            result.leverage[pair] = 30  # levier standard
        else:
            result.signals[pair] = "AUCUN"
            result.leverage[pair] = 0   # abstention obligatoire

    return result


def get_trading_setup(fatman_tf_1: str, fatman_tf_2: str) -> Optional[Tuple[str, str]]:
    """Grille TF Fatman → (TF entrée, TF confirmation). None si hors grille."""
    return TRADING_GRID.get((fatman_tf_1.upper(), fatman_tf_2.upper()))


# ─────────────────────────────────────────────────────────────────────
# __all__
# ─────────────────────────────────────────────────────────────────────
__all__ = [
    "TF_WEIGHTS",
    "MOMENTUM_PERIOD",
    "DELTA_FORT",
    "DELTA_MOYEN",
    "EDITOR_CURRENCIES",
    "EDITOR_PAIRS",
    "TRADING_GRID",
    "EditorMomentum",
    "FatmanEditorResult",
    "compute_pair_momentum",
    "compute_fatman_editor",
    "get_trading_setup",
]
