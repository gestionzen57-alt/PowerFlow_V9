"""
V10 — Monte Carlo bootstrap sur distribution PnL.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase A prerequisite pour risk management institutionnel.

Méthodologie :
  1. Récupère tous les PnL clôturés depuis la DB
  2. Bootstrap N tirages avec remise (default 10 000)
  3. Pour chaque tirage :
     - Sharpe, PnL total, Max DD (running max equity)
  4. Statistiques : mean, std, percentiles 5/50/95, proba de ruine
  5. Sortie JSON pour CI/allocator

Doctrine :
  R1-AGIR (CEO mandate Go max)
  R6-EXPLIQUER (SQL traçable)
  R7-MESURER (KPIs auto)
  R9-AUDITABLE (reproductible)
  R10-PROTÉGER CAPITAL (zéro kill)

Usage :
  .venv/Scripts/python.exe scripts/v10_monte_carlo.py
  .venv/Scripts/python.exe scripts/v10_monte_carlo.py --n 10000 --json
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


def run_monte_carlo(pnls: list[float], n_sim: int = 10_000, seed: int = 42) -> dict[str, Any]:
    """Bootstrap N tirages avec remise, calcule stats distribution."""
    if not pnls:
        return {"error": "Aucun PnL", "n_total": 0}

    random.seed(seed)
    n_trades = len(pnls)

    sharpes: list[float] = []
    pnls_total: list[float] = []
    max_dds: list[float] = []

    for _ in range(n_sim):
        sample = [random.choice(pnls) for _ in range(n_trades)]
        mean = sum(sample) / n_trades
        std = statistics.stdev(sample) if n_trades > 1 else 0
        sharpe = (mean / std) * math.sqrt(252) if std else 0.0
        sharpes.append(sharpe)
        pnls_total.append(sum(sample))
        # Max DD
        running = peak = 0.0
        max_dd = 0.0
        for p in sample:
            running += p
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd
        max_dds.append(max_dd)

    def pctile(data: list[float], p: float) -> float:
        s = sorted(data)
        idx = int(p / 100 * len(s))
        return s[min(idx, len(s) - 1)]

    # Proba de ruine (Max DD > 50% du capital)
    ruin_threshold = 500  # pips (calibration conservateur)
    proba_ruine = sum(1 for dd in max_dds if dd > ruin_threshold) / n_sim * 100

    # Sharpe percentiles
    sharpe_5 = pctile(sharpes, 5)
    sharpe_50 = pctile(sharpes, 50)
    sharpe_95 = pctile(sharpes, 95)
    sharpe_mean = statistics.mean(sharpes)

    pnl_5 = pctile(pnls_total, 5)
    pnl_50 = pctile(pnls_total, 50)
    pnl_95 = pctile(pnls_total, 95)

    dd_95 = pctile(max_dds, 95)

    # Kill criteria
    alerts: list[str] = []
    if sharpe_50 < 0.5:
        alerts.append(f"🔴 Sharpe médian {sharpe_50:.2f} < 0.5 (edge absent)")
    if proba_ruine > 5:
        alerts.append(f"🔴 Proba ruine {proba_ruine:.1f}% > 5% (risque excessif)")
    if dd_95 > 2000:
        alerts.append(f"🔴 Max DD p95 {dd_95:.0f} > 2000 pips (stress)")
    if pnl_5 > 0:
        alerts.append(f"⚠️  PnL p5 {pnl_5:.0f} > 0 (trop optimiste — data snoosing?)")

    return {
        "n_total_trades": n_trades,
        "n_simulations": n_sim,
        "seed": seed,
        "sharpe": {
            "mean": round(sharpe_mean, 3),
            "median": round(sharpe_50, 3),
            "p5": round(sharpe_5, 3),
            "p95": round(sharpe_95, 3),
        },
        "pnl_total": {
            "p5": round(pnl_5, 1),
            "median": round(pnl_50, 1),
            "p95": round(pnl_95, 1),
        },
        "max_dd_p95": round(dd_95, 1),
        "proba_ruine_pct": round(proba_ruine, 2),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 🎲 V10 Monte Carlo Bootstrap (10 000 simulations)"),
        BOLD("=" * 70),
        f"Trades totaux     : {result['n_total_trades']}",
        f"Simulations       : {result['n_simulations']:,}",
        f"Seed              : {result['seed']} (reproductibilité R9)",
        "",
        BOLD("📊 Distribution Sharpe"),
        f"  Mean             : {result['sharpe']['mean']}",
        f"  Median (p50)     : {result['sharpe']['median']}",
        f"  P5 (worst 5%)    : {result['sharpe']['p5']}",
        f"  P95 (best 5%)    : {result['sharpe']['p95']}",
        "",
        BOLD("💰 Distribution PnL total (pips)"),
        f"  P5 (worst)       : {result['pnl_total']['p5']:+.0f}",
        f"  Median           : {result['pnl_total']['median']:+.0f}",
        f"  P95 (best)       : {result['pnl_total']['p95']:+.0f}",
        "",
        BOLD(f"📉 Max DD p95         : {result['max_dd_p95']:.0f} pips"),
        BOLD(f"☠️  Proba de ruine     : {result['proba_ruine_pct']:.2f}%"),
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
    parser = argparse.ArgumentParser(description="V10 Monte Carlo bootstrap")
    parser.add_argument("--n", type=int, default=10_000, help="Nombre simulations")
    parser.add_argument("--seed", type=int, default=42, help="Seed reproductibilité")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=5)
    try:
        pnls = fetch_pnls(con)
    finally:
        con.close()

    result = run_monte_carlo(pnls, n_sim=args.n, seed=args.seed)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())