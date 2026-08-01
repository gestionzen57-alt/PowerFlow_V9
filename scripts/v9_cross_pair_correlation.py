"""v9_cross_pair_correlation.py — Phase 69 motion CEO 48H.

Cross-pair correlation live : pearson, dynamic window.
Detecte regimes de correlation.

Auteur : Hermes (Phase 69 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.cross_pair")


def compute_returns(prices: list[float]) -> list[float]:
    """Returns simple sur prix."""
    if len(prices) < 2:
        return []
    returns = []
    for i in range(1, len(prices)):
        r = (prices[i] - prices[i - 1]) / prices[i - 1]
        returns.append(r)
    return returns


def pearson_correlation(x: list[float], y: list[float]) -> float:
    """Pearson correlation entre 2 series."""
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / (var_x * var_y) ** 0.5


def correlation_matrix(prices_dict: dict, window: int = 30) -> dict:
    """Matrice correlation rolling sur N derniers prix."""
    symbols = list(prices_dict.keys())
    if len(symbols) < 2:
        return {"error": "insufficient_symbols"}
    matrix = {}
    for s1 in symbols:
        matrix[s1] = {}
        for s2 in symbols:
            if s1 == s2:
                matrix[s1][s2] = 1.0
                continue
            p1 = prices_dict[s1][-window:]
            p2 = prices_dict[s2][-window:]
            r1 = compute_returns(p1)
            r2 = compute_returns(p2)
            if len(r1) != len(r2):
                matrix[s1][s2] = 0.0
                continue
            corr = pearson_correlation(r1, r2)
            matrix[s1][s2] = round(corr, 3)
    return {"symbols": symbols, "matrix": matrix}


def detect_correlation_regime(matrix: dict) -> dict:
    """Detecte si correlation globale augmente ou diminue."""
    if "matrix" not in matrix:
        return {"regime": "UNKNOWN"}
    pairs = []
    for s1, row in matrix["matrix"].items():
        for s2, corr in row.items():
            if s1 < s2:  # chaque paire une fois
                pairs.append(corr)
    if not pairs:
        return {"regime": "NO_PAIRS"}
    avg_corr = sum(pairs) / len(pairs)
    n_high = sum(1 for p in pairs if abs(p) > 0.7)
    n_low = sum(1 for p in pairs if abs(p) < 0.3)
    if avg_corr > 0.5:
        regime = "RISK_OFF"  # tout corrélé
    elif avg_corr > 0.3:
        regime = "NORMAL"
    elif avg_corr < -0.3:
        regime = "DIVERSIFIED"
    elif n_high > len(pairs) * 0.5:
        regime = "RISK_OFF"
    elif n_low > len(pairs) * 0.5:
        regime = "DIVERSIFIED"
    else:
        regime = "NORMAL"
    return {
        "regime": regime,
        "avg_corr": round(avg_corr, 3),
        "n_pairs": len(pairs),
        "n_high": n_high,
        "n_low": n_low,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 cross-pair correlation (Phase 69)",
    )
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("V9 CROSS-PAIR CORRELATION")
    print("=" * 70)
    if args.demo:
        prices_dict = {
            "GBPUSD": [1.30 + i * 0.001 for i in range(40)],
            "EURUSD": [1.08 + i * 0.0005 for i in range(40)],
            "USDJPY": [150.0 + i * 0.05 for i in range(40)],
        }
    else:
        prices_dict = {}
    if not prices_dict:
        print("No data")
        return 1
    matrix = correlation_matrix(prices_dict)
    regime = detect_correlation_regime(matrix)
    print(f"Symbols       : {matrix['symbols']}")
    print(f"Regime        : {regime['regime']}")
    print(f"Avg corr      : {regime.get('avg_corr', 0)}")
    print()
    print("Matrix :")
    for s1, row in matrix["matrix"].items():
        cells = " ".join(f"{row[s2]:+.3f}" for s2 in matrix["symbols"])
        print(f"  {s1:7s} : {cells}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
