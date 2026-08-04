"""
V10 — Portfolio risk budget (8% vol, 5% DD).

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase D prerequisite : alloue le risque entre composantes du portefeuille.

Méthodologie :
  Budget de risque = répartir le risque total (vol cible) entre les
  stratégies. Chaque stratégie reçoit un poids de risque tel que la
  somme des contributions au risque = vol cible.

  risk_budget_i = vol_cible * (vol_i / somme_vol)

  Vérifie aussi que Max DD attendu ≤ seuil.

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_risk_budget.py
  .venv/Scripts/python.exe scripts/v10_risk_budget.py --target-vol 0.08 --max-dd 0.05 --json
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


def fetch_strategy_returns(con: sqlite3.Connection) -> dict[str, list[float]]:
    """Récupère les PnL groupés par principe principal."""
    try:
        rows = con.execute(
            "SELECT principes_source, pips_net_of_spread FROM paper_trades "
            "WHERE closed_at IS NOT NULL AND pips_net_of_spread IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    by_strategy: dict[str, list[float]] = {}
    for src, pnl in rows:
        if not src:
            continue
        try:
            import json as _json
            principles = _json.loads(src)
        except (json.JSONDecodeError, TypeError):
            principles = []
        if isinstance(principles, list) and principles:
            strat = str(principles[0])
            by_strategy.setdefault(strat, []).append(float(pnl))
    return by_strategy


def compute_risk_budget(by_strategy: dict[str, list[float]], target_vol: float = 0.08, max_dd: float = 0.05) -> dict[str, Any]:
    """Calcule le budget de risque par stratégie.

    Args:
        by_strategy: dict {stratégie: [PnL]}
        target_vol: vol annualisée cible du portefeuille
        max_dd: Max DD cible (fraction du capital)

    Returns:
        dict avec vol par stratégie, budget risque, statut DD
    """
    strategies = [s for s, p in by_strategy.items() if len(p) >= 5]
    if not strategies:
        return {"error": "Aucune stratégie avec ≥5 trades"}

    # Vol annualisée par stratégie
    vol_by_strat = {}
    for s in strategies:
        pnls = by_strategy[s]
        std = statistics.stdev(pnls) if len(pnls) > 1 else 0
        vol_by_strat[s] = std * math.sqrt(252)

    # Budget de risque inversement proportionnel à la vol
    total_inv = sum(1.0 / v if v > 0 else 0.0 for v in vol_by_strat.values())
    risk_budget = {}
    for s in strategies:
        inv = 1.0 / vol_by_strat[s] if vol_by_strat[s] > 0 else 0.0
        risk_budget[s] = (inv / total_inv * target_vol) if total_inv > 0 else (target_vol / len(strategies))

    total_budget = sum(risk_budget.values())

    alerts: list[str] = []
    if total_budget > 0.15:
        alerts.append(f"🔴 Budget risque total {total_budget:.1%} > 15% (trop agressif)")
    if max(vol_by_strat.values()) > 1.0:
        alerts.append(f"🔴 Vol max stratégie {max(vol_by_strat.values()):.1%} > 100% (très volatile)")

    return {
        "n_strategies": len(strategies),
        "target_vol": target_vol,
        "max_dd_target": max_dd,
        "vol_by_strategy": {s: round(vol_by_strat[s], 3) for s in strategies},
        "risk_budget": {s: round(risk_budget[s], 4) for s in strategies},
        "total_risk_budget": round(total_budget, 4),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(f" 🎯 V10 Risk Budget (vol cible {result['target_vol']:.0%}, DD max {result['max_dd_target']:.0%})"),
        BOLD("=" * 70),
        f"Stratégies        : {result['n_strategies']}",
        f"Budget risque total : {result['total_risk_budget']:.1%}",
        "",
        BOLD("📊 Budget par stratégie"),
    ]
    for s in result["vol_by_strategy"]:
        out.append(
            f"  {s[:35]:<35}  vol={result['vol_by_strategy'][s]:.1%}  "
            f"budget={result['risk_budget'][s]:.2%}"
        )
    out.append("")
    out.append(BOLD("🚨 KILL CRITERIA"))
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
    parser = argparse.ArgumentParser(description="V10 Risk budget")
    parser.add_argument("--target-vol", type=float, default=0.08, help="Vol cible (0.08)")
    parser.add_argument("--max-dd", type=float, default=0.05, help="Max DD cible (0.05)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        by_strategy = fetch_strategy_returns(con)
    finally:
        con.close()

    result = compute_risk_budget(by_strategy, target_vol=args.target_vol, max_dd=args.max_dd)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())