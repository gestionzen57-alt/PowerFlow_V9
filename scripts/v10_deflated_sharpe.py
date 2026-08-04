"""
V10 — Deflated Sharpe Ratio (Bailey & López de Prado 2014).

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase A prerequisite : corrige pour le data-snoosing (50+ backtests).

Méthodologie :
  Le Sharpe "brut" affiché est biaisé si on a testé N stratégies.
  Le Deflated Sharpe Ratio (DSR) corrige pour :
  - Nombre de trials N
  - Skewness de la distribution des returns
  - Kurtosis
  - Horizon temporel T

  DSR > 1.0 = edge statistiquement significatif APRÈS correction
  pour le data-snoosing.

Doctrine :
  R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10-PROTÉGER CAPITAL.

Usage :
  .venv/Scripts/python.exe scripts/v10_deflated_sharpe.py
  .venv/Scripts/python.exe scripts/v10_deflated_sharpe.py --n-trials 50 --json
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"


def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


GREEN = lambda t: _color(t, "32")
RED = lambda t: _color(t, "31")
YELLOW = lambda t: _color(t, "33")
BOLD = lambda t: _color(t, "1")


def fetch_returns(con: sqlite3.Connection) -> list[float]:
    rows = con.execute(
        "SELECT pips_net_of_spread FROM paper_trades "
        "WHERE closed_at IS NOT NULL AND pips_net_of_spread IS NOT NULL"
    ).fetchall()
    return [float(r[0]) for r in rows if r[0] is not None]


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_obs: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> dict[str, float]:
    """Deflated Sharpe Ratio (Bailey & López de Prado 2014).

    Args:
        observed_sharpe: Sharpe brut observé
        n_trials: nombre de stratégies testées (data-snoosing adjustment)
        n_obs: nombre d'observations (trades)
        skewness: skewness des returns (default 0)
        kurtosis: kurtosis des returns (default 3 = normal)

    Returns:
        dict avec DSR, expected_max_sharpe, proba_sharpe>observed
    """
    if n_trials < 1:
        n_trials = 1
    if n_obs < 2:
        return {"dsr": 0.0, "expected_max": 0.0, "proba_higher": 1.0}

    # E[max(Z)] approximé par Bailey 2014 eq. 4
    # E[max(Z)] ≈ (1 - γ) * Φ^(-1)(1 - 1/N) + γ * Φ^(-1)(1 - 1/(N*e))
    # Approximation simplifiée :
    # E[max(Z)] ≈ sqrt(2 * log(N)) - (log(log(N)) + log(4π)) / (2 * sqrt(2 * log(N)))
    if n_trials > 1:
        log_n = math.log(n_trials)
        expected_max = math.sqrt(2 * log_n) - (math.log(log_n) + math.log(4 * math.pi)) / (
            2 * math.sqrt(2 * log_n)
        )
    else:
        expected_max = 0.0

    # Variance du Sharpe sous H0
    # var(SR) ≈ (1 + 0.5 * SR^2 - skew * SR + (kurt-3)/4 * SR^2) / (T-1)
    sr_var = (
        1
        + 0.5 * observed_sharpe**2
        - skewness * observed_sharpe
        + ((kurtosis - 3) / 4) * observed_sharpe**2
    ) / (n_obs - 1)

    sr_std = math.sqrt(max(sr_var, 1e-12))

    # DSR : proba que le vrai Sharpe > E[max(Z)] sous H0
    z_score = (observed_sharpe - expected_max) / sr_std
    # Approximation CDF normale (Abramowitz & Stegun)
    proba_higher = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))

    return {
        "dsr": round(proba_higher, 4),
        "expected_max_sharpe": round(expected_max, 4),
        "z_score": round(z_score, 3),
        "sr_std": round(sr_std, 4),
    }


def compute_stats(returns: list[float]) -> dict[str, float]:
    n = len(returns)
    if n < 2:
        return {"mean": 0, "std": 0, "sharpe": 0, "skewness": 0, "kurtosis": 3}
    mean = sum(returns) / n
    std = statistics.stdev(returns)
    sharpe = (mean / std) * math.sqrt(252) if std else 0.0
    # Skewness
    if std > 0:
        skew = sum(((x - mean) / std) ** 3 for x in returns) / n
        kurt = sum(((x - mean) / std) ** 4 for x in returns) / n
    else:
        skew, kurt = 0.0, 3.0
    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "sharpe": round(sharpe, 4),
        "skewness": round(skew, 4),
        "kurtosis": round(kurt, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V10 Deflated Sharpe Ratio")
    parser.add_argument("--n-trials", type=int, default=50, help="Nombre stratégies testées")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=5)
    try:
        returns = fetch_returns(con)
    finally:
        con.close()

    if not returns:
        print(RED("❌ Aucun return"))
        return 1

    stats = compute_stats(returns)
    dsr_result = deflated_sharpe_ratio(
        observed_sharpe=stats["sharpe"],
        n_trials=args.n_trials,
        n_obs=len(returns),
        skewness=stats["skewness"],
        kurtosis=stats["kurtosis"],
    )

    verdict = "GO" if dsr_result["dsr"] > 0.5 else ("HOLD" if dsr_result["dsr"] > 0.25 else "NO-GO")
    color = GREEN if verdict == "GO" else (YELLOW if verdict == "HOLD" else RED)

    result = {
        "n_observations": len(returns),
        "n_trials_corrected": args.n_trials,
        "stats": stats,
        "deflated_sharpe": dsr_result,
        "verdict": verdict,
        "interpretation": (
            f"DSR={dsr_result['dsr']:.4f} : probabilité que le Sharpe observé "
            f"({stats['sharpe']:.3f}) dépasse le Sharpe maximum attendu "
            f"sous H0 ({dsr_result['expected_max_sharpe']:.3f}) après "
            f"{args.n_trials} trials. Si > 0.5 = edge réel."
        ),
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        out = [
            BOLD("=" * 70),
            BOLD(" 📐 V10 Deflated Sharpe Ratio (Bailey & López de Prado 2014)"),
            BOLD("=" * 70),
            f"Observations       : {result['n_observations']}",
            f"Trials corrigés    : {result['n_trials_corrected']}",
            "",
            BOLD("📊 Statistiques returns"),
            f"  Mean             : {stats['mean']:+.4f}",
            f"  Std              : {stats['std']:.4f}",
            f"  Sharpe brut      : {stats['sharpe']:.3f}",
            f"  Skewness         : {stats['skewness']:.3f}",
            f"  Kurtosis         : {stats['kurtosis']:.3f}",
            "",
            BOLD("📐 Deflated Sharpe Ratio"),
            f"  DSR              : {dsr_result['dsr']:.4f}",
            f"  Expected max SR  : {dsr_result['expected_max_sharpe']:.3f} (sous H0)",
            f"  Z-score          : {dsr_result['z_score']:.3f}",
            f"  SR std           : {dsr_result['sr_std']:.4f}",
            "",
            color(f"  VERDICT : {verdict}"),
            "",
            f"  {result['interpretation']}",
            BOLD("=" * 70),
        ]
        print("\n".join(out))

    return 0 if verdict == "GO" else (1 if verdict == "NO-GO" else 0)


if __name__ == "__main__":
    raise SystemExit(main())