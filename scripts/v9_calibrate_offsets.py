"""v9_calibrate_offsets.py — Calibration empirique des bornes learning_offset.

Phase 14.2 §2 — corrige le « - » du bilan Phase 14 :
'Le mapping _compute_multiplier_from_wr n'est pas calibré sur données
live (poids heuristique, pas issu d'un grid search)'.

Ce script applique une grid search sur l'historique live résolu
(`decisions WHERE is_win IS NOT NULL AND source_type='live'`) et
propose les bornes optimales par direction (maximisation du Sharpe
ratio observé, i.e. WR - 0.5, normalisé par n).

Doctrine respectée :
- R18 : 0 LLM, lecture seule sur la DB.
- R6 : toute erreur DB -> exit 1 avec message, pas de plantage.
- R25' : propose des bornes, ne les écrit jamais dans le module.
  Activation = motion CEO explicite + édition manuelle du module.

Usage :
    python scripts/v9_calibrate_offsets.py                 # full run
    python scripts/v9_calibrate_offsets.py --direction haussiere  # 1 direction
    python scripts/v9_calibrate_offsets.py --output-json calib.json  # export
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import sqlite3

from core.v9.config import DB_PATH
from core.v9.db_schema import get_connection
from core.v9.learning_offset_applier import (
    LEARNING_OFFSET_BOUNDS_BY_DIRECTION,
    LEARNING_OFFSET_BOUNDS_FALLBACK,
    LEARNING_OFFSET_MULT_NEUTRAL,
    LEARNING_OFFSET_WR_BASELINE,
    _compute_multiplier_from_wr,
)


# Grille de bornes à tester (lo, hi). Recherche = O(grid^2 × directions).
BOUND_GRID = [
    (0.75, 1.10), (0.75, 1.15), (0.75, 1.20), (0.75, 1.25),
    (0.80, 1.10), (0.80, 1.15), (0.80, 1.20), (0.80, 1.25),
    (0.85, 1.10), (0.85, 1.15), (0.85, 1.20), (0.85, 1.25),
    (0.90, 1.10), (0.90, 1.15), (0.90, 1.20), (0.90, 1.25),
]

# Contrainte d'asymétrie (lo doit être < 1.0 et hi > 1.0).
VALID_PAIRS = [
    (lo, hi) for lo, hi in BOUND_GRID
    if lo < LEARNING_OFFSET_MULT_NEUTRAL < hi
]


def _score_bounds(bounds: tuple[float, float],
                  wr: float, n: int) -> float:
    """Score empirique d'une paire de bornes sur observation (wr, n).

    Score = sqrt(n) * |WR - baseline|_clamped * sign(magnitude_relative).
    Maximise la magnitude ajustée par n (proxy Sharpe).
    """
    lo, hi = bounds
    mult = _compute_multiplier_from_wr_with_bounds(wr, lo, hi)
    delta = mult - LEARNING_OFFSET_MULT_NEUTRAL
    # Composante 1 : magnitude signée (boost > 0, reduce < 0).
    # Composante 2 : pondération par n (sqrt = compromis signal/bruit).
    return math.sqrt(max(n, 1)) * delta


def _compute_multiplier_from_wr_with_bounds(observed_wr: float,
                                            lo: float, hi: float) -> float:
    """Comme _compute_multiplier_from_wr mais avec bornes paramétrables."""
    delta = observed_wr - LEARNING_OFFSET_WR_BASELINE
    max_mag = max(abs(lo - LEARNING_OFFSET_MULT_NEUTRAL),
                  abs(hi - LEARNING_OFFSET_MULT_NEUTRAL))
    delta = max(-max_mag, min(max_mag, delta))
    mult = LEARNING_OFFSET_MULT_NEUTRAL + delta
    return max(lo, min(hi, mult))


def _load_empirical_data() -> dict[str, tuple[float, int]]:
    """Lit `decisions` live résolues par direction.

    Returns: dict[direction -> (WR observé, n)].
    """
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT direction, "
                "       SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) AS wins, "
                "       COUNT(*) AS total "
                "FROM decisions "
                "WHERE source_type='live' AND is_win IS NOT NULL "
                "AND direction IS NOT NULL "
                "GROUP BY direction",
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:
        print(f"[ERREUR DB] {e}", file=sys.stderr)
        return {}

    out: dict[str, tuple[float, int]] = {}
    for r in rows:
        wins = int(r["wins"] or 0)
        total = int(r["total"] or 0)
        if total < 5:
            continue  # trop peu de signal (R30 palier 5)
        out[r["direction"]] = (wins / total, total)
    return out


def _optimize_direction(observed_wr: float, n: int) -> tuple[tuple[float, float], float]:
    """Grid search sur VALID_PAIRS. Retourne (bornes_optimales, score_max)."""
    best_bounds = LEARNING_OFFSET_BOUNDS_FALLBACK
    best_score = -math.inf
    for bounds in VALID_PAIRS:
        score = _score_bounds(bounds, observed_wr, n)
        if score > best_score:
            best_score = score
            best_bounds = bounds
    return best_bounds, best_score


def main() -> int:
    p = argparse.ArgumentParser(
        description="Phase 14.2 §2 — grid search bornes learning_offset par direction",
    )
    p.add_argument(
        "--direction", choices=["haussiere", "baissiere"], default=None,
        help="Filtre sur 1 direction (défaut: toutes)",
    )
    p.add_argument(
        "--output-json", type=Path, default=None,
        help="Export des résultats en JSON",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Moins de logs (juste le résultat final)",
    )
    args = p.parse_args()

    data = _load_empirical_data()
    if not data:
        print("[ERREUR] Aucune donnée empirique disponible. "
              "Vérifier que la DB contient des décisions résolues.", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"--- V9 calibrate_offsets — Phase 14.2 §2 ---")
        print(f"DB : {DB_PATH}")
        print(f"Directions trouvées : {list(data.keys())}")
        print()

    results: dict[str, dict] = {}
    directions_to_process = (
        [args.direction] if args.direction else
        ["haussiere", "baissiere"]
    )
    for direction in directions_to_process:
        if direction not in data:
            print(f"[SKIP] {direction} : pas assez de données empiriques (n<5)")
            continue
        wr, n = data[direction]
        optimal, score = _optimize_direction(wr, n)
        current = LEARNING_OFFSET_BOUNDS_BY_DIRECTION.get(
            direction, LEARNING_OFFSET_BOUNDS_FALLBACK,
        )
        results[direction] = {
            "observed_wr": wr,
            "observed_n": n,
            "current_bounds": list(current),
            "optimal_bounds": list(optimal),
            "current_score": _score_bounds(current, wr, n),
            "optimal_score": score,
            "delta_score": score - _score_bounds(current, wr, n),
        }
        if not args.quiet:
            print(f"Direction {direction}:")
            print(f"  Données : WR={wr:.1%} n={n}")
            print(f"  Bornes actuelles : {list(current)} (score={results[direction]['current_score']:.2f})")
            print(f"  Bornes optimales : {list(optimal)} (score={score:.2f})")
            delta = results[direction]["delta_score"]
            print(f"  Delta : {delta:+.2f} ({'AMÉLIORATION' if delta > 0 else 'régression'})")
            print()

    if args.output_json:
        args.output_json.write_text(
            json.dumps(results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if not args.quiet:
            print(f"Résultats exportés : {args.output_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
