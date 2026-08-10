"""V10 Fatman Wave Predictor — détecteur de PRÉ-VAGUE (H7 Hermes / Z11 ZCode).

Signal 7 de la FATMAN BIBLE : entrée ANTICIPÉE avant divergence confirmée.
Concept : la compression sigma précède l'expansion directionnelle —
quand l'écart-type des scores Fatman se resserre (compression), le marché
se prépare à une vague ; le premier écart de compression annonce la
direction de la prochaine divergence.

Équivalent Elliott : entrée fin vague 4 (zone de compression) pour capter
la vague 5.

Doctrine V10 : R2 additif pur, R6 fail-open (historique trop court →
pas de pré-vague), R8 seuils surchargeables, R9 audit JSON, R10 compute
only (zéro ordre).

API :
    - `detect_pre_wave(sigma_history, window=10, ratio=0.60, min_history=20)`
      → PreWaveAlert {pre_wave, direction, sigma_min, sigma_recent,
                       compression_ratio, notes}

NOTE H7 : livraison Hermes prévue ; ce module fournit déjà la fondation
(fail-open) pour que Signal 7 puisse être branché immédiatement.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import List, Optional

# Seuils par défaut (R8 surchargeables) — calibrés sur sigma 0-100
PRE_WAVE_WINDOW = 10          # fenêtre récente de comparaison
PRE_WAVE_RATIO = 0.60         # sigma_recent <= ratio * sigma_historique → compression
PRE_WAVE_MIN_HISTORY = 20     # historique minimal pour éviter les faux positifs


@dataclass
class PreWaveAlert:
    """Alerte de pré-vague (compression sigma détectée)."""
    pre_wave: bool = False
    direction: str = "NONE"      # LONG / SHORT / NONE
    sigma_min: float = 0.0       # sigma minimum de la fenêtre récente
    sigma_recent: float = 0.0    # sigma moyen de la fenêtre récente
    sigma_hist: float = 0.0      # sigma moyen de l'historique complet
    compression_ratio: float = 0.0  # sigma_recent / sigma_hist
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pre_wave": self.pre_wave,
            "direction": self.direction,
            "sigma_min": round(self.sigma_min, 2),
            "sigma_recent": round(self.sigma_recent, 2),
            "sigma_hist": round(self.sigma_hist, 2),
            "compression_ratio": round(self.compression_ratio, 3),
            "notes": list(self.notes),
        }


def detect_pre_wave(
    sigma_history: List[float],
    *,
    window: int = PRE_WAVE_WINDOW,
    ratio: float = PRE_WAVE_RATIO,
    min_history: int = PRE_WAVE_MIN_HISTORY,
) -> PreWaveAlert:
    """Détecte une compression sigma annonciatrice de pré-vague.

    Args:
        sigma_history: série temporelle des sigma Fatman (0-100).
        window: fenêtre récente comparée à l'historique.
        ratio: seuil de compression (recent/hist <= ratio).
        min_history: minimum de points requis (R6 fail-open).

    Returns:
        PreWaveAlert — pre_wave=True si compression détectée.
        La direction est indéterminée à ce stade (la divergence n'est pas
        encore confirmée) → direction="NONE". Le caller (Signal 7) combine
        avec le gap Fatman pour orienter l'entrée.
    """
    clean = [float(s) for s in sigma_history if s is not None]
    clean = [s for s in clean if s > 0.0]
    if len(clean) < min_history:
        return PreWaveAlert(
            sigma_hist=_safe_mean(clean),
            notes=[f"historique trop court ({len(clean)}/{min_history})"],
        )
    if window <= 0 or ratio <= 0:
        return PreWaveAlert(
            sigma_hist=_safe_mean(clean),
            notes=["paramètres invalides (window/ratio ≤ 0)"],
        )

    hist_mean = _safe_mean(clean)
    recent = clean[-window:]
    recent_mean = _safe_mean(recent)
    sigma_min = min(recent)

    if hist_mean <= 0:
        return PreWaveAlert(notes=["sigma historique nul"])

    compression_ratio = recent_mean / hist_mean
    if compression_ratio <= ratio and sigma_min <= hist_mean * ratio:
        return PreWaveAlert(
            pre_wave=True,
            direction="NONE",  # orienté par le gap Fatman (Signal 7)
            sigma_min=sigma_min,
            sigma_recent=recent_mean,
            sigma_hist=hist_mean,
            compression_ratio=compression_ratio,
            notes=[f"compression détectée (ratio {compression_ratio:.2f} ≤ {ratio})"],
        )

    return PreWaveAlert(
        sigma_min=sigma_min,
        sigma_recent=recent_mean,
        sigma_hist=hist_mean,
        compression_ratio=compression_ratio,
        notes=[f"pas de compression (ratio {compression_ratio:.2f} > {ratio})"],
    )


def _safe_mean(values: List[float]) -> float:
    if not values:
        return 0.0
    try:
        return statistics.fmean(values) if len(values) > 1 else float(values[0])
    except Exception:
        return sum(values) / len(values)


__all__ = [
    "PreWaveAlert",
    "detect_pre_wave",
    "PRE_WAVE_WINDOW",
    "PRE_WAVE_RATIO",
    "PRE_WAVE_MIN_HISTORY",
]
