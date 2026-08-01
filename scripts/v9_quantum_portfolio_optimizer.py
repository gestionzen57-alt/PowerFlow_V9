"""v9_quantum_portfolio_optimizer.py — Phase 97 motion CEO 48H (Plan C).

Quantum-inspired portfolio optimizer (simulation QUBO / QAOA).
Random search + Sharpe-like objective. Sans QPU reel (R18 compliant).

Auteur : Hermes (Phase 97 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import logging
import math
import random
from typing import Any

log = logging.getLogger("v9.quantum_portfolio")

SQRT_252 = math.sqrt(252)  # annualisation


class Portfolio:
    """Portfolio simple avec poids (raw, non normalises)."""

    def __init__(self, weights: dict[str, float]) -> None:
        self.weights = weights

    def total(self) -> float:
        return sum(self.weights.values())

    def normalize(self) -> dict[str, float]:
        """Normalise les poids pour qu'ils somment a 1."""
        total = self.total()
        if total == 0:
            return {k: 0.0 for k in self.weights}
        return {k: v / total for k, v in self.weights.items()}


def compute_portfolio_sharpe(
    returns: dict[str, list[float]],
    weights: dict[str, float],
) -> float:
    """Sharpe annualise du portfolio (moyenne / std * sqrt(252))."""
    if not returns or not weights:
        return 0.0
    n_periods = min(len(r) for r in returns.values())
    if n_periods < 2:
        return 0.0
    # Calcule la serie de rendements du portfolio
    port_returns = []
    for t in range(n_periods):
        r = sum(
            weights.get(sym, 0.0) * returns[sym][t]
            for sym in returns
        )
        port_returns.append(r)
    mean = sum(port_returns) / len(port_returns)
    var = sum((r - mean) ** 2 for r in port_returns) / (len(port_returns) - 1)
    sd = math.sqrt(var)
    if sd < 1e-10:
        return 0.0
    return round(mean / sd * SQRT_252, 3)


def optimize_portfolio(
    returns: dict[str, list[float]],
    n_iterations: int = 100,
    seed: int = 42,
) -> dict[str, float]:
    """Optimise le portfolio via random search (QAOA-inspired).

    Returns : dict symbol -> weight (somme = 1.0).
    """
    if not returns:
        return {}
    rng = random.Random(seed)
    symbols = list(returns.keys())
    best_sharpe = -float("inf")
    best_weights = {s: 1.0 / len(symbols) for s in symbols}
    for _ in range(n_iterations):
        # Genere poids aleatoires (Dirichlet simplifie)
        raw = [rng.random() for _ in symbols]
        s = sum(raw)
        weights = {sym: w / s for sym, w in zip(symbols, raw)}
        sharpe = compute_portfolio_sharpe(returns, weights)
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = weights
    # Round les poids pour eviter les floats interminables
    return {k: round(v, 4) for k, v in best_weights.items()}


def main(argv=None) -> int:
    """Demo optimizer."""
    print("=" * 70)
    print("V9 QUANTUM PORTFOLIO OPTIMIZER (Phase 97)")
    print("=" * 70)
    returns = {
        "GBPUSD": [0.01, 0.02, -0.01, 0.03, 0.02, -0.02, 0.04],
        "EURUSD": [-0.01, 0.01, 0.02, -0.02, -0.01, 0.02, 0.01],
        "USDJPY": [0.005, -0.005, 0.01, 0.0, 0.005, -0.005, 0.0],
    }
    weights = optimize_portfolio(returns, n_iterations=200)
    print(f"Optimal weights :")
    for sym, w in weights.items():
        print(f"  {sym:7s} : {w*100:.2f}%")
    sharpe = compute_portfolio_sharpe(returns, weights)
    print(f"\nSharpe ratio   : {sharpe:.3f}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())