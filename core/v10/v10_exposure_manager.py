"""
v10_exposure_manager.py — Cycle 16
Gestion de l'exposition nette multi-paire : plafonds, checks corrélation,
et autorisation d'ouverture de nouvelle position.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ExposureCheck:
    pair: str
    allowed: bool
    current_exposure: float
    max_exposure: float
    correlated_pairs: List[str]
    reason: str

    def as_dict(self) -> dict:
        return {
            "pair": self.pair,
            "allowed": self.allowed,
            "exposure": round(self.current_exposure, 4),
            "max": round(self.max_exposure, 4),
            "correlated": self.correlated_pairs,
            "reason": self.reason,
        }


class ExposureManager:
    """
    Contrôle l'exposition totale et par paire.
    """

    MAX_TOTAL_EXPOSURE = 0.20    # 20% du capital max
    MAX_PAIR_EXPOSURE = 0.05     # 5% par paire
    MAX_CORRELATED_OPEN = 2      # max 2 paires corrélées simultanées

    def __init__(self) -> None:
        self._positions: Dict[str, float] = {}    # pair -> exposure fraction
        self._corr_groups: Dict[str, List[str]] = {}  # pair -> liste paires corrélées

    def set_correlation_group(self, pair: str, correlated: List[str]) -> None:
        self._corr_groups[pair] = correlated

    def open_position(self, pair: str, exposure: float) -> None:
        self._positions[pair] = exposure

    def close_position(self, pair: str) -> None:
        self._positions.pop(pair, None)

    def total_exposure(self) -> float:
        return sum(self._positions.values())

    def check(self, pair: str, new_exposure: float) -> ExposureCheck:
        allowed = True
        reasons: List[str] = []
        correlated_open: List[str] = []

        # Vérif exposition totale
        projected_total = self.total_exposure() + new_exposure
        if projected_total > self.MAX_TOTAL_EXPOSURE:
            allowed = False
            reasons.append(f"total_exposure {projected_total:.2%}>{self.MAX_TOTAL_EXPOSURE:.0%}")

        # Vérif exposition par paire
        if new_exposure > self.MAX_PAIR_EXPOSURE:
            allowed = False
            reasons.append(f"pair_exposure {new_exposure:.2%}>{self.MAX_PAIR_EXPOSURE:.0%}")

        # Vérif corrélations
        correlated = self._corr_groups.get(pair, [])
        for cp in correlated:
            if cp in self._positions:
                correlated_open.append(cp)
        if len(correlated_open) >= self.MAX_CORRELATED_OPEN:
            allowed = False
            reasons.append(f"{len(correlated_open)} paires corrélées déjà ouvertes")

        return ExposureCheck(
            pair=pair,
            allowed=allowed,
            current_exposure=self.total_exposure(),
            max_exposure=self.MAX_TOTAL_EXPOSURE,
            correlated_pairs=correlated_open,
            reason="OK" if allowed else " | ".join(reasons),
        )

    def snapshot(self) -> dict:
        return {
            "positions": dict(self._positions),
            "total_exposure": round(self.total_exposure(), 4),
            "max_total": self.MAX_TOTAL_EXPOSURE,
            "slots_used": len(self._positions),
        }

    def reset(self) -> None:
        self._positions.clear()
        self._corr_groups.clear()
