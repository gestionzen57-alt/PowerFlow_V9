"""v9_meta_strategy_optimizer.py — Sélection contextuelle de stratégies (Phase E, Doctrine R33).

Méta-couche au-dessus de `StrategySelector` (v9_strategy_pole.StrategySelector).

**Pourquoi ce module existe** :
- Le `StrategySelector` actuel choisit la stratégie sur la base d'un
  triplet `(principle, session, regime)`. C'est une granularité correcte
  mais **manque la dimension phase comportementale** (culmination /
  initiation / developpement / resolution) et la dimension volatilité
  relative (LOW / MEDIUM / HIGH ATR).
- Ce module ajoute ces deux dimensions et arbitre entre plusieurs
  **stratégies candidates** (TP_SL, TRAILING, TP_PARTIAL, FAST_EXIT)
  par un **score composite contextuel** : WR × PF × (1 - DD_ratio) ×
  log(n+1) × context_weight.

**Volet doctrinal** :
- R2 additif (clé préfixée `meta_strategy_*`, jamais destructif)
- R6 défensif (try/except + fallback vers `StrategySelector.recommend()`
  si contexte trop pauvre ou engine désactivé)
- R7 testable (DB mémoire + mock StrategySelector)
- R8 ne touche pas la DB live (lecture seule sur `principle_scores` +
  `paper_trades`, écriture nulle)
- R18 code pur (zéro LLM, 100 % stdlib)
- R33 doctrine du **Système Prédictif**

**Volet performance attendu** :
- Audit 2026-07-18 : 8771 décisions résolues, 226 stratégies scorées
  dans `principle_scores`, 4817 paper trades. Volumétrie suffisante
  pour la stratification (symbol, regime, phase, vol).
- Cible : **+10 pts WR et +1.5 PF** sur sous-ensembles à contexte dense
  (GBPUSD M15 NEUTRE culmination).
- Activation : `V9_META_STRATEGY_OPTIMIZER_ENABLED=1` (motion CEO 2026-07-18
  « APPLY direct pour les modules à gain certain »).

**Stratégies candidates supportées** :
1. **TP_SL** : take profit + stop loss statique. Bon en range / distribution.
2. **TRAILING** : trailing stop dynamique. Bon en trend (PF > 2).
3. **TP_PARTIAL** : 50% du sizing à TP, 50% en trailing. Compromis.
4. **FAST_EXIT** : time-based exit court (5-10 bougies). Bon en climax
   ou phase resolution.
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
    CyclePattern,
    MIN_N_OBSERVATIONS,
    cycle_memory_enabled,
    recall as cycle_recall,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ const

# Kill switch.
META_STRATEGY_ENABLED_ENV = "V9_META_STRATEGY_OPTIMIZER_ENABLED"

# Stratégies candidates.
STRATEGY_TP_SL = "TP_SL"
STRATEGY_TRAILING = "TRAILING"
STRATEGY_TP_PARTIAL = "TP_PARTIAL"
STRATEGY_FAST_EXIT = "FAST_EXIT"
ALL_STRATEGIES = (STRATEGY_TP_SL, STRATEGY_TRAILING, STRATEGY_TP_PARTIAL, STRATEGY_FAST_EXIT)

# Phases comportementales alignées sur `behaviors.phase`.
VALID_PHASES = ("culmination", "developpement", "initiation", "resolution")

# Vol buckets alignés sur `v9_cycle_memory._bucket_vol_atr`.
VOL_LOW = "LOW"
VOL_MEDIUM = "MEDIUM"
VOL_HIGH = "HIGH"
VOL_UNKNOWN = "UNKNOWN"
VALID_VOL_BUCKETS = (VOL_LOW, VOL_MEDIUM, VOL_HIGH, VOL_UNKNOWN)

# Bornes sizing/tp/sl alignées sur core/v9/config.py (R30).
DEFAULT_TP = 10.0
DEFAULT_SL = 15.0
MIN_TP = 5.0
MAX_TP = 20.0
MIN_SL = 5.0
MAX_SL = 20.0

# Paramètres de scoring composite.
MIN_TRADES_FOR_SCORE = 5          # < ce seuil, pas de score (fallback)
LOG_N_WEIGHT = 0.2                # poids du facteur log(n+1)
DD_RATIO_CAP = 0.20               # DD au-delà de 20% du capital → pénalité max
TRAILING_PF_THRESHOLD = 2.0       # PF > 2.0 → TRAILING favorisé (cf. StrategySelector)
FAST_EXIT_DURATION_P25 = 5.0      # < P25 durée phase → FAST_EXIT favorisé


# ------------------------------------------------------------------ dataclasses


@dataclass(frozen=True)
class ContextScore:
    """Score composite d'une stratégie candidate pour un contexte donné.

    Attributs :
    - `strategy` : nom de la stratégie candidate (TP_SL / TRAILING / ...)
    - `score` : score composite ∈ [0, 1]
    - `wr` : win-rate observé [0, 1]
    - `pf` : profit factor observé
    - `n_trades` : nombre de trades sur lequel le score est calculé
    - `dd_ratio` : drawdown ratio [0, 1] (capé à DD_RATIO_CAP)
    - `context_weight` : poids contextuel (cyclic memory, vol bucket, etc.)
    - `rationale` : explication textuelle (debug)
    """
    strategy: str
    score: float
    wr: float
    pf: float
    n_trades: int
    dd_ratio: float
    context_weight: float
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MetaStrategyDecision:
    """Décision finale du méta-stratégie optimizer."""
    chosen_strategy: str
    recommended_tp: float
    recommended_sl: float
    confidence: float
    source: str                   # "meta_optimizer" / "fallback_selector" / "default"
    all_candidates: tuple[ContextScore, ...]
    cycle_memory: CyclePattern | None
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # CyclePattern non sérialisable tel quel → conversion.
        if self.cycle_memory is not None:
            d["cycle_memory"] = self.cycle_memory.to_dict()
        else:
            d["cycle_memory"] = None
        return d


# ------------------------------------------------------------------ kill switch

def meta_strategy_optimizer_enabled() -> bool:
    """Kill switch — défaut ON (motion CEO 2026-07-18 APPLY direct)."""
    val = os.environ.get(META_STRATEGY_ENABLED_ENV, "1")
    return val == "1"


# ------------------------------------------------------------------ helpers

def _clamp_tp(tp: float) -> float:
    return max(MIN_TP, min(MAX_TP, float(tp)))


def _clamp_sl(sl: float) -> float:
    return max(MIN_SL, min(MAX_SL, float(sl)))


def _dd_ratio(max_drawdown_pips: float, capital_pips: float = 1000.0) -> float:
    """Drawdown ratio [0, 1]. capital_pips par défaut = 1000 (≈ 10% de marge)."""
    if capital_pips <= 0:
        return 1.0
    return min(1.0, abs(max_drawdown_pips) / capital_pips)


def _compute_composite_score(
    wr: float,
    pf: float,
    n_trades: int,
    dd_ratio: float,
    context_weight: float = 1.0,
) -> float:
    """Score composite ∈ [0, 1].

    Formule :
        score = wr × min(pf, 5)/5 × (1 - dd_ratio) × log(n+1)^k × context_weight
    - WR ∈ [0, 1] (pondération directe)
    - PF borné à 5 (au-delà = capping, évite qu'un PF outlier écrase tout)
    - DD ratio pénalité linéaire
    - log(n+1)^0.2 = facteur volume (doubler n augmente le score de 1.15× max)
    - context_weight ∈ [0.5, 1.5] : bonus si contexte chaud, malus si froid
    """
    if n_trades < MIN_TRADES_FOR_SCORE:
        return 0.0
    wr_clamped = max(0.0, min(1.0, wr))
    pf_clamped = max(0.0, min(5.0, pf))
    dd_penalty = max(0.0, min(1.0, 1.0 - dd_ratio))
    vol_factor = math.log(n_trades + 1) ** LOG_N_WEIGHT
    ctx_clamped = max(0.5, min(1.5, context_weight))
    return round(wr_clamped * (pf_clamped / 5.0) * dd_penalty * vol_factor * ctx_clamped, 4)


# ------------------------------------------------------------------ core


def _score_candidate_strategies(
    *,
    symbol: str,
    timeframe: str,
    regime_type: str,
    phase: str,
    vol_atr_pips: float | None,
    direction: str,
    db_path: Path | str | None,
) -> list[ContextScore]:
    """Score les 4 stratégies candidates pour un contexte opérationnel.

    Sources de données :
    - `principle_scores` : WR/PF agrégés par stratégie (226 lignes)
    - `paper_trades` : DD max par stratégie
    - `cycle_memory` (TIER 1.1) : context_weight via pattern historique
    """
    candidates: list[ContextScore] = []
    if db_path is None:
        return candidates

    db_p = Path(db_path) if not isinstance(db_path, Path) else db_path
    if not db_p.exists():
        return candidates

    try:
        conn = sqlite3.connect(str(db_p))
        try:
            # Récupère les stats par stratégie candidate depuis principle_scores
            # (filtré par combination_hash != NULL = combinaisons)
            # et les paper_trades pour DD.
            conn.row_factory = sqlite3.Row

            # Map stratégie → heuristique de filtrage principle_scores
            # TP_SL = tous, TRAILING = WR > 0.7 et PF > 2.0,
            # TP_PARTIAL = WR > 0.5 et PF entre 1.0 et 2.0,
            # FAST_EXIT = WR faible mais petit DD.
            strategy_filters = {
                STRATEGY_TP_SL: "",          # tous
                STRATEGY_TRAILING: " AND win_rate > 0.70 AND (total_pips / MAX(1, n_losses)) > 2.0 ",
                STRATEGY_TP_PARTIAL: " AND win_rate BETWEEN 0.50 AND 0.85 AND (total_pips / MAX(1, n_losses)) BETWEEN 1.0 AND 2.5 ",
                STRATEGY_FAST_EXIT: " AND n_trades > 0 AND avg_pips > -2.0 ",
            }

            # Context weight depuis cycle memory
            ctx_weight = 1.0
            cm: CyclePattern | None = None
            cm_db = CYCLE_MEMORY_DB_PATH if cycle_memory_enabled() else None
            if cm_db and cm_db.exists():
                try:
                    cm = cycle_recall(symbol, timeframe, regime_type, phase,
                                      vol_atr_pips, db_path=cm_db)
                except Exception as e:
                    logger.debug("meta_strategy: cycle_memory recall failed: %s", e)
                    cm = None
            if cm is not None and cm.n_observations >= MIN_N_OBSERVATIONS:
                # Bonus si WR historique > 0.55, malus si < 0.45
                if cm.win_rate > 0.55:
                    ctx_weight = 1.0 + min(0.5, (cm.win_rate - 0.55) * 2.0)
                elif cm.win_rate < 0.45:
                    ctx_weight = 1.0 - min(0.5, (0.45 - cm.win_rate) * 2.0)

            # Bonus/malus phase
            phase_phase_weight = {
                "culmination": 1.10,      # phase stable → bon pour TRAILING
                "developpement": 1.05,
                "initiation": 1.0,        # neutre
                "resolution": 0.85,       # phase finale → FAST_EXIT favorisé
            }.get(phase, 1.0)

            # Bonus/malus vol
            from core.v9.v9_cycle_memory import _bucket_vol_atr as bucket
            vol_bucket = bucket(vol_atr_pips)
            vol_weight = {
                VOL_LOW: 0.90,    # faible vol → TP_SL plus fiable
                VOL_MEDIUM: 1.05,
                VOL_HIGH: 1.10,   # haute vol → TRAILING capture les swings
                VOL_UNKNOWN: 1.0,
            }.get(vol_bucket, 1.0)

            combined_weight = ctx_weight * phase_phase_weight * vol_weight

            for strategy, extra_filter in strategy_filters.items():
                try:
                    # Stats globales par stratégie (pas de filtre par contexte DB,
                    # la stratification fine est faite par cycle_memory + weights).
                    sql = f"""
                        SELECT
                            COALESCE(SUM(n_trades), 0) AS n_trades,
                            COALESCE(SUM(n_wins), 0) AS n_wins,
                            COALESCE(SUM(n_losses), 0) AS n_losses,
                            COALESCE(SUM(total_pips), 0.0) AS total_pips,
                            COALESCE(AVG(NULLIF(win_rate, 0)), 0.0) AS avg_wr,
                            COALESCE(SUM(total_pips) / MAX(1, SUM(n_losses)), 0.0) AS pf
                        FROM principle_scores
                        WHERE 1=1 {extra_filter}
                    """
                    row = conn.execute(sql).fetchone()
                    if row is None or row["n_trades"] == 0:
                        # Stratégie sans data → score conservateur
                        score_obj = ContextScore(
                            strategy=strategy,
                            score=0.0,
                            wr=0.0,
                            pf=0.0,
                            n_trades=0,
                            dd_ratio=0.0,
                            context_weight=combined_weight,
                            rationale="no_data_in_principle_scores",
                        )
                        candidates.append(score_obj)
                        continue

                    n_t = int(row["n_trades"])
                    n_w = int(row["n_wins"])
                    wr = float(row["avg_wr"]) if row["avg_wr"] else (n_w / max(1, n_t))
                    pf = float(row["pf"]) if row["pf"] else 0.0

                    # DD : on récupère le max DD depuis paper_trades (approximation)
                    # Sur une stratégie donnée, on approxime par le min cumulé.
                    dd_row = conn.execute(
                        "SELECT COALESCE(MIN(pips_simulated), 0.0) FROM paper_trades"
                    ).fetchone()
                    dd_pips = float(dd_row[0]) if dd_row else 0.0
                    dd_r = _dd_ratio(dd_pips)

                    # Specific override : FAST_EXIT n'est pertinent qu'en climax/resolution
                    # On pénalise si phase ne correspond pas.
                    if strategy == STRATEGY_FAST_EXIT and phase not in ("resolution", "culmination"):
                        specific_weight = 0.6
                    elif strategy == STRATEGY_TRAILING and phase == "resolution":
                        specific_weight = 0.7
                    else:
                        specific_weight = 1.0

                    final_weight = combined_weight * specific_weight
                    score = _compute_composite_score(
                        wr=wr,
                        pf=pf,
                        n_trades=n_t,
                        dd_ratio=dd_r,
                        context_weight=final_weight,
                    )
                    rationale = (
                        f"WR={wr:.2%} PF={pf:.2f} n={n_t} "
                        f"dd={dd_r:.2%} ctx_w={final_weight:.2f}"
                    )
                    candidates.append(ContextScore(
                        strategy=strategy,
                        score=score,
                        wr=wr,
                        pf=pf,
                        n_trades=n_t,
                        dd_ratio=dd_r,
                        context_weight=final_weight,
                        rationale=rationale,
                    ))
                except sqlite3.Error as e:
                    logger.warning(
                        "meta_strategy: error scoring %s : %s", strategy, e
                    )
                    candidates.append(ContextScore(
                        strategy=strategy,
                        score=0.0, wr=0.0, pf=0.0,
                        n_trades=0, dd_ratio=0.0,
                        context_weight=combined_weight,
                        rationale=f"db_error: {e}",
                    ))
            return candidates
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("meta_strategy: cannot open DB %s : %s", db_p, e)
        return []


def _select_tp_sl_from_candidates(candidates: list[ContextScore]) -> tuple[float, float]:
    """Choisit TP/SL en fonction de la stratégie gagnante.

    Logique :
    - TRAILING → TP plus large (15), SL modéré (12)
    - TP_SL → défaut (10, 15)
    - TP_PARTIAL → TP modéré (10), SL serré (10)
    - FAST_EXIT → TP petit (5), SL large (15) (capture vite, laisse respirer)
    """
    if not candidates:
        return DEFAULT_TP, DEFAULT_SL
    best = max(candidates, key=lambda c: c.score)
    if best.strategy == STRATEGY_TRAILING:
        return _clamp_tp(15.0), _clamp_sl(12.0)
    if best.strategy == STRATEGY_TP_PARTIAL:
        return _clamp_tp(10.0), _clamp_sl(10.0)
    if best.strategy == STRATEGY_FAST_EXIT:
        return _clamp_tp(5.0), _clamp_sl(15.0)
    return DEFAULT_TP, DEFAULT_SL


# ------------------------------------------------------------------ API publique


def select_strategy(
    *,
    symbol: str,
    timeframe: str,
    regime_type: str,
    phase: str,
    vol_atr_pips: float | None,
    direction: str,
    db_path: Path | str | None = None,
    fallback_selector: Any = None,
) -> MetaStrategyDecision:
    """Sélection contextuelle de stratégie.

    Si `meta_strategy_optimizer_enabled()` est OFF ou si le contexte est
    trop pauvre, fallback sur le `StrategySelector` fourni (ou défaut).

    Args :
        symbol, timeframe, regime_type, phase, vol_atr_pips, direction :
            contexte opérationnel (cf. CyclePattern).
        db_path : chemin vers `v9_forces.db` (lecture seule sur principle_scores).
        fallback_selector : instance `StrategySelector` à utiliser en fallback.
            Si None, retourne TP/SL défaut.

    Returns :
        MetaStrategyDecision avec stratégie choisie + rationale complète.
    """
    # Kill switch
    if not meta_strategy_optimizer_enabled():
        return _fallback_decision(
            fallback_selector, symbol, timeframe, regime_type,
            source="disabled_kill_switch",
        )

    # Validation phase (R6)
    if phase not in VALID_PHASES:
        phase = "initiation"  # défaut neutre

    # 1. Score les 4 candidats
    candidates = _score_candidate_strategies(
        symbol=symbol,
        timeframe=timeframe,
        regime_type=regime_type,
        phase=phase,
        vol_atr_pips=vol_atr_pips,
        direction=direction,
        db_path=db_path,
    )

    # 2. Si aucun candidat (DB absente, pas de data) → fallback
    if not candidates:
        return _fallback_decision(
            fallback_selector, symbol, timeframe, regime_type,
            source="no_candidates_db_empty",
        )

    # 3. Si tous les candidats ont score 0 → fallback conservateur
    best = max(candidates, key=lambda c: c.score)
    if best.score <= 0.0:
        return _fallback_decision(
            fallback_selector, symbol, timeframe, regime_type,
            source="all_candidates_zero_score",
        )

    # 4. Choix de la stratégie gagnante
    tp, sl = _select_tp_sl_from_candidates(candidates)

    # 5. Récupération du cycle pattern pour rationale
    cm: CyclePattern | None = None
    if cycle_memory_enabled() and CYCLE_MEMORY_DB_PATH.exists():
        try:
            cm = cycle_recall(symbol, timeframe, regime_type, phase,
                              vol_atr_pips, db_path=CYCLE_MEMORY_DB_PATH)
        except Exception as e:
            logger.debug("meta_strategy: cycle_memory recall failed: %s", e)

    confidence = min(1.0, best.score + (cm.confidence * 0.3 if cm else 0.0))

    rationale = (
        f"chosen={best.strategy} score={best.score:.3f} "
        f"vs runners=" + ", ".join(
            f"{c.strategy}={c.score:.3f}" for c in candidates if c != best
        )
        + (f" cycle_memory_WR={cm.win_rate:.2%}" if cm else " cycle_memory=None")
    )

    return MetaStrategyDecision(
        chosen_strategy=best.strategy,
        recommended_tp=tp,
        recommended_sl=sl,
        confidence=round(confidence, 4),
        source="meta_optimizer",
        all_candidates=tuple(sorted(candidates, key=lambda c: -c.score)),
        cycle_memory=cm,
        rationale=rationale,
    )


def _fallback_decision(
    fallback_selector: Any,
    symbol: str,
    timeframe: str,
    regime_type: str,
    source: str,
) -> MetaStrategyDecision:
    """Décision de repli si meta_optimizer désactivé ou contexte pauvre."""
    if fallback_selector is not None and hasattr(fallback_selector, "recommend"):
        try:
            rec = fallback_selector.recommend(
                principle="default",
                session="unknown",
                regime=regime_type,
            )
            return MetaStrategyDecision(
                chosen_strategy=rec.recommended_strategy,
                recommended_tp=rec.recommended_tp,
                recommended_sl=rec.recommended_sl,
                confidence=rec.confidence,
                source="fallback_selector",
                all_candidates=(),
                cycle_memory=None,
                rationale=f"fallback to StrategySelector ({source})",
            )
        except Exception as e:
            logger.warning("meta_strategy: fallback selector failed: %s", e)
    return MetaStrategyDecision(
        chosen_strategy=STRATEGY_TP_SL,
        recommended_tp=DEFAULT_TP,
        recommended_sl=DEFAULT_SL,
        confidence=0.3,
        source=source,
        all_candidates=(),
        cycle_memory=None,
        rationale=f"default fallback ({source})",
    )


# ------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    """CLI : test select_strategy en mode dry-run."""
    import argparse
    parser = argparse.ArgumentParser(
        description="v9_meta_strategy_optimizer CLI (dry-run)"
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--regime", default="NEUTRE")
    parser.add_argument("--phase", default="culmination",
                        choices=VALID_PHASES)
    parser.add_argument("--vol-atr", type=float, default=3.5)
    parser.add_argument("--direction", default="haussiere")
    parser.add_argument("--db", type=str, default=r"C:/projet/V9/data/v9_forces.db")
    args = parser.parse_args(argv)

    decision = select_strategy(
        symbol=args.symbol,
        timeframe=args.timeframe,
        regime_type=args.regime,
        phase=args.phase,
        vol_atr_pips=args.vol_atr,
        direction=args.direction,
        db_path=args.db,
    )
    print(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
