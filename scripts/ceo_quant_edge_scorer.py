"""CEO-OPT3 : QUANT Edge Scorer — Z-score force + pre_wave_phase + regime HMM.

Score composite [0, 1] combinant :
  - Z-score force brute (currency strength delta)
  - Poids pre_wave_phase (COMPRESSION > NEUTRAL > DIVERGENCE)
  - Confirmateur régime HMM (TRENDING boost, RANGING malus)
  - Signal level (A1 > A2 > A3)

R6 fail-open par composante.
R10 : compute only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# Poids composantes CEO
W_FORCE   = 0.40   # Force delta Z-score
W_PHASE   = 0.25   # Pre-wave phase
W_REGIME  = 0.20   # Régime HMM
W_LEVEL   = 0.15   # Signal level

# Maps poids
PHASE_WEIGHT = {
    "COMPRESSION": 1.0,
    "NEUTRAL":     0.5,
    "DIVERGENCE":  0.1,   # watch_only = malus fort
}

REGIME_WEIGHT = {
    "TRENDING_UP":   1.0,
    "TRENDING_DOWN": 1.0,
    "RANGING":       0.3,
    "VOLATILE":      0.4,
    "NEWS":          0.1,
    "UNKNOWN":       0.5,
}

LEVEL_WEIGHT = {
    "A1": 1.0,
    "A2": 0.65,
    "A3": 0.30,
    "NONE": 0.0,
}


@dataclass
class EdgeScore:
    score: float                # Score composite [0, 1]
    grade: str                  # 'STRONG' | 'MODERATE' | 'WEAK' | 'NO_EDGE'
    z_force: float              # Z-score force delta
    phase_w: float              # Poids phase
    regime_w: float             # Poids régime
    level_w: float              # Poids level
    components: dict            # Détail audit
    go: bool                    # Score >= 0.55 → GO

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "grade": self.grade,
            "z_force": round(self.z_force, 3),
            "phase_w": self.phase_w,
            "regime_w": self.regime_w,
            "level_w": self.level_w,
            "go": self.go,
            "components": self.components,
        }


def _zscore(value: float, mean: float, std: float) -> float:
    """Z-score sécurisé."""
    if std < 1e-9:
        return 0.0
    return (value - mean) / std


def _sigmoid(x: float) -> float:
    """Normalise Z-score en [0,1]."""
    return 1.0 / (1.0 + math.exp(-x))


def compute_edge_score(
    force_delta: float,                    # Delta force base-quote actuel
    force_history: Optional[list[float]] = None,  # Historique 20 valeurs
    pre_wave_phase: str = "NEUTRAL",
    regime: str = "UNKNOWN",
    signal_level: str = "A2",
) -> EdgeScore:
    """Score QUANT composite CEO.

    R6 fail-open sur chaque composante.
    """
    # --- Composante force ---
    try:
        if force_history and len(force_history) >= 5:
            mean = sum(force_history) / len(force_history)
            variance = sum((x - mean) ** 2 for x in force_history) / len(force_history)
            std = math.sqrt(variance)
            z = _zscore(force_delta, mean, std)
        else:
            # Pas d'historique : Z approximatif par magnitude
            z = min(3.0, max(-3.0, force_delta / 10.0))
        z_force = z
        force_component = _sigmoid(z)       # [0, 1]
    except Exception:  # noqa: BLE001
        z_force = 0.0
        force_component = 0.5              # fail-open neutre

    # --- Composante phase ---
    phase_w = PHASE_WEIGHT.get(pre_wave_phase.upper(), 0.5)

    # --- Composante régime ---
    regime_w = REGIME_WEIGHT.get(regime.upper(), 0.5)

    # --- Composante level ---
    level_w = LEVEL_WEIGHT.get(signal_level.upper(), 0.3)

    # --- Score composite pondéré ---
    score = (
        W_FORCE  * force_component +
        W_PHASE  * phase_w +
        W_REGIME * regime_w +
        W_LEVEL  * level_w
    )
    score = max(0.0, min(1.0, score))

    # --- Grade ---
    if score >= 0.75:
        grade = "STRONG"
    elif score >= 0.55:
        grade = "MODERATE"
    elif score >= 0.35:
        grade = "WEAK"
    else:
        grade = "NO_EDGE"

    return EdgeScore(
        score=score,
        grade=grade,
        z_force=z_force,
        phase_w=phase_w,
        regime_w=regime_w,
        level_w=level_w,
        go=score >= 0.55,
        components={
            "force_component": round(force_component, 4),
            "phase_component": round(phase_w, 4),
            "regime_component": round(regime_w, 4),
            "level_component": round(level_w, 4),
        },
    )


__all__ = ["EdgeScore", "compute_edge_score", "PHASE_WEIGHT", "REGIME_WEIGHT", "LEVEL_WEIGHT"]
