"""V10 VSA Threshold Calibrator — Phase 21+ R8 grid search seuils VSA.

Doctrine V10 (CEO phase 21+ suite) :
  R1 : agit par défaut
  R2 : additif pur
  R6 : fail-open
  R7 : tests verts cumulés
  R8 : AUTO-CALIBRATION seuils VSA BULLISH/BEARISH
  R9 : audit metadata honnête
  R10 : zéro capital

Objectif Phase 21+ :
  Le Phase 11+ v10_compression_extension.py utilise seuils fixes ±0.30.
  Cette phase recalibre ces seuils par R8 grid search pour maximiser :
    - taux de signal non-NEUTRAL (couverture)
    - accuracy directionnelle (WR proxy) sur signaux BULLISH/BEARISH
  Contraintes :
    - seuil_bearish < 0 < seuil_bullish (ordonné)
    - |seuil_bullish - seuil_bearish| >= 0.10 (séparation minimale)
"""
from __future__ import annotations

import itertools
import json
import statistics
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Tuple

from core.v10.v10_compression_extension import (
    compute_vsa_signal,
    compute_tf_vsa_state,
    load_multi_tf_from_db,
)


# ─────────────────────────────────────────────────────────────────────
# CONSTANTES GRID
# ─────────────────────────────────────────────────────────────────────

# Seuils bullish candidats
BULLISH_THRESHOLD_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]

# Seuils bearish candidats (symétriques par défaut)
BEARISH_THRESHOLD_GRID = [-0.50, -0.40, -0.35, -0.30, -0.25, -0.20, -0.15, -0.10]

# Contrainte R8 (Pitfall CEO) : séparation minimale 0.10
MIN_SEPARATION = 0.10

# Limites R10
MAX_COMBOS = 30


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class VSAThresholdParams:
    """Seuils VSA calibrés R8 (Phase 21+)."""
    bullish_threshold: float = 0.30
    bearish_threshold: float = -0.30
    method: str = ""
    n_pairs_evaluated: int = 0
    target_metric: str = ""
    target_metric_value: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class VSAThresholdReport:
    """Rapport R8 calibration seuils VSA."""
    timestamp: str = ""
    n_grid_combos_evaluated: int = 0
    best_params: VSAThresholdParams = field(default_factory=VSAThresholdParams)
    top_10_combos: List[VSAThresholdParams] = field(default_factory=list)
    metric_by_combo: Dict[str, float] = field(default_factory=dict)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────

def _valid_threshold_combo(bullish: float, bearish: float) -> bool:
    """Contraintes R8 :
    - bearish < 0 < bullish
    - |bullish - bearish| >= MIN_SEPARATION
    """
    if not (bearish < 0 < bullish):
        return False
    if abs(bullish - bearish) < MIN_SEPARATION:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────
# ÉVALUATION 1 COMBO
# ─────────────────────────────────────────────────────────────────────

def _evaluate_threshold_combo(
    snapshots_per_pair: Dict[str, Dict[str, List[Dict]]],
    *,
    bullish_threshold: float,
    bearish_threshold: float,
) -> Dict:
    """Évalue 1 combo seuils sur toutes les paires × TF.

    Args:
        snapshots_per_pair: {pair: {tf: [snapshots]}}

    Returns:
        dict {n_signals_bullish, n_signals_bearish, n_signals_neutral,
              wr_bullish_proxy, wr_bearish_proxy, coverage_pct}
    """
    n_bull = 0
    n_bear = 0
    n_neut = 0
    n_total = 0

    # Pour calculer WR proxy par signal :
    # Si signal=BULLISH et close[t+1] > close[t] → win
    # Si signal=BEARISH et close[t+1] < close[t] → win
    n_bull_wins = 0
    n_bear_wins = 0

    for pair, tfs_snapshots in snapshots_per_pair.items():
        for tf, snaps in tfs_snapshots.items():
            if len(snaps) < 5:
                continue

            # Calculer signal pour chaque snapshot (window=20)
            window_size = 20
            for i in range(0, len(snaps) - window_size):
                window = snaps[i:i + window_size]
                state_m30 = compute_tf_vsa_state(window, "M30", window_size=window_size)
                state_h1 = compute_tf_vsa_state(window, "H1", window_size=window_size)
                state_h4 = compute_tf_vsa_state(window, "H4", window_size=window_size)

                score_global = (
                    0.50 * state_h4.score_directionnel
                    + 0.30 * state_h1.score_directionnel
                    + 0.20 * state_m30.score_directionnel
                )
                # M30 align bonus
                m30_aligns = (
                    (state_m30.score_directionnel > 0 and state_h1.score_directionnel > 0)
                    or (state_m30.score_directionnel < 0 and state_h1.score_directionnel < 0)
                )
                if m30_aligns:
                    if score_global > 0:
                        score_global += 0.15
                    elif score_global < 0:
                        score_global -= 0.15
                # H4 extreme bonus
                if state_h4.last_intensite == "EXTREME":
                    if score_global > 0:
                        score_global += 0.10
                    elif score_global < 0:
                        score_global -= 0.10

                score_global = max(-1.0, min(1.0, score_global))

                # Apply thresholds
                if score_global > bullish_threshold:
                    signal = "BULLISH"
                    n_bull += 1
                elif score_global < bearish_threshold:
                    signal = "BEARISH"
                    n_bear += 1
                else:
                    signal = "NEUTRAL"
                    n_neut += 1
                n_total += 1

                # Proxy WR : si on a un close[t+1]
                if i + window_size + 1 < len(snaps):
                    close_t = snaps[i + window_size].get("close", 0)
                    close_t_1 = snaps[i + window_size + 1].get("close", 0)
                    if close_t and close_t_1 and signal == "BULLISH":
                        if close_t_1 > close_t:
                            n_bull_wins += 1
                    elif close_t and close_t_1 and signal == "BEARISH":
                        if close_t_1 < close_t:
                            n_bear_wins += 1

    wr_bull = (n_bull_wins / n_bull) if n_bull else 0.0
    wr_bear = (n_bear_wins / n_bear) if n_bear else 0.0
    coverage = (n_bull + n_bear) / n_total if n_total else 0.0

    return {
        "n_signals_bullish": n_bull,
        "n_signals_bearish": n_bear,
        "n_signals_neutral": n_neut,
        "n_signals_total": n_total,
        "wr_bullish_proxy": round(wr_bull, 4),
        "wr_bearish_proxy": round(wr_bear, 4),
        "coverage_pct": round(coverage, 4),
    }


# ─────────────────────────────────────────────────────────────────────
# GRID SEARCH R8
# ─────────────────────────────────────────────────────────────────────

def calibrate_vsa_thresholds(
    db_path: str = "data/v9_forces.db",
    *,
    pairs: Tuple[str, ...] = ("EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"),
    timeframes: Tuple[str, ...] = ("M30", "H1", "H4"),
    limit: int = 200,
    target_metric: str = "wr_proxy_balanced",  # ou "coverage" ou "wr_proxy_diff"
    max_combos: int = MAX_COMBOS,
) -> VSAThresholdReport:
    """R8 grid search : trouve seuils VSA optimaux.

    target_metric :
      - "wr_proxy_balanced" : moyenne wr_bullish + wr_bearish
      - "coverage" : taux signal non-NEUTRAL
      - "wr_proxy_diff" : wr_bullish - wr_bearish (favor directional clarity)
    """
    # Charger tous les snapshots
    snapshots_per_pair: Dict[str, Dict[str, List[Dict]]] = {}
    for pair in pairs:
        mtf = load_multi_tf_from_db(db_path, pair, tfs=timeframes, limit=limit)
        if all(len(mtf.get(tf, [])) > 5 for tf in timeframes):
            snapshots_per_pair[pair] = mtf

    if not snapshots_per_pair:
        return VSAThresholdReport(
            timestamp="",
            audit={"error": "insufficient_data", "n_pairs_loaded": 0},
        )

    # Générer combos valides
    all_combos = []
    for b in BULLISH_THRESHOLD_GRID:
        for be in BEARISH_THRESHOLD_GRID:
            if _valid_threshold_combo(b, be):
                all_combos.append((b, be))

    if len(all_combos) > max_combos:
        # R10 safety cap
        step = len(all_combos) // max_combos
        all_combos = all_combos[::step][:max_combos]

    metric_by_combo: Dict[str, float] = {}
    top_10: List[VSAThresholdParams] = []
    best_value = -1e9
    best_combo: Tuple[float, float] = (0.30, -0.30)

    for idx, (b_thr, be_thr) in enumerate(all_combos):
        metrics = _evaluate_threshold_combo(
            snapshots_per_pair,
            bullish_threshold=b_thr,
            bearish_threshold=be_thr,
        )

        # Métrique cible
        if target_metric == "wr_proxy_balanced":
            wr_b = metrics["wr_bullish_proxy"]
            wr_be = metrics["wr_bearish_proxy"]
            value = (wr_b + wr_be) / 2 if (wr_b or wr_be) else 0.0
        elif target_metric == "coverage":
            value = metrics["coverage_pct"]
        elif target_metric == "wr_proxy_diff":
            value = abs(metrics["wr_bullish_proxy"] - metrics["wr_bearish_proxy"])
        else:
            value = (metrics["wr_bullish_proxy"] + metrics["wr_bearish_proxy"]) / 2

        combo_key = f"combo_{idx}"
        metric_by_combo[combo_key] = round(value, 4)

        if value > best_value:
            best_value = value
            best_combo = (b_thr, be_thr)

        candidate = VSAThresholdParams(
            bullish_threshold=b_thr,
            bearish_threshold=be_thr,
            method="grid_search_phase21+",
            n_pairs_evaluated=len(snapshots_per_pair),
            target_metric=target_metric,
            target_metric_value=round(value, 4),
            audit={
                "wr_bullish_proxy": metrics["wr_bullish_proxy"],
                "wr_bearish_proxy": metrics["wr_bearish_proxy"],
                "coverage_pct": metrics["coverage_pct"],
                "n_signals_total": metrics["n_signals_total"],
            },
        )
        top_10.append(candidate)

    top_10.sort(key=lambda p: p.target_metric_value, reverse=True)
    top_10 = top_10[:10]

    best_metrics = _evaluate_threshold_combo(
        snapshots_per_pair,
        bullish_threshold=best_combo[0],
        bearish_threshold=best_combo[1],
    )

    best_params = VSAThresholdParams(
        bullish_threshold=best_combo[0],
        bearish_threshold=best_combo[1],
        method="grid_search_phase21+",
        n_pairs_evaluated=len(snapshots_per_pair),
        target_metric=target_metric,
        target_metric_value=round(best_value, 4),
        audit={
            "wr_bullish_proxy": best_metrics["wr_bullish_proxy"],
            "wr_bearish_proxy": best_metrics["wr_bearish_proxy"],
            "coverage_pct": best_metrics["coverage_pct"],
            "n_signals_total": best_metrics["n_signals_total"],
            "n_combos_evaluated": len(all_combos),
            "limit_per_pair_tf": limit,
        },
    )

    return VSAThresholdReport(
        timestamp="",
        n_grid_combos_evaluated=len(all_combos),
        best_params=best_params,
        top_10_combos=top_10,
        metric_by_combo=metric_by_combo,
        audit={
            "method": "R8 grid search seuils VSA BULLISH/BEARISH",
            "doctrine": "R2, R6, R7, R8, R9, R10",
            "constraint_R8": f"bearish<0<bullish, separation>={MIN_SEPARATION}",
            "constraint_R10": f"max_combos={max_combos}",
        },
    )


__all__ = [
    "BULLISH_THRESHOLD_GRID",
    "BEARISH_THRESHOLD_GRID",
    "MIN_SEPARATION",
    "MAX_COMBOS",
    "VSAThresholdParams",
    "VSAThresholdReport",
    "_valid_threshold_combo",
    "_evaluate_threshold_combo",
    "calibrate_vsa_thresholds",
]
