"""v9_predictive_engine.py — Moteur de prédiction Markov + Retournement (Phase E, Doctrine R33).

**Pourquoi ce module existe** :
- Le système V9 décrit le marché en haute définition (forces, scènes,
  comportements) mais **ne prédit pas la phase suivante**. Un trader
  senior veut savoir : « je suis en culmination depuis 30 bougies, est-ce
  que ça va durer ou basculer ? ».
- Ce module répond à cette question par une chaîne markovienne
  empirique sur l'historique résolu + un indicateur de **risque de
  retournement** basé sur la durée écoulée dans la phase + le contexte.

**Volet mathématique** :
1. **Markov phase T-1 → T** : pour chaque cellule
   `(symbol, timeframe, regime_type)` on a une matrice 4×4 des
   transitions observées depuis la DB `v9_cycle_memory.db` (persistée
   par `update_transition()`).
2. **Retournement risk** ∈ [0, 1] :
   `risk = sigmoid((duree_phase / duree_moyenne) · weight_duree
                  + vol_weight · (1 si vol=HIGH)
                  + divergence_penalty)`
   → P(phase_T+1 ≠ phase_T).
3. **Magnitude attendue** : on n'utilise que la magnitude binaire
   (`is_win`) — l'audit 2026-07-18 confirme que `resolution_pips` est
   capé à 9.5 (TP fixe), donc inutilisable comme label continu. On
   renvoie donc un `p_win` directement (via `v9_bayesian_predictor`).
4. **Confidence** ∈ [0, 1] : f(n_transitions observées, fraîcheur).

**Volet doctrinal** :
- R2 additif (clé `predictive_*`, ne mute pas `signal_generator`)
- R6 défensif (try/except + fallback conservateur)
- R7 testable
- R8 ne touche pas la DB live
- R18 code pur (zéro LLM, math stdlib)
- R33 doctrine du **Système Prédictif**

**Activation** : `V9_PREDICTIVE_ENGINE_ENABLED=1` (défaut ON, motion CEO
2026-07-18 « APPLY direct »).
"""
from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from core.v9.v9_cycle_memory import (
    DEFAULT_DB_PATH as CYCLE_MEMORY_DB_PATH,
    TransitionPattern,
    VALID_PHASES,
    cycle_memory_enabled,
    get_transition,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ const

# Kill switch.
PREDICTIVE_ENABLED_ENV = "V9_PREDICTIVE_ENGINE_ENABLED"

# Phases alignées.
VALID_REGIMES = ("NEUTRE", "RETOUR_EQUILIBRE", "EXTENSION", "PALIER", "CASSURE", "REJET")

# Paramètres retournement risk.
RET_WEIGHT_DURATION = 1.5         # poids de la durée dans le retournement
RET_WEIGHT_VOL_HIGH = 0.20        # bonus retournement si vol HIGH
RET_WEIGHT_VOL_LOW = -0.10        # malus retournement si vol LOW (stabilité)
RET_WEIGHT_DIVERGENCE = 0.30      # bonus si divergence MTF détectée

# Seuils magnitude (binaire).
DEFAULT_TP = 10.0
DEFAULT_SL = 15.0
MIN_TRADES_FOR_TRANSITION = 10   # < ce seuil → confidence = 0 (fallback)


# ------------------------------------------------------------------ dataclasses


@dataclass(frozen=True)
class PredictiveContext:
    """Contexte d'entrée pour la prédiction."""
    symbol: str
    timeframe: str
    regime_type: str
    phase: str
    vol_atr_pips: float | None = None
    duration_bars: float | None = None      # durée écoulée dans la phase actuelle
    mtf_divergence: bool = False            # divergence MTF détectée ?


@dataclass(frozen=True)
class Prediction:
    """Prédiction du moteur prédictif."""
    phase_predicted: str                  # phase T+1 la plus probable
    phase_distribution: dict[str, float]  # P(phase_T+1 | phase_T, ...) sur les 4 phases
    p_no_change: float                    # P(phase_T+1 == phase_T)
    p_reversal: float                     # P(phase_T+1 ≠ phase_T)
    reversal_risk: float                  # [0, 1] ajusté par contexte (durée, vol, div)
    reversal_window_bars: int             # estimation bougies avant retournement
    p_win_given_phase: float | None       # P(is_win | phase_T+1) via cycle memory
    confidence: float                     # [0, 1] qualité du pattern
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ kill switch


def predictive_engine_enabled() -> bool:
    """Kill switch — défaut ON (motion CEO 2026-07-18)."""
    val = os.environ.get(PREDICTIVE_ENABLED_ENV, "1")
    return val == "1"


# ------------------------------------------------------------------ helpers


def _bucket_vol_atr(vol_atr_pips: float | None) -> str:
    """Aligné sur v9_cycle_memory."""
    if vol_atr_pips is None:
        return "UNKNOWN"
    try:
        v = float(vol_atr_pips)
    except (TypeError, ValueError):
        return "UNKNOWN"
    if v < 0:
        return "UNKNOWN"
    if v <= 2.0:
        return "LOW"
    if v <= 6.0:
        return "MEDIUM"
    return "HIGH"


def _sigmoid(x: float) -> float:
    """Sigmoid stable numériquement."""
    if x >= 0:
        ex = math.exp(-x)
        return 1.0 / (1.0 + ex)
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _expected_phase_duration(context: PredictiveContext,
                              cycle_db: Path | None) -> float | None:
    """Récupère la durée moyenne d'une phase depuis cycle_memory (pour le
    calcul du retournement risk par durée écoulée).

    Ne dépend PAS du kill switch V9_CYCLE_MEMORY_ENABLED — le moteur
    prédictif est un consumer de cycle memory, pas un sous-système.
    """
    if cycle_db is None or not cycle_db.exists():
        return None
    try:
        from core.v9.v9_cycle_memory import recall as cycle_recall
        cp = cycle_recall(
            symbol=context.symbol,
            timeframe=context.timeframe,
            regime_type=context.regime_type,
            phase=context.phase,
            vol_atr_pips=context.vol_atr_pips,
            db_path=cycle_db,
        )
        if cp is not None and cp.is_actionable():
            return cp.mean_duration_bars
        return None
    except Exception as e:
        logger.debug("predictive: cycle_memory recall failed: %s", e)
        return None


# ------------------------------------------------------------------ core


def predict_phase_transition(context: PredictiveContext,
                              cycle_db: Path | None = None) -> Prediction:
    """Prédit la distribution de phase T+1 sachant la phase T + contexte.

    Args :
        context : PredictiveContext (symbol, timeframe, regime, phase,
            vol_atr, durée écoulée, divergence MTF).
        cycle_db : path vers la DB cycle memory (défaut : DEFAULT).

    Returns :
        Prediction avec distribution, probas, et risque de retournement.
    """
    if not predictive_engine_enabled():
        return _fallback_prediction(context, "disabled_kill_switch")

    # Validation contexte (R6 défensif)
    if context.phase not in VALID_PHASES:
        return _fallback_prediction(context, f"invalid_phase:{context.phase}")
    if context.regime_type not in VALID_REGIMES:
        return _fallback_prediction(context, f"invalid_regime:{context.regime_type}")

    if cycle_db is None:
        cycle_db = CYCLE_MEMORY_DB_PATH

    # 1. Lookup transition markov (ne dépend PAS du kill switch
    # V9_CYCLE_MEMORY_ENABLED — le moteur prédictif est un consumer de
    # cycle memory, pas un sous-système du cycle memory).
    transition: TransitionPattern | None = None
    if cycle_db is not None and cycle_db.exists():
        try:
            transition = get_transition(
                from_phase=context.phase,
                symbol=context.symbol,
                timeframe=context.timeframe,
                regime_type=context.regime_type,
                db_path=cycle_db,
            )
        except Exception as e:
            logger.warning("predictive: get_transition failed: %s", e)
            transition = None

    if transition is None:
        return _fallback_prediction(context, "no_transition_data")

    # 2. Distribution et phase la plus probable
    phase_distribution = dict(transition.distribution)
    # Compléter avec phases manquantes (probabilité 0)
    for p in VALID_PHASES:
        if p not in phase_distribution:
            phase_distribution[p] = 0.0
    # Renormaliser pour être safe (somme = 1.0)
    total = sum(phase_distribution.values())
    if total > 0:
        phase_distribution = {k: v / total for k, v in phase_distribution.items()}

    phase_predicted = transition.most_likely_next
    p_no_change = phase_distribution.get(context.phase, 0.0)
    p_reversal = 1.0 - p_no_change

    # 3. Retournement risk ajusté par contexte
    reversal_risk = p_reversal  # base = markov
    risk_factors: list[str] = [f"base_markov={p_reversal:.3f}"]

    # Facteur durée : si on est en phase depuis longtemps vs moyenne
    mean_duration = _expected_phase_duration(context, cycle_db)
    if mean_duration is not None and context.duration_bars is not None:
        try:
            duration_ratio = float(context.duration_bars) / max(1.0, mean_duration)
            # Si duration_ratio > 1, on est "en retard" → plus de chance de basculer
            # duration_factor ∈ [0, 1] : 0 = rien à signaler, 1 = bascule imminente
            duration_factor = _sigmoid(
                RET_WEIGHT_DURATION * (duration_ratio - 1.0)
            )
            # Combinaison multiplicative modérée : si markov dit 50% reversal
            # et durée normale (factor=0.21) → risk ≈ 1 - 0.5 * 0.79 = 0.395.
            # Si durée 2x (factor=0.82) → risk ≈ 1 - 0.5 * 0.18 = 0.91.
            # Si durée 0.5x (factor=0.05) → risk ≈ 1 - 0.5 * 0.95 = 0.525.
            reversal_risk = 1.0 - (1.0 - reversal_risk) * (1.0 - duration_factor)
            risk_factors.append(
                f"duration_ratio={duration_ratio:.2f} factor={duration_factor:.3f}"
            )
        except (TypeError, ValueError):
            pass

    # Facteur vol
    vol_bucket = _bucket_vol_atr(context.vol_atr_pips)
    if vol_bucket == "HIGH":
        reversal_risk = min(1.0, reversal_risk + RET_WEIGHT_VOL_HIGH)
        risk_factors.append("vol=HIGH(+0.20)")
    elif vol_bucket == "LOW":
        reversal_risk = max(0.0, reversal_risk + RET_WEIGHT_VOL_LOW)
        risk_factors.append("vol=LOW(-0.10)")

    # Facteur divergence MTF
    if context.mtf_divergence:
        reversal_risk = min(1.0, reversal_risk + RET_WEIGHT_DIVERGENCE)
        risk_factors.append("mtf_div=True(+0.30)")

    # Borner [0, 1]
    reversal_risk = max(0.0, min(1.0, reversal_risk))

    # 4. P(win | phase_T+1) via cycle memory si cellule existe
    # (ne dépend pas du kill switch V9_CYCLE_MEMORY_ENABLED — consumer).
    p_win_given_phase: float | None = None
    if cycle_db is not None and cycle_db.exists():
        try:
            from core.v9.v9_cycle_memory import recall as cycle_recall
            cp_next = cycle_recall(
                symbol=context.symbol,
                timeframe=context.timeframe,
                regime_type=context.regime_type,
                phase=phase_predicted,
                vol_atr_pips=context.vol_atr_pips,
                db_path=cycle_db,
            )
            if cp_next is not None and cp_next.is_actionable():
                p_win_given_phase = cp_next.win_rate
        except Exception as e:
            logger.debug("predictive: cycle_memory recall (next phase) failed: %s", e)

    # 5. Confidence = f(n_transitions, dominance, freshness)
    confidence = transition.confidence

    # 6. Estimation fenêtre retournement (en bougies)
    if mean_duration is not None:
        reversal_window_bars = max(1, int(mean_duration * 0.3))
    else:
        reversal_window_bars = 5  # défaut conservateur

    rationale = (
        f"phase_T={context.phase} phase_T+1_pred={phase_predicted} "
        f"p_no_change={p_no_change:.3f} | "
        + " ".join(risk_factors)
        + f" | reversal_risk={reversal_risk:.3f}"
        + (f" p_win_given={p_win_given_phase:.3f}" if p_win_given_phase is not None else "")
        + f" n_transitions={transition.n_transitions}"
    )

    return Prediction(
        phase_predicted=phase_predicted,
        phase_distribution={k: round(v, 4) for k, v in phase_distribution.items()},
        p_no_change=round(p_no_change, 4),
        p_reversal=round(p_reversal, 4),
        reversal_risk=round(reversal_risk, 4),
        reversal_window_bars=reversal_window_bars,
        p_win_given_phase=round(p_win_given_phase, 4) if p_win_given_phase is not None else None,
        confidence=round(confidence, 4),
        rationale=rationale,
    )


def _fallback_prediction(context: PredictiveContext, reason: str) -> Prediction:
    """Prédiction de repli (données insuffisantes)."""
    return Prediction(
        phase_predicted=context.phase,  # assume pas de changement
        phase_distribution={p: 0.25 for p in VALID_PHASES},
        p_no_change=0.25,
        p_reversal=0.75,
        reversal_risk=0.5,
        reversal_window_bars=5,
        p_win_given_phase=None,
        confidence=0.0,
        rationale=f"fallback({reason})",
    )


# ------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    """CLI : predict dry-run pour un contexte."""
    import argparse
    parser = argparse.ArgumentParser(
        description="v9_predictive_engine CLI (dry-run)"
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--regime", default="NEUTRE")
    parser.add_argument("--phase", default="culmination",
                        choices=VALID_PHASES)
    parser.add_argument("--vol-atr", type=float, default=3.5)
    parser.add_argument("--duration", type=float, default=None,
                        help="Durée écoulée dans la phase (bougies)")
    parser.add_argument("--mtf-div", action="store_true",
                        help="Force mtf_divergence=True")
    args = parser.parse_args(argv)

    ctx = PredictiveContext(
        symbol=args.symbol,
        timeframe=args.timeframe,
        regime_type=args.regime,
        phase=args.phase,
        vol_atr_pips=args.vol_atr,
        duration_bars=args.duration,
        mtf_divergence=args.mtf_div,
    )
    pred = predict_phase_transition(ctx)
    print(json.dumps(pred.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
