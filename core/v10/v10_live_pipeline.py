"""V10 Live Pipeline — Phase 22+ orchestration end-to-end.

Doctrine V10 (CEO phase 22+) :
  R1 : agit par défaut
  R2 : additif pur (0 import core/v9/)
  R6 : fail-open
  R7 : tests verts cumulés
  R8 : utilise R8-calibrated params (Phase 21+)
  R9 : audit metadata honnête
  R10 : zéro capital (calcule + observe, pas de trade)

Objectif Phase 22+ :
  Wrapper live qui orchestre TOUT en un seul pipeline :
    1. Charger multi-TF snapshots depuis DB (v10_compression_extension)
    2. Compute VSA signal multi-TF (v10_compression_extension.compute_vsa_signal)
       → utilise seuils RECALIBRÉS (v10_vsa_threshold_calibrator)
    3. Extract M30 VSA bias + state pour bonus solidarity
       (v10_market_context_global.compute_market_context M30 bonus)
    4. Charger thresholds par (paire, TF) depuis JSON
       (v10_bayesian_recalibrator.load_thresholds_pair_tf_json)
    5. Calcule market context (v10_market_context_global.compute_market_context)
       → avec seuils recalibrés + M30 bonus solidarity
    6. Compose signal final V10
       (v10_orchestrator.compose_signal_with_context)
    7. Audit complet JSON-sérialisable

API :
  - run_live_pipeline(pair, db_path, ...) → LivePipelineReport
  - LivePipelineReport dataclass avec tous les outputs
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from core.v10.v10_bayesian_recalibrator import (
    DEFAULT_THRESHOLDS,
    load_thresholds_pair_tf_json,
)

# Imports locaux (R2 additif pur)
from core.v10.v10_compression_extension import (
    TFVSAState,
    VSASignalReport,
    compute_tf_vsa_state,
    compute_vsa_signal,
    load_multi_tf_from_db,
)
from core.v10.v10_fatman_wave_predictor import (
    PreWaveAlert,
    detect_pre_wave,
)
from core.v10.v10_force_native_calibrator import (
    CalibratedParams,
    calibrate_intensity_to_pips,
)
from core.v10.v10_market_context_global import (
    MarketContext,
    compute_market_context,
)
from core.v10.v10_perplexity_sigma_oracle import (
    get_sigma_history,
)
from core.v10.v10_vsa_threshold_calibrator import (
    VSAThresholdParams,
    calibrate_vsa_thresholds,
)

# ─────────────────────────────────────────────────────────────────────
# CONSTANTES (recalibrables Phase 21+)
# ─────────────────────────────────────────────────────────────────────

# Seuils VSA defaults (Phase 11+ originaux) — recalibrés Phase 21+
DEFAULT_VSA_BULLISH_THRESHOLD = 0.30
DEFAULT_VSA_BEARISH_THRESHOLD = -0.30

# Pondérations multi-TF
DEFAULT_TF_WEIGHTS = {"H4": 0.50, "H1": 0.30, "M30": 0.20}

# Bonus M30 solidarity
DEFAULT_M30_SOLIDARITY_BONUS = 0.15

# Cache des calibrations (éviter recalibration à chaque appel)
_CALIBRATION_CACHE: Dict[str, Tuple[float, float]] = {}


# ─────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────

@dataclass
class LivePipelineReport:
    """Rapport live pipeline V10 (Phase 22+ end-to-end)."""
    timestamp: str = ""
    pair: str = ""
    n_snapshots_m30: int = 0
    n_snapshots_h1: int = 0
    n_snapshots_h4: int = 0
    vsa_signal: str = "NEUTRAL"  # BULLISH / BEARISH / NEUTRAL
    vsa_score_global: float = 0.0
    vsa_m30_aligns_h1: bool = False
    vsa_h4_extreme: bool = False
    m30_vsa_bias: str = "NEUTRAL"
    m30_vsa_state: str = "NEUTRAL"
    market_context_tradeable: bool = False
    market_context_score: float = 0.0
    market_context_block_reason: str = ""
    market_context_tradeable_pairs: List[str] = field(default_factory=list)
    thresholds_source: str = "default"  # "calibrated_v2" ou "default"
    vsa_thresholds: Tuple[float, float] = (0.30, -0.30)  # (bullish, bearish)
    intensity_calibrated: bool = False
    pre_wave: bool = False  # compression sigma détectée (ZCode API)
    pre_wave_direction: str = "NONE"  # orienté par gap Fatman (Signal 7)
    pre_wave_sigma_recent: float = 0.0
    pre_wave_sigma_hist: float = 0.0
    pre_wave_compression_ratio: float = 0.0
    watch_only: bool = False  # compression → skip trade, WATCH_ONLY (H-NEXT)
    audit: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────
# CHARGER SEUILS VSA RECALIBRÉS (Phase 21+)
# ─────────────────────────────────────────────────────────────────────

def get_vsa_thresholds(
    db_path: str = "data/v9_forces.db",
    *,
    use_calibrated: bool = True,
) -> Tuple[float, float]:
    """Charge seuils VSA recalibrés (Phase 21+) ou defaults.

    Args:
        db_path: chemin DB
        use_calibrated: True = utilise grid search Phase 21+; False = defaults

    Returns:
        (bullish_threshold, bearish_threshold)
    """
    if not use_calibrated:
        return (DEFAULT_VSA_BULLISH_THRESHOLD, DEFAULT_VSA_BEARISH_THRESHOLD)

    if "vsa_thresholds" in _CALIBRATION_CACHE:
        return _CALIBRATION_CACHE["vsa_thresholds"]

    try:
        rep = calibrate_vsa_thresholds(
            db_path,
            pairs=("EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"),
            timeframes=("M30", "H1", "H4"),
            limit=80,
            target_metric="wr_proxy_balanced",
            max_combos=15,
        )
        best = rep.best_params
        thresholds = (best.bullish_threshold, best.bearish_threshold)
        _CALIBRATION_CACHE["vsa_thresholds"] = thresholds
        return thresholds
    except Exception:
        return (DEFAULT_VSA_BULLISH_THRESHOLD, DEFAULT_VSA_BEARISH_THRESHOLD)


def get_intensity_calibrated(
    db_path: str = "data/v9_forces.db",
) -> Optional[CalibratedParams]:
    """Charge intensity_to_pips recalibrés (Phase 21+)."""
    if "intensity" in _CALIBRATION_CACHE:
        # Already calibrated as tuple (FAIBLE, MOYEN, FORT, EXTREME, rec_bonus, rej_pen)
        cached = _CALIBRATION_CACHE["intensity"]
        return CalibratedParams(
            intensity_to_pips={
                "FAIBLE": cached[0],
                "MOYEN": cached[1],
                "FORT": cached[2],
                "EXTREME": cached[3],
            },
            recroisement_bonus_pips=cached[4],
            rejet_penalty_pips=cached[5],
        )

    try:
        rep = calibrate_intensity_to_pips(
            db_path,
            pairs=("EURUSD", "GBPUSD", "AUDUSD"),
            timeframes=("M30", "H1"),
            limit=80,
            target_metric="delta_wr",
            max_combos=15,
        )
        best = rep.best_params
        _CALIBRATION_CACHE["intensity"] = (
            best.intensity_to_pips.get("FAIBLE", 1.5),
            best.intensity_to_pips.get("MOYEN", 3.0),
            best.intensity_to_pips.get("FORT", 5.0),
            best.intensity_to_pips.get("EXTREME", 8.0),
            best.recroisement_bonus_pips,
            best.rejet_penalty_pips,
        )
        return best
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# PIPELINE ORCHESTRATEUR
# ─────────────────────────────────────────────────────────────────────

def run_live_pipeline(
    pair: str,
    db_path: str = "data/v9_forces.db",
    *,
    timestamp: str = "",
    thresholds_pair_tf_path: Optional[str] = None,
    use_calibrated_thresholds: bool = True,
    use_calibrated_intensity: bool = True,
    m30_solidarity_bonus: float = DEFAULT_M30_SOLIDARITY_BONUS,
    limit_per_tf: int = 100,
    window_size: int = 20,
) -> LivePipelineReport:
    """Pipeline live Phase 22+ end-to-end.

    Args:
        pair: ex "GBPUSD"
        db_path: chemin v9_forces.db
        timestamp: ISO 8601 UTC
        thresholds_pair_tf_path: chemin JSON thresholds Phase 21+
        use_calibrated_thresholds: True = utilise seuils VSA recalibrés
        use_calibrated_intensity: True = utilise intensité recalibrée
        m30_solidarity_bonus: bonus M30 solidarity (default 0.15)
        limit_per_tf: nb candles max par TF
        window_size: fenêtre d'analyse VSA

    Returns:
        LivePipelineReport avec VSA signal + market context + audit
    """
    # 1. Charger multi-TF snapshots depuis DB (inclure D1 pour read_cycle)
    mtf = load_multi_tf_from_db(
        db_path, pair,
        tfs=("M30", "H1", "H4", "D1"),
        limit=limit_per_tf,
    )

    n_m30 = len(mtf.get("M30", []))
    n_h1 = len(mtf.get("H1", []))
    n_h4 = len(mtf.get("H4", []))

    # R6 fail-open : si pas assez de data → NEUTRAL
    if n_m30 < 5 or n_h1 < 5 or n_h4 < 5:
        return LivePipelineReport(
            timestamp=timestamp,
            pair=pair,
            n_snapshots_m30=n_m30,
            n_snapshots_h1=n_h1,
            n_snapshots_h4=n_h4,
            vsa_signal="NEUTRAL",
            audit={"error": "insufficient_data", "need": 5},
        )

    # 2. Seuils VSA recalibrés (Phase 21+) ou defaults
    bullish_thr, bearish_thr = get_vsa_thresholds(
        db_path, use_calibrated=use_calibrated_thresholds
    )
    thresholds_source = "calibrated_v2" if use_calibrated_thresholds else "default"

    # 3. Compute VSA signal multi-TF avec seuils recalibrés
    vsa_report = compute_vsa_signal(
        mtf["M30"],
        mtf["H1"],
        mtf["H4"],
        pair,
        timestamp=timestamp,
        window_size=window_size,
    )

    # 3.5. Pre-wave Fatman (H-NEXT / Z11) — détection compression sigma.
    # R6 fail-open : si historique sigma indisponible → pas de pré-vague.
    pre_wave = False
    pre_wave_direction = "NONE"
    pre_wave_sigma_recent = 0.0
    pre_wave_sigma_hist = 0.0
    pre_wave_compression_ratio = 0.0
    watch_only = False
    signal_score_multiplier = 1.0
    try:
        sigma_history = get_sigma_history(
            pair, "H1", n=10, db_path=db_path
        )
        if sigma_history:
            # ZCode API : min_history bas pour travailler sur 10 barres H1.
            alert: PreWaveAlert = detect_pre_wave(
                sigma_history, min_history=6, window=4
            )
            pre_wave = alert.pre_wave
            pre_wave_direction = alert.direction
            pre_wave_sigma_recent = alert.sigma_recent
            pre_wave_sigma_hist = alert.sigma_hist
            pre_wave_compression_ratio = alert.compression_ratio
            if alert.pre_wave:
                # Compression pré-vague → amplifier le signal (boost 1.15)
                signal_score_multiplier = 1.15
                watch_only = True  # WATCH_ONLY : compression → skip trade
    except Exception:  # R6 fail-open
        pre_wave = False

    # Apply recalibrated thresholds (override Phase 11+ defaults)
    # La compression pré-vague booste le score (H-NEXT).
    score_global = vsa_report.score_global * signal_score_multiplier
    if score_global > bullish_thr:
        vsa_signal = "BULLISH"
    elif score_global < bearish_thr:
        vsa_signal = "BEARISH"
    else:
        vsa_signal = "NEUTRAL"

    # 4. Extract M30 VSA bias + state (pour bonus solidarity)
    state_m30 = vsa_report.state_m30
    m30_vsa_bias = (
        "BULLISH" if state_m30.score_directionnel > 0.10
        else "BEARISH" if state_m30.score_directionnel < -0.10
        else "NEUTRAL"
    )
    m30_vsa_state = state_m30.last_state  # COMPRESSION/EXTENSION/NEUTRE

    # 5. Charger thresholds par (paire, TF) depuis JSON si fourni
    thresholds = None
    if thresholds_pair_tf_path:
        try:
            json_data = load_thresholds_pair_tf_json(thresholds_pair_tf_path)
            thresholds_by_ptf = json_data.get("thresholds_by_pair_tf", {})
            pair_thresholds = {
                k: v for k, v in thresholds_by_ptf.items()
                if k.startswith(f"{pair}_")
            }
            if pair_thresholds:
                first_key = sorted(pair_thresholds.keys())[0]
                thresholds = {pair: pair_thresholds[first_key]}
        except Exception:
            thresholds = None

    # 6. Compute market context (Couche 3) avec bonus M30 solidarity
    # R6 fail-open : compute_market_context attend CurrencyStrength reports,
    # pas forces_snapshots. Si format incompatible → tradeable=False mais
    # on garde le VSA signal.
    try:
        ctx = compute_market_context(
            mtf,
            timestamp=timestamp,
            thresholds=thresholds,
            m30_vsa_bias=m30_vsa_bias,
            h1_vsa_bias="NEUTRAL",  # pourrait être amélioré Phase 23+
            m30_vsa_state=m30_vsa_state,
            m30_solidarity_bonus=m30_solidarity_bonus,
        )
        market_context_tradeable = ctx.tradeable
        market_context_score = ctx.context_score
        market_context_block_reason = ctx.block_reason
        market_context_tradeable_pairs = list(ctx.tradeable_pairs)
    except Exception as exc:
        # R6 fail-open : compute_market_context incompatible avec forces_snapshots.
        # On continue avec VSA signal seul (Phase 22+ MVP).
        market_context_tradeable = False
        market_context_score = 0.0
        market_context_block_reason = (
            f"compute_market_context_incompatible_with_forces_snapshots: {exc}"
        )
        market_context_tradeable_pairs = []

    # 7. Intensity recalibrée (audit info)
    intensity_calib = get_intensity_calibrated(db_path) if use_calibrated_intensity else None

    return LivePipelineReport(
        timestamp=timestamp,
        pair=pair,
        n_snapshots_m30=n_m30,
        n_snapshots_h1=n_h1,
        n_snapshots_h4=n_h4,
        vsa_signal=vsa_signal,
        vsa_score_global=vsa_report.score_global,
        vsa_m30_aligns_h1=vsa_report.m30_aligns_h1,
        vsa_h4_extreme=vsa_report.h4_extreme_detected,
        m30_vsa_bias=m30_vsa_bias,
        m30_vsa_state=m30_vsa_state,
        market_context_tradeable=market_context_tradeable,
        market_context_score=market_context_score,
        market_context_block_reason=market_context_block_reason,
        market_context_tradeable_pairs=market_context_tradeable_pairs,
        thresholds_source=thresholds_source,
        vsa_thresholds=(bullish_thr, bearish_thr),
        intensity_calibrated=(intensity_calib is not None),
        pre_wave=pre_wave,
        pre_wave_direction=pre_wave_direction,
        pre_wave_sigma_recent=pre_wave_sigma_recent,
        pre_wave_sigma_hist=pre_wave_sigma_hist,
        pre_wave_compression_ratio=pre_wave_compression_ratio,
        watch_only=watch_only,
        audit={
            "method": "V10 Live Pipeline Phase 22+ end-to-end",
            "phases_integrated": [
                "Phase 9.1 forces natives",
                "Phase 11+ compression-extension VSA",
                "Phase 21+ R8 calibration INTENSITY_TO_PIPS",
                "Phase 21+ R8 calibration seuils VSA",
                "Phase 22 M30 bonus solidarity",
                "Phase 16 Couche 3 market context",
                "H-NEXT pre-wave Fatman (Z11 compression sigma)",
            ],
            "doctrine": "R1, R2 additif, R6 fail-open, R7, R8 auto-cal, R9 audit, R10",
            "pre_wave": {
                "detected": pre_wave,
                "direction": pre_wave_direction,
                "sigma_recent": round(pre_wave_sigma_recent, 3),
                "sigma_hist": round(pre_wave_sigma_hist, 3),
                "compression_ratio": round(pre_wave_compression_ratio, 3),
                "signal_score_multiplier": signal_score_multiplier,
                "watch_only": watch_only,
            },
            "tf_weights": DEFAULT_TF_WEIGHTS,
            "m30_solidarity_bonus": m30_solidarity_bonus,
            "window_size": window_size,
            "limit_per_tf": limit_per_tf,
            "phase_21_calibrated_intensity": (
                dict(intensity_calib.intensity_to_pips)
                if intensity_calib else None
            ),
        },
    )


# ─────────────────────────────────────────────────────────────────────
# CLI DEMO
# ─────────────────────────────────────────────────────────────────────

def demo_run_live_pipeline(
    db_path: str = "data/v9_forces.db",
    pairs: Tuple[str, ...] = ("EURUSD", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "USDJPY"),
    thresholds_pair_tf_path: Optional[str] = None,
    use_calibrated_thresholds: bool = False,
    use_calibrated_intensity: bool = False,
) -> List[LivePipelineReport]:
    """Run live pipeline sur N paires.

    Returns:
        Liste de LivePipelineReport par paire.
    """
    reports = []
    for pair in pairs:
        rep = run_live_pipeline(
            pair, db_path,
            timestamp="2026-08-05T09:00:00Z",
            thresholds_pair_tf_path=thresholds_pair_tf_path,
            use_calibrated_thresholds=use_calibrated_thresholds,
            use_calibrated_intensity=use_calibrated_intensity,
        )
        reports.append(rep)
    return reports


__all__ = [
    "DEFAULT_VSA_BULLISH_THRESHOLD",
    "DEFAULT_VSA_BEARISH_THRESHOLD",
    "DEFAULT_TF_WEIGHTS",
    "DEFAULT_M30_SOLIDARITY_BONUS",
    "LivePipelineReport",
    "get_vsa_thresholds",
    "get_intensity_calibrated",
    "run_live_pipeline",
    "demo_run_live_pipeline",
]
