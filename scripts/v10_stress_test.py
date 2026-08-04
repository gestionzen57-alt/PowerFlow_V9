"""
V10 — Stress Test 5 scénarios historiques.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase A prerequisite pour risk management institutionnel.

Scénarios :
  1. 2008 GFC (Lehman, -45% S&P)
  2. 2010 Flash Crash (intraday -9%)
  3. 2015 CHF Unpegging (EUR/CHF -30% en 1 jour)
  4. 2020 COVID Crash (-35% en 5 semaines)
  5. 2022 SNB + Russia/Ukraine (FX chaos)

Pour chaque scénario, on applique un stress multiplicatif au PnL
historique et on calcule : Sharpe stress, Max DD stress, Recovery.

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_stress_test.py
  .venv/Scripts/python.exe scripts/v10_stress_test.py --json
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


# 5 scénarios historiques (volatility multiplier + drawdown shock)
SCENARIOS = {
    "2008_GFC": {
        "description": "Global Financial Crisis (Lehman, AIG, FX carry unwind)",
        "vol_multiplier": 3.5,
        "dd_shock_pct": -45,
        "duration_days": 180,
    },
    "2010_FLASH_CRASH": {
        "description": "Flash Crash 06/05/2010 (intraday -9%, recovery 20min)",
        "vol_multiplier": 4.0,
        "dd_shock_pct": -25,
        "duration_days": 1,
    },
    "2015_CHF_UNPEGGING": {
        "description": "15/01/2015 SNB unpegs EUR/CHF (EURCHF -30% intraday)",
        "vol_multiplier": 5.0,
        "dd_shock_pct": -30,
        "duration_days": 1,
    },
    "2020_COVID_CRASH": {
        "description": "COVID-19 crash Feb-Mar 2020 (-35% S&P en 5 semaines)",
        "vol_multiplier": 3.0,
        "dd_shock_pct": -35,
        "duration_days": 35,
    },
    "2022_SNB_UKRAINE": {
        "description": "2022 SNB surprise + Russia invasion (FX chaos, -15% EM)",
        "vol_multiplier": 2.5,
        "dd_shock_pct": -20,
        "duration_days": 90,
    },
}


def fetch_pnls(con: sqlite3.Connection) -> list[float]:
    rows = con.execute(
        "SELECT pips_net_of_spread FROM paper_trades "
        "WHERE closed_at IS NOT NULL AND pips_net_of_spread IS NOT NULL"
    ).fetchall()
    return [float(r[0]) for r in rows if r[0] is not None]


def apply_stress(pnls: list[float], vol_mult: float, dd_shock_pct: float) -> dict[str, float]:
    """Applique stress : vol_multiplier amplifie chaque trade, dd_shock ajoute DD."""
    stressed = [p * vol_mult for p in pnls]
    # Ajouter DD shock comme une perte unique
    total_pnl = sum(stressed)
    dd_shock_pips = abs(dd_shock_pct) * 10  # approximation 1% = 10 pips
    stressed_with_shock = stressed + [-dd_shock_pips]

    # Compute Sharpe stressé
    n = len(stressed_with_shock)
    mean = sum(stressed_with_shock) / n
    std = statistics.stdev(stressed_with_shock) if n > 1 else 0
    sharpe = (mean / std) * math.sqrt(252) if std else 0.0

    # Max DD stressé
    running = peak = 0.0
    max_dd = 0.0
    for p in stressed_with_shock:
        running += p
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    return {
        "sharpe_stressed": round(sharpe, 3),
        "total_pnl_stressed": round(total_pnl, 1),
        "max_dd_stressed": round(max_dd, 1),
        "dd_shock_pips": round(dd_shock_pips, 0),
        "survives": total_pnl > -1000,  # Survie si > -1000 pips
    }


def run_stress_test(pnls: list[float]) -> dict[str, Any]:
    if not pnls:
        return {"error": "Aucun PnL"}

    results = []
    for name, scen in SCENARIOS.items():
        res = apply_stress(pnls, scen["vol_multiplier"], scen["dd_shock_pct"])
        results.append({
            "scenario": name,
            "description": scen["description"],
            "vol_multiplier": scen["vol_multiplier"],
            "dd_shock_pct": scen["dd_shock_pct"],
            **res,
        })

    n_survive = sum(1 for r in results if r["survives"])
    n_total = len(results)

    alerts: list[str] = []
    if n_survive < n_total:
        alerts.append(f"🔴 Stratégie perd >1000 pips sur {n_total - n_survive}/{n_total} scénarios")
    worst = max(results, key=lambda r: r["max_dd_stressed"])
    if worst["max_dd_stressed"] > 5000:
        alerts.append(f"🔴 Max DD worst case {worst['max_dd_stressed']:.0f} > 5000 pips ({worst['scenario']})")

    verdict = "GO" if not alerts else "NO-GO"

    return {
        "n_trades_base": len(pnls),
        "n_scenarios": n_total,
        "n_survives": n_survive,
        "scenarios": results,
        "kill_criteria": alerts,
        "verdict": verdict,
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 🌪️  V10 Stress Test — 5 scénarios historiques"),
        BOLD("=" * 70),
        f"Trades base       : {result['n_trades_base']}",
        f"Scénarios         : {result['n_scenarios']}",
        f"Survies           : {result['n_survives']}/{result['n_scenarios']}",
        "",
    ]
    for s in result["scenarios"]:
        col = GREEN if s["survives"] else RED
        out.append(BOLD(f"  📛 {s['scenario']}"))
        out.append(f"     {s['description']}")
        out.append(f"     Vol mult={s['vol_multiplier']}x, DD shock={s['dd_shock_pct']}%")
        out.append(col(f"     Sharpe stressé={s['sharpe_stressed']:+.3f} | "
                       f"MaxDD={s['max_dd_stressed']:.0f} pips | "
                       f"Survives={s['survives']}"))
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
    parser = argparse.ArgumentParser(description="V10 Stress Test")
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

    result = run_stress_test(pnls)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())