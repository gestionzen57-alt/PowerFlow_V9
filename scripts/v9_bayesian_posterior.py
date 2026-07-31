"""v9_bayesian_posterior.py — Phase 23 motion CEO « EDGE FUND MAX ».

Bayesian posterior sur la probabilite que l'edge (WR reel) soit superieur
a un seuil donne, base sur Beta prior + donnees observees.

Posterior ~ Beta(alpha + wins, beta + losses)
P(WR > threshold | data) = integral de la posterior au-dessus du seuil.

Auteur : Hermes (Phase 23 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.bayesian_posterior")


def get_paper_trades_results(db_path: Path | str) -> tuple[int, int]:
    """Retourne (n_wins, n_losses) des paper trades fermes."""
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


def beta_pdf(x: float, alpha: float, beta: float) -> float:
    """Beta PDF (normalisee)."""
    if x <= 0 or x >= 1:
        return 0.0
    # B(alpha, beta) = Gamma(alpha) * Gamma(beta) / Gamma(alpha+beta)
    log_b = math.lgamma(alpha) + math.lgamma(beta) - math.lgamma(alpha + beta)
    log_pdf = (alpha - 1) * math.log(x) + (beta - 1) * math.log(1 - x) - log_b
    return math.exp(log_pdf)


def beta_cdf_approx(x: float, alpha: float, beta: float, n_steps: int = 1000) -> float:
    """CDF approximee par quadrature (simple Riemann sum)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    dx = x / n_steps
    total = 0.0
    for i in range(n_steps):
        xi = (i + 0.5) * dx
        total += beta_pdf(xi, alpha, beta)
    return total * dx


def bayesian_posterior(n_wins: int, n_losses: int, threshold: float = 0.60,
                       prior_alpha: float = 1.0, prior_beta: float = 1.0,
                       n_steps: int = 1000) -> dict:
    """Calcule la posterior Beta et P(WR > threshold).

    Prior faible (1, 1) = uniforme, equivalent a "je ne sais rien".
    """
    alpha_post = prior_alpha + n_wins
    beta_post = prior_beta + n_losses
    n = n_wins + n_losses

    if n == 0:
        return {"error": "no_data", "n_total": 0}

    # Mean et std de la posterior
    mean = alpha_post / (alpha_post + beta_post)
    var = (alpha_post * beta_post) / (
        (alpha_post + beta_post) ** 2 * (alpha_post + beta_post + 1)
    )
    std = math.sqrt(var)

    # P(WR > threshold) = 1 - CDF(threshold)
    cdf_threshold = beta_cdf_approx(threshold, alpha_post, beta_post, n_steps)
    prob_edge = 1.0 - cdf_threshold

    # Intervalle de credibilite 95%
    cdf_025 = beta_cdf_approx(0.025 + mean - 1.96 * std, alpha_post, beta_post, n_steps)
    cdf_975 = beta_cdf_approx(0.025 + mean + 1.96 * std, alpha_post, beta_post, n_steps)
    ci_low = 0.025 + mean - 1.96 * std
    ci_high = 0.025 + mean + 1.96 * std

    return {
        "n_wins": n_wins,
        "n_losses": n_losses,
        "n_total": n,
        "prior": {"alpha": prior_alpha, "beta": prior_beta},
        "posterior": {"alpha": alpha_post, "beta": beta_post},
        "posterior_mean_wr": round(mean, 4),
        "posterior_std_wr": round(std, 4),
        "threshold": threshold,
        "p_wr_above_threshold": round(prob_edge, 4),
        "ci_95_low": round(max(0, ci_low), 4),
        "ci_95_high": round(min(1, ci_high), 4),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 Bayesian posterior WR (Phase 23 quantique)",
    )
    parser.add_argument("--threshold", type=float, default=0.60,
                        help="Seuil WR (defaut 0.60 = 60%%)")
    parser.add_argument("--prior-alpha", type=float, default=1.0,
                        help="Beta prior alpha (defaut 1 = uniforme)")
    parser.add_argument("--prior-beta", type=float, default=1.0,
                        help="Beta prior beta (defaut 1 = uniforme)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    n_wins, n_losses = get_paper_trades_results(DB_PATH)
    result = bayesian_posterior(
        n_wins, n_losses,
        threshold=args.threshold,
        prior_alpha=args.prior_alpha,
        prior_beta=args.prior_beta,
    )

    print("=" * 70)
    print("PHASE 23 — BAYESIAN POSTERIOR (WR)")
    print("=" * 70)
    if "error" in result:
        print(f"Erreur : {result['error']}")
        return 1

    print(f"N wins / losses  : {result['n_wins']} / {result['n_losses']}")
    print(f"N total          : {result['n_total']}")
    print(f"Prior Beta({result['prior']['alpha']}, {result['prior']['beta']})")
    print(f"Posterior Beta({result['posterior']['alpha']}, {result['posterior']['beta']})")
    print()
    print(f"Posterior mean WR: {result['posterior_mean_wr'] * 100:.1f}%")
    print(f"Posterior std WR : {result['posterior_std_wr'] * 100:.1f}%")
    print(f"CI 95%           : [{result['ci_95_low'] * 100:.1f}%, "
          f"{result['ci_95_high'] * 100:.1f}%]")
    print()
    print(f"P(WR > {args.threshold * 100:.0f}%)       : "
          f"{result['p_wr_above_threshold'] * 100:.2f}%")
    print()
    if result["p_wr_above_threshold"] > 0.95:
        print(">>> Edge TRES PROBABLE (>95% confiance)")
    elif result["p_wr_above_threshold"] > 0.80:
        print(">>> Edge PROBABLE (>80% confiance)")
    else:
        print(">>> Edge INCERTAIN (<80% confiance)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())