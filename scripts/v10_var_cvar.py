"""
V10 — VaR / CVaR (Value at Risk / Conditional VaR).

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase B prerequisite pour risk management institutionnel.

Méthodes :
  1. Paramétrique (variance-covariance, distribution normale)
  2. Historique (percentile empirique)
  3. Monte Carlo (bootstrap 10k)

VaR = perte max à un niveau de confiance (95%/99%) sur un horizon.
CVaR = perte moyenne au-delà du VaR (Expected Shortfall).

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_var_cvar.py
  .venv/Scripts/python.exe scripts/v10_var_cvar.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import random
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


def fetch_pnls(con: sqlite3.Connection) -> list[float]:
    rows = con.execute(
        "SELECT pips_net_of_spread FROM paper_trades "
        "WHERE closed_at IS NOT NULL AND pips_net_of_spread IS NOT NULL"
    ).fetchall()
    return [float(r[0]) for r in rows if r[0] is not None]


def percentile(data: list[float], p: float) -> float:
    s = sorted(data)
    idx = int(p / 100 * len(s))
    return s[min(idx, len(s) - 1)]


def compute_var_cvar(pnls: list[float], confidence: float = 0.95, n_mc: int = 10_000, seed: int = 42) -> dict[str, Any]:
    """Calcule VaR/CVaR par 3 méthodes.

    Args:
        pnls: liste des PnL par trade (pips)
        confidence: niveau de confiance (0.95 ou 0.99)
        n_mc: nombre simulations Monte Carlo
        seed: seed reproductibilité

    Returns:
        dict avec VaR/CVaR paramétrique, historique, Monte Carlo
    """
    if not pnls:
        return {"error": "Aucun PnL"}

    alpha = 1 - confidence
    n = len(pnls)
    mean = sum(pnls) / n
    std = statistics.stdev(pnls) if n > 1 else 0

    # 1. Paramétrique (normale)
    # VaR = -(mean + z_alpha * std), z_alpha = quantile normal
    # z_0.05 = 1.645, z_0.01 = 2.326
    z = {0.95: 1.645, 0.99: 2.326}.get(confidence, 1.645)
    var_param = -(mean + z * std)
    # CVaR paramétrique (normale) : E[X | X < VaR]
    # = -(mean - std * phi(z_alpha) / alpha)
    phi = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    cvar_param = -(mean - std * phi / alpha)

    # 2. Historique
    var_hist = -percentile(pnls, alpha * 100)
    tail = [p for p in pnls if p <= -var_hist]
    cvar_hist = -(sum(tail) / len(tail)) if tail else var_hist

    # 3. Monte Carlo (bootstrap)
    random.seed(seed)
    mc_samples = []
    for _ in range(n_mc):
        sample = [random.choice(pnls) for _ in range(n)]
        mc_samples.append(sum(sample) / n)  # PnL moyen par trade
    var_mc = -percentile(mc_samples, alpha * 100)
    mc_tail = [p for p in mc_samples if p <= -var_mc]
    cvar_mc = -(sum(mc_tail) / len(mc_tail)) if mc_tail else var_mc

    # Kill criteria
    alerts: list[str] = []
    if var_hist > 50:
        alerts.append(f"🔴 VaR 95% historique {var_hist:.1f} > 50 pips (risque excessif)")
    if cvar_hist > 100:
        alerts.append(f"🔴 CVaR 95% historique {cvar_hist:.1f} > 100 pips (tail risk)")

    return {
        "n_trades": n,
        "confidence": confidence,
        "mean_pnl": round(mean, 2),
        "std_pnl": round(std, 2),
        "var": {
            "parametrique": round(var_param, 2),
            "historique": round(var_hist, 2),
            "monte_carlo": round(var_mc, 2),
        },
        "cvar": {
            "parametrique": round(cvar_param, 2),
            "historique": round(cvar_hist, 2),
            "monte_carlo": round(cvar_mc, 2),
        },
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(f" 📉 V10 VaR/CVaR — confiance {result['confidence']*100:.0f}%"),
        BOLD("=" * 70),
        f"Trades            : {result['n_trades']}",
        f"Mean PnL/trade    : {result['mean_pnl']:+.2f} pips",
        f"Std PnL/trade     : {result['std_pnl']:.2f} pips",
        "",
        BOLD("VaR (perte max)"),
        f"  Paramétrique    : {result['var']['parametrique']:+.2f} pips",
        f"  Historique      : {result['var']['historique']:+.2f} pips",
        f"  Monte Carlo     : {result['var']['monte_carlo']:+.2f} pips",
        "",
        BOLD("CVaR (Expected Shortfall)"),
        f"  Paramétrique    : {result['cvar']['parametrique']:+.2f} pips",
        f"  Historique      : {result['cvar']['historique']:+.2f} pips",
        f"  Monte Carlo     : {result['cvar']['monte_carlo']:+.2f} pips",
        "",
        BOLD("🚨 KILL CRITERIA"),
    ]
    if result["kill_criteria"]:
        for a in result["kill_criteria"]:
            out.append(f"  {a}")
        out.append(RED(f"  ❌ VERDICT : {result['verdict']}"))
    else:
        out.append(GREEN("  ✅ Aucun kill criteria franchi"))
        out.append(GREEN(f"  ✅ VERDICT : {result['verdict']}"))
    out.append(BOLD("=" * 70))
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="V10 VaR/CVaR")
    parser.add_argument("--confidence", type=float, default=0.95, help="Niveau confiance (0.95/0.99)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        pnls = fetch_pnls(con)
    finally:
        con.close()

    result = compute_var_cvar(pnls, confidence=args.confidence)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())