"""v9_meta_learning.py — Phase 46 motion CEO 48h autopilote.

Meta-learning : auto-tune hyperparams des leviers L1-L15.
Utilise grid search + Bayesian optimization simplifie pour trouver
les hyperparams optimaux.

Auteur : Hermes (Phase 46 motion CEO 48h, 31/07/2026)
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

log = logging.getLogger("v9.meta")

REPORT_PATH = Path(r"C:\projet\V9\data\meta_learning.json")


def _get_paper_trades_pips(db_path: Path) -> list[float]:
    """Retourne pips_net des trades fermes."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute("""
                SELECT pips_net FROM v9_paper_trades
                WHERE closed_at IS NOT NULL AND pips_net IS NOT NULL
            """).fetchall()
            return [float(r[0]) for r in rows]
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def evaluate_hyperparams(pips: list[float],
                            tp_atr_mult: float = 2.5,
                            sl_atr_mult: float = 0.8,
                            filter_threshold: float = 0.5,
                            position_factor: float = 1.0) -> dict:
    """Evalue un set d'hyperparams sur les trades existants.

    Approximation simplifiee : calcule le score comme une fonction
    des hyperparams et des stats de trades.
    """
    if not pips:
        return {"score": 0.0, "wr": 0.0, "expectancy": 0.0}
    n = len(pips)
    wins = sum(1 for p in pips if p > 0)
    wr = wins / n
    expectancy = sum(pips) / n
    # Score = weighted combination
    score = (wr * 0.5 + max(min(expectancy / 20, 1.0), -1.0) * 0.5)
    score *= position_factor
    if tp_atr_mult < sl_atr_mult * 2:
        score *= 0.5  # bad RR
    return {
        "score": round(score, 4),
        "wr": round(wr, 4),
        "expectancy": round(expectancy, 3),
        "n_trades": n,
    }


def grid_search(pips: list[float],
                  param_grid: dict[str, list[float]]) -> dict:
    """Grid search exhaustif sur les hyperparams."""
    best_score = -1.0
    best_params = {}
    n_evals = 0
    keys = list(param_grid.keys())
    values = [param_grid[k] for k in keys]
    # Cartesian product
    def _recurse(idx: int, current: dict):
        nonlocal best_score, best_params, n_evals
        if idx == len(keys):
            result = evaluate_hyperparams(pips, **current)
            n_evals += 1
            if result["score"] > best_score:
                best_score = result["score"]
                best_params = dict(current)
            return
        for v in values[idx]:
            current[keys[idx]] = v
            _recurse(idx + 1, current)
    if pips:
        _recurse(0, {})
    return {
        "best_score": round(best_score, 4),
        "best_params": best_params,
        "n_evals": n_evals,
    }


def bayesian_optimization(pips: list[float],
                            n_iterations: int = 50,
                            seed: int = 42) -> dict:
    """Bayesian optimization simplifie (random search + memorisation)."""
    if not pips:
        return {"best_score": 0.0, "best_params": {}, "n_evals": 0}
    random.seed(seed)
    best_score = -1.0
    best_params = {}
    history = []
    for i in range(n_iterations):
        # Random sample around current best (Gaussian)
        if best_params:
            params = {
                k: max(0.1, v + random.gauss(0, 0.1))
                for k, v in best_params.items()
            }
        else:
            params = {
                "tp_atr_mult": random.uniform(1.5, 4.0),
                "sl_atr_mult": random.uniform(0.5, 1.5),
                "filter_threshold": random.uniform(0.3, 0.8),
                "position_factor": random.uniform(0.5, 2.0),
            }
        result = evaluate_hyperparams(pips, **params)
        history.append({"i": i + 1, "score": result["score"],
                          "params": params})
        if result["score"] > best_score:
            best_score = result["score"]
            best_params = dict(params)
    return {
        "best_score": round(best_score, 4),
        "best_params": {k: round(v, 3) for k, v in best_params.items()},
        "n_evals": n_iterations,
        "history": history[-5:],  # last 5 only
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 meta-learning (Phase 46)",
    )
    parser.add_argument("--method", choices=["grid", "bayesian"],
                        default="bayesian")
    parser.add_argument("--n-iter", type=int, default=50)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    pips = _get_paper_trades_pips(Path(DB_PATH))
    print("=" * 70)
    print("PHASE 46 — META-LEARNING")
    print("=" * 70)
    print(f"N trades        : {len(pips)}")
    print(f"Method          : {args.method}")
    if not pips:
        print("Aucun trade ferme. Walk-forward 7j necessaire.")
        return 1
    if args.method == "grid":
        param_grid = {
            "tp_atr_mult": [2.0, 2.5, 3.0, 3.5],
            "sl_atr_mult": [0.6, 0.8, 1.0],
            "filter_threshold": [0.4, 0.5, 0.6],
            "position_factor": [1.0, 1.5],
        }
        result = grid_search(pips, param_grid)
    else:
        result = bayesian_optimization(pips, n_iterations=args.n_iter)
    print(f"Best score      : {result['best_score']}")
    print(f"Best params     : {result['best_params']}")
    print(f"Evaluations     : {result['n_evals']}")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Rapport         : {REPORT_PATH}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())