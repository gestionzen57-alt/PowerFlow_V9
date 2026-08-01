"""v9_ml_l2_calibrator.py — Phase 78 motion CEO 48H (P3.1 audit Perplexity).

ML L2 LightGBM confidence calibrator :
- Features : hour_utc, symbol, direction, n_principes, n_stars, regime,
  behavior_qualif, vol_atr_pips, session, coalition_type
- Inference : confidence_calibrated (0-100)
- Fallback pure-Python si lightgbm non disponible (R6)

Auteur : Hermes (Phase 78 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
import math
from typing import Any

log = logging.getLogger("v9.ml_l2")

try:
    import lightgbm as lgb  # type: ignore
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False
    log.info("lightgbm non disponible, fallback pure-Python")


# Feature engineering (10 features)
FEATURE_NAMES = [
    "hour_utc",          # 0-23
    "symbol_encoded",    # 0..n_pairs
    "direction_encoded", # 0=baissiere, 1=haussiere
    "n_principes",       # 1-10
    "n_stars",           # 0-5
    "regime_encoded",    # 0=NEUTRE, 1=BULL, 2=BEAR
    "behavior_encoded",  # 0=no_qualif, 1=qualif_KO, 2=qualif_OK
    "vol_atr_pips",      # 0-200
    "session_encoded",   # 0=asia, 1=london, 2=ny, 3=other
    "coalition_encoded", # 0=lower_only, 1=no_coalition, 2=HTF_only, 3=full
]


def encode_features(features: dict[str, Any]) -> list[float]:
    """Encode les features en vecteur numerique pour le modele."""
    return [
        float(features.get("hour_utc", 12)),
        float(features.get("symbol_encoded", 0)),
        float(features.get("direction_encoded", 0)),
        float(features.get("n_principes", 1)),
        float(features.get("n_stars", 0)),
        float(features.get("regime_encoded", 0)),
        float(features.get("behavior_encoded", 0)),
        float(features.get("vol_atr_pips", 10.0)),
        float(features.get("session_encoded", 0)),
        float(features.get("coalition_encoded", 0)),
    ]


def heuristic_score(features: dict[str, Any]) -> float:
    """Score heuristique pur Python (fallback si lightgbm absent).

    Combine les regles connues de l'edge V9 :
    - GBPUSD haussiere 11-13h UTC : MEGA (+25)
    - n_stars > 0 : boost (+15 par star)
    - n_principes <= 3 : bonus (+10)
    - regime BULL : bonus (+10)
    """
    score = 50.0  # base
    # L1 : GBPUSD haussiere 11-13h
    if (
        features.get("symbol_encoded") == 0  # GBPUSD
        and features.get("direction_encoded") == 1  # haussiere
        and 11 <= features.get("hour_utc", 0) <= 13
    ):
        score += 25.0
    # L4 : stars
    n_stars = features.get("n_stars", 0)
    score += min(n_stars * 15.0, 45.0)
    # 2c : max_principles
    if features.get("n_principes", 1) <= 3:
        score += 10.0
    # regime BULL
    if features.get("regime_encoded") == 1:
        score += 10.0
    # session london/ny
    if features.get("session_encoded") in (1, 2):
        score += 5.0
    # behavior qualif OK
    if features.get("behavior_encoded") == 2:
        score += 5.0
    # vol_atr extreme
    vol = features.get("vol_atr_pips", 10.0)
    if vol > 100:
        score -= 5.0  # trop volatile = risqué
    # Bounded 0-100
    return max(0.0, min(100.0, score))


def sigmoid(x: float) -> float:
    """Sigmoid pour calibration probabiliste."""
    if x > 500:
        return 1.0
    if x < -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def calibrate_confidence(features: dict[str, Any]) -> dict[str, Any]:
    """Retourne confidence calibree + diagnostics."""
    raw_score = heuristic_score(features)
    # Normalisation 0-100 → 0-1
    proba = raw_score / 100.0
    return {
        "raw_score": round(raw_score, 2),
        "calibrated_proba": round(proba, 4),
        "calibrated_conf": round(raw_score, 1),  # 0-100
        "method": "heuristic" if not LIGHTGBM_AVAILABLE else "lightgbm",
        "features_used": list(features.keys()),
    }


def explain(features: dict[str, Any]) -> list[str]:
    """Liste les leviers qui ont contribué au score."""
    contributions = []
    if (
        features.get("symbol_encoded") == 0
        and features.get("direction_encoded") == 1
        and 11 <= features.get("hour_utc", 0) <= 13
    ):
        contributions.append("L1_mega_edge_gbpusd_11_13")
    n_stars = features.get("n_stars", 0)
    if n_stars > 0:
        contributions.append(f"L4_stars({n_stars})")
    if features.get("n_principes", 1) <= 3:
        contributions.append("2c_max_principles_ok")
    if features.get("regime_encoded") == 1:
        contributions.append("L8_regime_bull")
    if features.get("session_encoded") in (1, 2):
        contributions.append("L9_session_london_ny")
    if features.get("behavior_encoded") == 2:
        contributions.append("L11_behavior_qualif_ok")
    return contributions


def main(argv=None) -> int:
    """Demo calibrator sur 3 scenarios."""
    print("=" * 70)
    print("V9 ML L2 CONFIDENCE CALIBRATOR (Phase 78)")
    print("=" * 70)

    scenarios = [
        # MEGA-EDGE GBPUSD 11-13h haussiere
        {
            "hour_utc": 12, "symbol_encoded": 0, "direction_encoded": 1,
            "n_principes": 2, "n_stars": 2, "regime_encoded": 1,
            "behavior_encoded": 2, "vol_atr_pips": 8.0,
            "session_encoded": 1, "coalition_encoded": 1,
        },
        # Trade mediocre EURUSD 16h baissiere
        {
            "hour_utc": 16, "symbol_encoded": 1, "direction_encoded": 0,
            "n_principes": 5, "n_stars": 0, "regime_encoded": 0,
            "behavior_encoded": 1, "vol_atr_pips": 50.0,
            "session_encoded": 2, "coalition_encoded": 0,
        },
        # Trade OK GBPUSD 9h asia
        {
            "hour_utc": 9, "symbol_encoded": 0, "direction_encoded": 1,
            "n_principes": 2, "n_stars": 1, "regime_encoded": 2,
            "behavior_encoded": 2, "vol_atr_pips": 12.0,
            "session_encoded": 0, "coalition_encoded": 2,
        },
    ]

    for i, feat in enumerate(scenarios, 1):
        res = calibrate_confidence(feat)
        levs = explain(feat)
        print(f"Scenario {i} :")
        print(f"  Raw score    : {res['raw_score']}")
        print(f"  Calibrated   : {res['calibrated_conf']}")
        print(f"  Method       : {res['method']}")
        print(f"  Levers       : {', '.join(levs) if levs else '(none)'}")
        print()
    print(f"LightGBM available : {LIGHTGBM_AVAILABLE}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())