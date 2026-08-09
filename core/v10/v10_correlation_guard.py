"""
v10_correlation_guard.py — CYCLE 12 : Correlation Guard

C12-OPT4 : Bloque l'ouverture de positions corrélées (>0.70) qui
            dépassent la capacité nette du portefeuille.

Doctrine : R2 additif pur | R6 fail-open | R9 audit
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any


# ── Seuils ────────────────────────────────────────────────────────────────────
CORR_BLOCK_THRESHOLD: float = 0.70
MAX_CORRELATED_LOTS: float = 2.0   # max lots cumulés sur paires corrélées

# Matrice de corrélation statique simplifiée (extend dynamiquement)
DEFAULT_CORR_MATRIX: dict[tuple[str, str], float] = {
    ("EURUSD", "GBPUSD"): 0.80,
    ("EURUSD", "EURGBP"): -0.60,
    ("GBPUSD", "GBPJPY"): 0.75,
    ("USDJPY", "EURJPY"): 0.72,
    ("XAUUSD", "XAGUSD"): 0.85,
    ("EURUSD", "USDCHF"): -0.90,
}


@dataclass
class CorrelationGuardResult:
    allowed: bool = True
    block_reason: str = ""
    correlated_pairs: list = field(default_factory=list)
    net_exposure: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "block_reason": self.block_reason,
            "correlated_pairs": self.correlated_pairs,
            "net_exposure": self.net_exposure,
        }


def check_correlation(
    new_pair: str,
    new_lots: float,
    open_positions: dict[str, float],  # {pair: lots}
    corr_matrix: dict | None = None,
) -> CorrelationGuardResult:
    """
    Vérifie si l'ajout de new_pair/new_lots viole les règles de corrélation.

    Args:
        new_pair       : paire à ouvrir (ex: 'EURUSD')
        new_lots       : taille de la position
        open_positions : positions actuellement ouvertes {pair: lots}
        corr_matrix    : matrice de corrélation custom (optionnel)
    """
    result = CorrelationGuardResult()
    if corr_matrix is None:
        corr_matrix = DEFAULT_CORR_MATRIX

    try:
        cumulated = new_lots
        for open_pair, open_lots in open_positions.items():
            # Cherche corr dans les deux sens
            corr = corr_matrix.get((new_pair, open_pair)) or \
                   corr_matrix.get((open_pair, new_pair)) or 0.0
            if abs(corr) >= CORR_BLOCK_THRESHOLD:
                result.correlated_pairs.append(
                    {"pair": open_pair, "corr": corr, "lots": open_lots}
                )
                cumulated += open_lots

        result.net_exposure = round(cumulated, 4)

        if cumulated > MAX_CORRELATED_LOTS:
            result.allowed = False
            result.block_reason = (
                f"CORR_OVERLOAD net_lots={cumulated:.2f}>{MAX_CORRELATED_LOTS} "
                f"pairs={[p['pair'] for p in result.correlated_pairs]}"
            )

    except Exception as e:  # R6 fail-open
        warnings.warn(f"[C12] CorrelationGuard error (fail-open): {e}")
        result.allowed = True  # fail-open = laisser passer
        result.block_reason = f"ERROR_FAIL_OPEN: {e}"

    return result
