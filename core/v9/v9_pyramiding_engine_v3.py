"""v9_pyramiding_engine_v3.py — Phase 133 : Multi-Timeframe Pyramiding Boost.

Extension V3 du PyramidingEngine qui ajoute un boost selon l'alignement
multi-timeframe (MTF) : si la confluence est confirmée sur 3+ timeframes
(M5 + M15 + H1 par exemple), le sizing reçoit un boost additionnel ×1.2.

Mission CEO no-stop 03/08/2026 — sprint L11+.

Hypothèse : un trade Pyramiding V2 STARS qui a aussi une confirmation
MTF forte (3+ TF alignés) est statistiquement plus robuste. Boost ×1.2
sur sizing pour amplifier l'edge.

Gain projeté : 30-60 pips additionnels (extension V2).

Doctrine : R2 additif, R6 fail-open, R25' motion CEO.
"""
from __future__ import annotations

from typing import Sequence

from core.v9.kill_switches import get
from core.v9.v9_pyramiding_engine import (
    PyramidingEngineV2,
    pyramiding_boost_stars_enabled,
    pyramiding_boost_super_stars_enabled,
)

VERSION = "3.0"

# ── Configuration V3 ────────────────────────────────────────────────
MTF_BOOST_MULT = 1.2         # Boost si >= MTF_MIN_TIMEFRAMES
MTF_MIN_TIMEFRAMES = 3       # 3 TF minimum pour activer le boost
PYRAMIDING_V3_ENABLED_ENV = "V9_PYRAMIDING_V3_MTF_BOOST_ENABLED"


# ── Kill switch V3 ──────────────────────────────────────────────────
def pyramiding_v3_mtf_boost_enabled() -> bool:
    """Kill switch V9_PYRAMIDING_V3_MTF_BOOST_ENABLED — Phase 133 (03/08).

    Active le boost multi-timeframe additionnel (×1.2 si >=3 TF alignés).
    Defaut OFF (R25' strict motion CEO), R6 jamais bloquant.
    Additif (R2), 0 modif core/ partage (herite de PyramidingEngineV2).
    """
    return get(PYRAMIDING_V3_ENABLED_ENV, "0") == "1"


# ── Multi-timeframe boost evaluation ────────────────────────────────
def evaluate_mtf_boost(
    aligned_timeframes: Sequence[str],
    min_timeframes: int = MTF_MIN_TIMEFRAMES,
) -> dict:
    """Evalue le boost MTF selon le nombre de timeframes alignes.

    Args:
        aligned_timeframes : Liste des TF confirmes (ex: ["M5", "M15", "H1"]).
        min_timeframes : Nombre minimum de TF pour activer le boost (defaut 3).

    Returns:
        dict avec :
          - multiplier : float (1.0 si pas de boost, 1.2 sinon)
          - n_timeframes : int
          - active : bool
          - reason : str
          - leviers : list[str]
    """
    if not aligned_timeframes:
        return {
            "multiplier": 1.0,
            "n_timeframes": 0,
            "active": False,
            "reason": "no_timeframes_provided",
            "leviers": [],
        }
    n = len(set(aligned_timeframes))
    if n >= min_timeframes:
        return {
            "multiplier": MTF_BOOST_MULT,
            "n_timeframes": n,
            "active": True,
            "reason": f"mtf_boost_{n}tf_>=_{min_timeframes}",
            "leviers": [f"L17_pyramiding_v3_mtf_x1.2_{n}tf"],
        }
    return {
        "multiplier": 1.0,
        "n_timeframes": n,
        "active": False,
        "reason": f"insufficient_tfs_{n}_<_{min_timeframes}",
        "leviers": [],
    }


# ── V3 Pyramiding Engine (extension V2 + MTF boost) ────────────────
class PyramidingEngineV3(PyramidingEngineV2):
    """PyramidingEngine V3 = V2 + boost multi-timeframe.

    Herite de PyramidingEngineV2 (STARS/SUPER_STARS), ajoute le boost
    MTF ×1.2 si >= 3 TF alignes. Composition multiplicative avec V2.

    Additif (R2) : ne modifie pas V2, etend le comportement.
    """

    def __init__(self) -> None:
        super().__init__()

    def evaluate_v3(
        self,
        signal: dict,
        aligned_timeframes: Sequence[str] | None = None,
        context: dict | None = None,
    ) -> dict:
        """Evalue le sizing final = V2 base × MTF boost.

        Args:
            signal : dict compatible V2.evaluate() (memes cles)
            aligned_timeframes : Liste des TF confirmes (optionnel).

        Returns:
            dict V2 enrichi avec :
              - v3_mtf_multiplier : float (1.0 ou 1.2)
              - v3_mtf_active : bool
              - v3_mtf_n_timeframes : int
              - v3_mtf_leviers : list[str]
              - v3_final_multiplier : float (V2 multiplier × MTF boost)
        """
        # 1. Evaluation V2 (STARS/SUPER_STARS)
        v2_result = self.evaluate(signal, context)
        v2_mult = v2_result.get("multiplier", 1.0)

        # 2. Evaluation MTF boost
        if aligned_timeframes is None:
            mtf_result = {
                "multiplier": 1.0,
                "n_timeframes": 0,
                "active": False,
                "reason": "no_mtf_data",
                "leviers": [],
            }
        else:
            mtf_result = evaluate_mtf_boost(aligned_timeframes)

        mtf_mult = mtf_result["multiplier"] if pyramiding_v3_mtf_boost_enabled() else 1.0
        final_mult = v2_mult * mtf_mult

        # Composition des leviers
        leviers = list(v2_result.get("leviers", []))
        if mtf_result["active"] and pyramiding_v3_mtf_boost_enabled():
            leviers.extend(mtf_result["leviers"])

        return {
            **v2_result,
            "v3_mtf_multiplier": mtf_mult,
            "v3_mtf_active": mtf_result["active"] and pyramiding_v3_mtf_boost_enabled(),
            "v3_mtf_n_timeframes": mtf_result["n_timeframes"],
            "v3_mtf_leviers": mtf_result["leviers"],
            "v3_mtf_reason": mtf_result["reason"],
            "v3_final_multiplier": round(final_mult, 3),
            "v3_combo": v2_result.get("stars_level", "base") + (
                "_mtf" if mtf_result["active"] and pyramiding_v3_mtf_boost_enabled() else ""
            ),
            "v3_leviers_combined": leviers,
        }