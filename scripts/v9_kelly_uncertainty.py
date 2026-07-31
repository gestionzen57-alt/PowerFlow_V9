"""v9_kelly_uncertainty.py — Phase 25C motion CEO autopilote.

Kelly avec uncertainty bars sur WR (et non plus deterministe).
Utilise Monte Carlo pour estimer la distribution Kelly.

Auteur : Hermes (Phase 25C motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import logging
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.kelly_unc")


def get_paper_trades_results(db_path: Path | str) -> tuple[int, int]:
    db_path = Path(db_path)
    if not db_path.exists():
        return 0, 0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("""
                SELECT
                    SUM(CASE WHEN pips_net > 0 THEN 1 ELSE 0 END) AS n_wins,
                    SUM(CASE WHEN pips_net <= 0 THEN 1 ELSE 0 END) AS n_losses
                FROM v9_paper_trades
                WHERE closed_at IS NOT NULL
            """).fetchone()
            return int(row[0] or 0), int(row[1] or 0)
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return 0, 0


def beta_sample(alpha: float, beta: float, n: int = 1) -> list[float]:
    """Echantillonne depuis Beta(alpha, beta)."""
    import random
    return [random.betavariate(alpha, beta) for _ in range(n)]


def kelly_with_uncertainty(n_wins: int, n_losses: int,
                            reward_risk: float = 3.125,
                            fractional: float = 0.25,
                            n_sims: int = 1000,
                            seed: int = 42) -> dict:
    """Calcule distribution Kelly depuis posterior Beta(1+wins, 1+losses)."""
    import random
    if n_wins + n_losses == 0:
        return {"error": "no_data"}
    random.seed(seed)
    alpha_post = 1 + n_wins
    beta_post = 1 + n_losses

    kelly_samples = []
    wr_samples = []
    for _ in range(n_sims):
        wr_sample = random.betavariate(alpha_post, beta_post)
        wr_samples.append(wr_sample)
        if wr_sample > 0:
            kelly_full = (wr_sample * (reward_risk + 1) - 1) / reward_risk
            kelly_safe = max(0, kelly_full * fractional)
            kelly_samples.append(min(kelly_safe, 0.25))

    if not kelly_samples:
        return {"error": "no_positive_kelly"}
    kelly_samples.sort()
    return {
        "n_sims": n_sims,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "wr_mean": round(sum(wr_samples) / n_sims, 4),
        "kelly_mean": round(sum(kelly_samples) / n_sims, 4),
        "kelly_median": round(kelly_samples[n_sims // 2], 4),
        "kelly_p5": round(kelly_samples[n_sims // 20], 4),
        "kelly_p95": round(kelly_samples[n_sims - n_sims // 20], 4),
        "kelly_conservative": round(kelly_samples[n_sims // 20], 4),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 Kelly with uncertainty (Phase 25C)",
    )
    parser.add_argument("--tp", type=float, default=25.0)
    parser.add_argument("--sl", type=float, default=8.0)
    parser.add_argument("--fractional", type=float, default=0.25)
    parser.add_argument("--n-sims", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    n_wins, n_losses = get_paper_trades_results(DB_PATH)
    rr = args.tp / args.sl
    result = kelly_with_uncertainty(
        n_wins, n_losses, reward_risk=rr,
        fractional=args.fractional, n_sims=args.n_sims, seed=args.seed,
    )

    print("=" * 70)
    print("PHASE 25C — KELLY WITH UNCERTAINTY")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1
    print(f"N wins / losses    : {result['n_wins']} / {result['n_losses']}")
    print(f"WR posterior mean  : {result['wr_mean'] * 100:.2f}%")
    print(f"Kelly distribution :")
    print(f"  Mean             : {result['kelly_mean'] * 100:.2f}%")
    print(f"  Median           : {result['kelly_median'] * 100:.2f}%")
    print(f"  P5               : {result['kelly_p5'] * 100:.2f}%")
    print(f"  P95              : {result['kelly_p95'] * 100:.2f}%")
    print()
    print(f"RECOMMANDATION (Kelly conservative P5) : {result['kelly_conservative'] * 100:.2f}%")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())