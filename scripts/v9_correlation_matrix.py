"""v9_correlation_matrix.py — Phase 41A motion CEO 48h autopilote.

Matrice de correlation inter-symboles (pips_net).
Identifie les paires qui bougent ensemble (hedge possible) ou
opposees (diversification).

Auteur : Hermes (Phase 41A motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.corr")

REPORT_PATH = Path(r"C:\projet\V9\data\correlation_matrix.json")


def _get_pips_by_symbol(db_path: Path) -> dict[str, list[float]]:
    """Retourne pips_net par symbole."""
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT symbol, pips_net FROM v9_paper_trades
                WHERE closed_at IS NOT NULL AND pips_net IS NOT NULL
            """).fetchall()
            result = defaultdict(list)
            for r in rows:
                result[r["symbol"]].append(float(r["pips_net"]))
            return dict(result)
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return {}


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Correlation de Pearson entre deux series."""
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    xs = xs[:n]
    ys = ys[:n]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / n
    var_x = sum((x - mean_x) ** 2 for x in xs) / n
    var_y = sum((y - mean_y) ** 2 for y in ys) / n
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x * var_y) ** 0.5


def compute_correlation_matrix(db_path: Path) -> dict:
    """Calcule la matrice de correlation entre symboles."""
    by_symbol = _get_pips_by_symbol(db_path)
    symbols = sorted(by_symbol.keys())
    matrix = {}
    pairs = []
    if not symbols:
        return {"symbols": [], "matrix": {}, "pairs": []}
    for sym_a in symbols:
        matrix[sym_a] = {}
        for sym_b in symbols:
            if sym_a == sym_b:
                matrix[sym_a][sym_b] = 1.0
                continue
            r = _pearson(by_symbol[sym_a], by_symbol[sym_b])
            matrix[sym_a][sym_b] = round(r, 3) if r is not None else None
    # Paires interessantes
    for i, sym_a in enumerate(symbols):
        for j, sym_b in enumerate(symbols):
            if j <= i:
                continue
            r = matrix[sym_a][sym_b]
            if r is None:
                continue
            if abs(r) >= 0.7:
                tag = "HIGH_CORR"
            elif abs(r) >= 0.4:
                tag = "MEDIUM_CORR"
            elif abs(r) < 0.2:
                tag = "DIVERSIFYING"
            else:
                tag = "LOW_CORR"
            pairs.append({
                "a": sym_a, "b": sym_b, "r": r, "tag": tag,
            })
    pairs.sort(key=lambda p: abs(p["r"]), reverse=True)
    return {"symbols": symbols, "matrix": matrix, "pairs": pairs}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 correlation matrix (Phase 41A)",
    )
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    result = compute_correlation_matrix(Path(DB_PATH))

    print("=" * 70)
    print("PHASE 41A — CORRELATION MATRIX")
    print("=" * 70)
    print(f"Symboles : {len(result['symbols'])}")
    if not result["symbols"]:
        print("Aucun trade ferme.")
        return 1
    print(f"Paires analysees : {len(result['pairs'])}")
    print()
    print("TOP PAIRES (|r| desc) :")
    for p in result["pairs"][:10]:
        print(f"  {p['a']:8s} <-> {p['b']:8s}  r={p['r']:+.3f}  "
              f"[{p['tag']}]")

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