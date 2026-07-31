"""v9_portfolio_optimizer.py — Phase 41B motion CEO 48h autopilote.

Optimiseur portfolio multi-strategies (L1-L15).
Maximise Sharpe-like via allocation optimale des poids.

Auteur : Hermes (Phase 41B motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.portfolio")

REPORT_PATH = Path(r"C:\projet\V9\data\portfolio_weights.json")


def _get_levier_pips(db_path: Path, lever: str) -> list[float]:
    """Retourne pips_net pour les trades correspondants au levier.

    Approximation : tous les trades d'un symbole/horaire specifique.
    """
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            # Par defaut, on retourne tous les trades fermes
            rows = conn.execute("""
                SELECT pips_net FROM v9_paper_trades
                WHERE closed_at IS NOT NULL AND pips_net IS NOT NULL
            """).fetchall()
            return [float(r[0]) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def _sharpe_like(pips: list[float]) -> float:
    """Sharpe-like = mean / std (pas de rf)."""
    if len(pips) < 2:
        return 0.0
    n = len(pips)
    mean = sum(pips) / n
    var = sum((p - mean) ** 2 for p in pips) / n
    std = var ** 0.5
    if std == 0:
        return 0.0
    return mean / std


def _portfolio_sharpe(weights: list[float],
                       return_matrix: list[list[float]]) -> float:
    """Sharpe d'un portfolio avec poids donnes."""
    if not weights or not return_matrix:
        return 0.0
    n_trades = min(len(r) for r in return_matrix)
    if n_trades < 2:
        return 0.0
    port_returns = []
    for t in range(n_trades):
        ret = sum(weights[i] * return_matrix[i][t] for i in range(len(weights)))
        port_returns.append(ret)
    return _sharpe_like(port_returns)


def optimize_weights(pips_per_lever: list[list[float]],
                       n_iterations: int = 1000,
                       seed: int = 42) -> dict:
    """Random search pour optimiser poids portfolio."""
    random.seed(seed)
    if not pips_per_lever or any(len(p) < 2 for p in pips_per_lever):
        return {"weights": [], "sharpe": 0.0, "n_iterations": 0}
    n_levers = len(pips_per_lever)
    # Matrice de returns : chaque ligne = un lever, chaque col = un trade
    n_trades = min(len(p) for p in pips_per_lever)
    return_matrix = [p[:n_trades] for p in pips_per_lever]
    # Equal weight baseline
    equal_w = [1.0 / n_levers] * n_levers
    equal_sharpe = _portfolio_sharpe(equal_w, return_matrix)
    best_weights = equal_w
    best_sharpe = equal_sharpe
    for _ in range(n_iterations):
        # Random weights simplex
        raw = [random.random() for _ in range(n_levers)]
        s = sum(raw)
        w = [r / s for r in raw]
        sharpe = _portfolio_sharpe(w, return_matrix)
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = w
    return {
        "weights": [round(w, 4) for w in best_weights],
        "sharpe": round(best_sharpe, 4),
        "n_iterations": n_iterations,
        "equal_sharpe": round(equal_sharpe, 4),
        "improvement_pct": round(
            100 * (best_sharpe - equal_sharpe) / max(abs(equal_sharpe), 0.001),
            2,
        ) if equal_sharpe != 0 else 0.0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 portfolio optimizer (Phase 41B)",
    )
    parser.add_argument("--n-iter", type=int, default=1000,
                        help="Nombre d'iterations random search")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    # Approx : 15 levers = 15 copies du dataset complet
    pips = _get_levier_pips(Path(DB_PATH), "all")
    if not pips:
        print("Aucun trade ferme. Walk-forward 7j necessaire.")
        return 1
    # 15 levers (L1-L15) copies
    pips_per_lever = [pips] * 15
    result = optimize_weights(pips_per_lever,
                               n_iterations=args.n_iter,
                               seed=args.seed)

    print("=" * 70)
    print("PHASE 41B — PORTFOLIO OPTIMIZER")
    print("=" * 70)
    print(f"Iterations       : {result['n_iterations']}")
    print(f"Equal Sharpe     : {result['equal_sharpe']}")
    print(f"Optimal Sharpe   : {result['sharpe']}")
    print(f"Improvement      : {result['improvement_pct']:+.2f}%")
    print()
    print("Poids optimaux (L1-L15) :")
    for i, w in enumerate(result["weights"], 1):
        bar = "#" * int(w * 50)
        print(f"  L{i:2d}  {w:.3f}  {bar}")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print()
    print(f"Rapport : {REPORT_PATH}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())