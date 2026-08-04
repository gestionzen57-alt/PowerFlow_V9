"""
V10 — Slippage model (calibration vs bid-ask spread).

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase C prerequisite : modélise le slippage d'exécution.

Méthodologie :
  Le slippage = différence entre le prix d'exécution théorique (mid)
  et le prix réellement rempli. Sans broker live, on estime le slippage
  à partir du spread moyen + un facteur de volatilité.

  slippage_estimé = spread_moyen * slippage_factor
  slippage_factor typique : 0.5 (50% du spread) pour un ordre market.

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_slippage_model.py
  .venv/Scripts/python.exe scripts/v10_slippage_model.py --factor 0.5 --json
"""

from __future__ import annotations

import argparse
import json
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


def fetch_spreads(con: sqlite3.Connection) -> list[float]:
    """Récupère les spreads moyens des paper_trades."""
    try:
        rows = con.execute(
            "SELECT spread_pips FROM paper_trades WHERE spread_pips IS NOT NULL"
        ).fetchall()
        return [float(r[0]) for r in rows if r[0] is not None]
    except sqlite3.OperationalError:
        return []


def compute_slippage_model(spreads: list[float], factor: float = 0.5) -> dict[str, Any]:
    """Calcule le slippage estimé à partir du spread.

    Args:
        spreads: liste des spreads par trade (pips)
        factor: slippage factor (fraction du spread)

    Returns:
        dict avec spread moyen, slippage estimé, impact PnL
    """
    if not spreads:
        return {"error": "Aucun spread disponible"}

    n = len(spreads)
    spread_avg = statistics.mean(spreads)
    spread_med = statistics.median(spreads)
    spread_std = statistics.stdev(spreads) if n > 1 else 0

    slippage_est = spread_avg * factor
    # Impact sur un trade moyen (perte due au slippage)
    pnl_impact = slippage_est

    alerts: list[str] = []
    if slippage_est > 2.0:
        alerts.append(f"🔴 Slippage estimé {slippage_est:.2f} pips > 2 pips (trop élevé)")
    if spread_avg > 3.0:
        alerts.append(f"🔴 Spread moyen {spread_avg:.2f} pips > 3 pips (paires illiquides)")

    return {
        "n_trades": n,
        "spread_mean": round(spread_avg, 3),
        "spread_median": round(spread_med, 3),
        "spread_std": round(spread_std, 3),
        "slippage_factor": factor,
        "slippage_estimated_pips": round(slippage_est, 3),
        "pnl_impact_per_trade_pips": round(pnl_impact, 3),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 💹 V10 Slippage Model"),
        BOLD("=" * 70),
        f"Trades            : {result['n_trades']}",
        f"Spread moyen      : {result['spread_mean']} pips",
        f"Spread médian     : {result['spread_median']} pips",
        f"Spread std        : {result['spread_std']} pips",
        f"Slippage factor   : {result['slippage_factor']}",
        "",
        BOLD("📊 Estimation"),
        f"  Slippage estimé : {result['slippage_estimated_pips']} pips/trade",
        f"  Impact PnL       : {result['pnl_impact_per_trade_pips']} pips/trade",
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
    parser = argparse.ArgumentParser(description="V10 Slippage model")
    parser.add_argument("--factor", type=float, default=0.5, help="Slippage factor (0-1)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        spreads = fetch_spreads(con)
    finally:
        con.close()

    result = compute_slippage_model(spreads, factor=args.factor)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())