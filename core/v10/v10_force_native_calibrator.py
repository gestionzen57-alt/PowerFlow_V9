"""V10 Force Native Calibrator — Phase 21+ R8 auto-calibration.

Doctrine V10 (CEO phase 21+ suite) :
  R1 : agit par défaut
  R2 : additif pur (0 import core/v9/)
  R6 : fail-open (data absente → garde defaults)
  R7 : tests verts cumulés
  R8 : AUTO-CALIBRATION — ce module recalibre INTENSITY_TO_PIPS et
        seuils VSA en maximisant corrélation WR natif vs proxy
  R9 : audit metadata honnête
  R10 : zéro capital (calcul seul)

Objectif Phase 21+ :
  Le Phase 20+ v10_force_native.py utilise des poids conservateurs
  (1.5/3.0/5.0/8.0). Cette phase recalibre ces poids par R8 grid search
  pour maximiser la métrique cible :
    - corrélation WR natif vs WR proxy (Pearson)
    - WR natif moyen (par paire × TF)
    - delta_WR vs proxy (positif = bon)
  Contraintes :
    - R2 additif : recalibration locale au module, 0 impact core/v9/
    - R6 fail-open : si data absente, garde defaults
    - R9 : grille + résultats + best params + JSON sérialisable
    - R10 : paper only, jamais d'ordre réel
"""
from __future__ import annotations

import itertools
import json
import sqlite3
import statistics
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

# Imports locaux (R2 additif pur)
from core.v10.v10_force_native import (
    INTENSITY_TO_PIPS as DEFAULT_INTENSITY_TO_PIPS,
    CROISEMENT_DIRECTION_TO_PIPS,
    RECROISEMENT_BONUS_PIPS as DEFAULT_RECROISEMENT_BONUS_PIPS,
    REJET_PENALTY_PIPS as DEFAULT_REJET_PENALTY_PIPS,
    _safe_float,
    _intensity_to_pips,
    compute_force_native_features,
    compute_native_force_report,
    load_snapshots_from_db,
)


# ─────────────────────────────────────────────────────────────────────
# CONSTANTES GRID SEARCH
# ─────────────────────────────────────────────────────────────────────

# Grille intensité → pips (R8 calibration)
INTENSITY_GRID = {
    "FAIBLE": [0.5, 1.0, 1.5, 2.0],
    "MOYEN": [1.5, 2.5, 3.0, 4.0, 5.0],
    "FORT": [3.0, 4.0, 5.0, 6.0, 7.0],
    "EXTREME": [5.0, 6.5, 8.0, 10.0, 12.0],
}

# Bonus grid
RECROISEMENT_BONUS_GRID = [1.0, 1.5, 2.0, 3.0, 4.0]
REJET_PENALTY_GRID = [-0.5, -1.0, -1.5, -2.0, -3.0]

# Contraintes R8 (Pitfall CEO Phase 21) :
# - intensité FAIBLE ≤ MOYEN ≤ FORT ≤ EXTREME (ordonnée)
# - recroisement_bonus ≥ 0
# - rejet_penalty ≤ 0


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CalibratedParams:
    """Paramètres calibrés R8 (Phase 21+)."""
    intensity_to_pips: Dict[str, float] = field(default_factory=dict)
    recroisement_bonus_pips: float = 0.0
    rejet_penalty_pips: float = 0.0
    method: str = ""
    n_pairs_tf_evaluated: int = 0
    target_metric: str = ""
    target_metric_value: float = 0.0
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CalibrationReport:
    """Rapport R8 calibration (Phase 21+)."""
    timestamp: str = ""
    n_grid_combos_evaluated: int = 0
    best_params: CalibratedParams = field(default_factory=CalibratedParams)
    top_10_combos: List[CalibratedParams] = field(default_factory=list)
    metric_by_combo: Dict[str, float] = field(default_factory=dict)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _valid_intensity_combo(combo: Dict[str, float]) -> bool:
    """Contrainte R8 : intensité ordonnée FAIBLE ≤ MOYEN ≤ FORT ≤ EXTREME."""
    f = combo.get("FAIBLE", 0)
    m = combo.get("MOYEN", 0)
    fo = combo.get("FORT", 0)
    e = combo.get("EXTREME", 0)
    return f <= m <= fo <= e


def _safe_pearson(xs: List[float], ys: List[float]) -> float:
    """Pearson correlation, 0 si undefined ou constant."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    n = len(xs)
    if statistics.stdev(xs) == 0 or statistics.stdev(ys) == 0:
        return 0.0
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = sum((x - mean_x) ** 2 for x in xs)
    den_y = sum((y - mean_y) ** 2 for y in ys)
    den = (den_x * den_y) ** 0.5
    return num / den if den > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────
# ÉVALUATION 1 COMBO
# ─────────────────────────────────────────────────────────────────────

def _evaluate_combo_on_pair_tf(
    snapshots: List[Dict],
    pair: str,
    timeframe: str,
    *,
    intensity_to_pips: Dict[str, float],
    recroisement_bonus_pips: float,
    rejet_penalty_pips: float,
    horizon: int = 3,
) -> Optional[Dict]:
    """Évalue 1 combo de params sur 1 (pair, TF).

    Returns:
        dict {wr_native, wr_proxy, delta_wr, avg_pnl_native, avg_pnl_proxy}
        ou None si data insuffisante.
    """
    if len(snapshots) < horizon + 1:
        return None

    pnl_native_total = 0.0
    pnl_proxy_total = 0.0
    n_native_wins = 0
    n_proxy_wins = 0
    n_trades = 0

    for i in range(len(snapshots) - horizon):
        feat = compute_force_native_features(snapshots[i], pair)

        # Pnl natif avec combo custom
        pnl_native = _compute_pnl_native_with_params(
            feat=feat,
            snapshots_t_plus=snapshots[i + 1 : i + horizon + 1],
            pair=pair,
            intensity_to_pips=intensity_to_pips,
            recroisement_bonus_pips=recroisement_bonus_pips,
            rejet_penalty_pips=rejet_penalty_pips,
        )
        pnl_native_total += pnl_native
        if pnl_native > 0:
            n_native_wins += 1

        # Pnl proxy
        close_t = _safe_float(snapshots[i].get("close", 0.0), 0.0)
        close_t_h = _safe_float(snapshots[i + horizon].get("close", 0.0), 0.0)
        if close_t > 0:
            pnl_proxy = (close_t_h - close_t) * (10000 if "JPY" not in pair else 100)
            pnl_proxy_total += pnl_proxy
            if pnl_proxy > 0:
                n_proxy_wins += 1
            n_trades += 1

    if n_trades == 0:
        return None

    return {
        "wr_native": n_native_wins / n_trades,
        "wr_proxy": n_proxy_wins / n_trades,
        "delta_wr": (n_native_wins - n_proxy_wins) / n_trades,
        "avg_pnl_native": pnl_native_total / n_trades,
        "avg_pnl_proxy": pnl_proxy_total / n_trades,
        "n_trades": n_trades,
    }


def _compute_pnl_native_with_params(
    feat,
    snapshots_t_plus: List[Dict],
    pair: str,
    *,
    intensity_to_pips: Dict[str, float],
    recroisement_bonus_pips: float,
    rejet_penalty_pips: float,
) -> float:
    """Calcule pnl natif avec params custom (R8 calibration)."""
    # Use feat for current bar, look at horizon features after
    horizon_features = [feat]
    for snap in snapshots_t_plus:
        horizon_features.append(compute_force_native_features(snap, pair))

    if not horizon_features:
        return 0.0

    pnl_total = 0.0
    for i, f in enumerate(horizon_features):
        # 1. Compression/Extension pips (composante principale)
        if not f.compression_extension_intensite:
            intensity_pips = intensity_to_pips.get("MOYEN", 3.0)
        else:
            intensity_pips = intensity_to_pips.get(
                f.compression_extension_intensite.upper(),
                intensity_to_pips.get("MOYEN", 3.0),
            )

        if f.compression_extension_etat == "COMPRESSION":
            comp_pips = intensity_pips
        elif f.compression_extension_etat == "EXTENSION":
            comp_pips = intensity_pips * 0.5
        else:
            comp_pips = intensity_pips * 0.25

        # Signe (AUTO)
        sign = 1.0 if f.force_delta >= 0 else -1.0
        comp_pips_signed = comp_pips * sign

        # 2. Croisement
        crois_pips = 0.0
        if f.croisement_detecte:
            crois_sign = CROISEMENT_DIRECTION_TO_PIPS.get(f.croisement_direction, 0.0)
            crois_pips = intensity_pips * 0.3 * crois_sign

        # 3. Recroisement
        recrois_pips = recroisement_bonus_pips * sign if f.recroisement_detecte else 0.0

        # 4. Rejet
        rejet_pips = rejet_penalty_pips * (f.rejet_intensite or 1.0) if f.rejet_repulsion_detecte else 0.0

        # 5. Force delta boost
        force_boost = (abs(f.force_delta) / 100.0) * intensity_pips * sign

        candle_pnl = comp_pips_signed + crois_pips + recrois_pips + rejet_pips + force_boost

        # Decay
        weight = 1.0 - 0.1 * i
        pnl_total += candle_pnl * weight

    return round(pnl_total, 4)


# ─────────────────────────────────────────────────────────────────────
# GRID SEARCH R8
# ─────────────────────────────────────────────────────────────────────

def _grid_combos() -> List[Dict]:
    """Génère tous les combos valides (R8 contraintes)."""
    # All intensity combos respecting ordering
    f_vals = INTENSITY_GRID["FAIBLE"]
    m_vals = INTENSITY_GRID["MOYEN"]
    fo_vals = INTENSITY_GRID["FORT"]
    e_vals = INTENSITY_GRID["EXTREME"]

    intensity_combos = []
    for f, m, fo, e in itertools.product(f_vals, m_vals, fo_vals, e_vals):
        combo = {"FAIBLE": f, "MOYEN": m, "FORT": fo, "EXTREME": e}
        if _valid_intensity_combo(combo):
            intensity_combos.append(combo)

    # All recroisement × rejet combos
    other_combos = list(itertools.product(RECROISEMENT_BONUS_GRID, REJET_PENALTY_GRID))

    # Cross-product
    all_combos = []
    for i_combo in intensity_combos:
        for rec_bonus, rej_pen in other_combos:
            all_combos.append({
                "intensity_to_pips": dict(i_combo),
                "recroisement_bonus_pips": rec_bonus,
                "rejet_penalty_pips": rej_pen,
            })
    return all_combos


def calibrate_intensity_to_pips(
    db_path: str = "data/v9_forces.db",
    *,
    pairs: Tuple[str, ...] = ("EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"),
    timeframes: Tuple[str, ...] = ("M30", "H1", "H4"),
    limit: int = 100,
    target_metric: str = "delta_wr",  # ou "wr_native_mean" ou "pearson"
    horizon: int = 3,
    max_combos: int = 50,  # safety cap R10
) -> CalibrationReport:
    """R8 grid search : trouve best params maximisant target_metric.

    Args:
        db_path: chemin vers v9_forces.db
        pairs: paires à évaluer
        timeframes: TF à évaluer
        limit: nb candles max par snapshot window
        target_metric: métrique cible ("delta_wr", "wr_native_mean", "pearson")
        horizon: nb candles futures pour pnl
        max_combos: cap R10 (ne pas tout explorer)

    Returns:
        CalibrationReport avec best_params + top 10 combos + audit.
    """
    # Charger snapshots pour tous (paire, TF)
    snapshots_per_pair_tf: Dict[Tuple[str, str], List[Dict]] = {}
    for pair in pairs:
        for tf in timeframes:
            snaps = load_snapshots_from_db(db_path, pair, tf, limit=limit)
            if len(snaps) >= horizon + 5:
                snapshots_per_pair_tf[(pair, tf)] = snaps

    if not snapshots_per_pair_tf:
        return CalibrationReport(
            timestamp="",
            audit={"error": "insufficient_data", "pairs_tf_loaded": 0},
        )

    # Générer combos
    all_combos = _grid_combos()
    if len(all_combos) > max_combos:
        # R10 safety cap : prendre 1 sur N
        step = len(all_combos) // max_combos
        all_combos = all_combos[::step][:max_combos]

    metric_by_combo: Dict[str, float] = {}
    top_10: List[CalibratedParams] = []
    best_value = -1e9
    best_combo: Optional[Dict] = None

    for idx, combo in enumerate(all_combos):
        # Évaluer combo sur tous (paire, TF)
        per_pair_tf_metrics = []
        wr_native_list = []
        wr_proxy_list = []

        for (pair, tf), snaps in snapshots_per_pair_tf.items():
            metrics = _evaluate_combo_on_pair_tf(
                snaps,
                pair,
                tf,
                intensity_to_pips=combo["intensity_to_pips"],
                recroisement_bonus_pips=combo["recroisement_bonus_pips"],
                rejet_penalty_pips=combo["rejet_penalty_pips"],
                horizon=horizon,
            )
            if metrics:
                per_pair_tf_metrics.append(metrics)
                wr_native_list.append(metrics["wr_native"])
                wr_proxy_list.append(metrics["wr_proxy"])

        if not per_pair_tf_metrics:
            continue

        # Métrique cible
        if target_metric == "delta_wr":
            value = sum(m["delta_wr"] for m in per_pair_tf_metrics) / len(per_pair_tf_metrics)
        elif target_metric == "wr_native_mean":
            value = statistics.mean(wr_native_list)
        elif target_metric == "pearson":
            value = _safe_pearson(wr_native_list, wr_proxy_list)
        else:
            value = sum(m["delta_wr"] for m in per_pair_tf_metrics) / len(per_pair_tf_metrics)

        combo_key = f"combo_{idx}"
        metric_by_combo[combo_key] = round(value, 4)

        # Track best
        if value > best_value:
            best_value = value
            best_combo = combo

        # Track top 10 (insert sorted)
        candidate_params = CalibratedParams(
            intensity_to_pips=dict(combo["intensity_to_pips"]),
            recroisement_bonus_pips=combo["recroisement_bonus_pips"],
            rejet_penalty_pips=combo["rejet_penalty_pips"],
            method="grid_search_phase21+",
            n_pairs_tf_evaluated=len(per_pair_tf_metrics),
            target_metric=target_metric,
            target_metric_value=round(value, 4),
            audit={
                "wr_native_mean": round(statistics.mean(wr_native_list), 4),
                "wr_proxy_mean": round(statistics.mean(wr_proxy_list), 4),
            },
        )
        top_10.append(candidate_params)

    # Sort top 10 by metric desc
    top_10.sort(key=lambda p: p.target_metric_value, reverse=True)
    top_10 = top_10[:10]

    best_params = CalibratedParams(
        intensity_to_pips=dict(best_combo["intensity_to_pips"]) if best_combo else dict(DEFAULT_INTENSITY_TO_PIPS),
        recroisement_bonus_pips=best_combo["recroisement_bonus_pips"] if best_combo else DEFAULT_RECROISEMENT_BONUS_PIPS,
        rejet_penalty_pips=best_combo["rejet_penalty_pips"] if best_combo else DEFAULT_REJET_PENALTY_PIPS,
        method="grid_search_phase21+",
        n_pairs_tf_evaluated=len(snapshots_per_pair_tf),
        target_metric=target_metric,
        target_metric_value=round(best_value, 4),
        audit={
            "default_intensity_to_pips": dict(DEFAULT_INTENSITY_TO_PIPS),
            "default_recroisement_bonus": DEFAULT_RECROISEMENT_BONUS_PIPS,
            "default_rejet_penalty": DEFAULT_REJET_PENALTY_PIPS,
            "n_combos_evaluated": len(all_combos),
            "horizon": horizon,
            "limit_per_pair_tf": limit,
        },
    ) if best_combo else CalibratedParams()

    return CalibrationReport(
        timestamp="",
        n_grid_combos_evaluated=len(all_combos),
        best_params=best_params,
        top_10_combos=top_10,
        metric_by_combo=metric_by_combo,
        audit={
            "method": "R8 grid search INTENSITY_TO_PIPS + bonuses",
            "doctrine": "R2 additif, R6 fail-open, R7, R8 auto-calibration, R9 audit, R10 paper-only",
            "constraint_R8": "FAIBLE ≤ MOYEN ≤ FORT ≤ EXTREME",
            "constraint_R10": f"max_combos={max_combos} (safety cap)",
        },
    )


__all__ = [
    "INTENSITY_GRID",
    "RECROISEMENT_BONUS_GRID",
    "REJET_PENALTY_GRID",
    "CalibratedParams",
    "CalibrationReport",
    "_valid_intensity_combo",
    "_safe_pearson",
    "_evaluate_combo_on_pair_tf",
    "_compute_pnl_native_with_params",
    "_grid_combos",
    "calibrate_intensity_to_pips",
]
