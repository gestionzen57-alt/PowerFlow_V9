"""
V10 — Liquidity-adjusted Sharpe Ratio.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase B prerequisite : pénalise le Sharpe pour l'illiquidité.

Méthodologie :
  Le Sharpe brut ignore les coûts de transaction (slippage, spread).
  Le Liquidity-adjusted Sharpe soustrait le coût moyen par trade
  du PnL avant de calculer le ratio.

  Coût moyen = spread moyen + slippage estimé (pips)
  Sharpe_adj = (mean_pnl - cost) / std * sqrt(252)

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_liquidity_sharpe.py
  .venv/Scripts/python.exe scripts/v10_liquidity_sharpe.py --spread 1.5 --slippage 0.5 --json
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


def fetch_pnls(con: sqlite3.Connection) -> list[float]:
    rows = con.execute(
        "SELECT pips_net_of_spread FROM paper_trades "
        "WHERE closed_at IS NOT NULL AND pips_net_of_spread IS NOT NULL"
    ).fetchall()
    return [float(r[0]) for r in rows if r[0] is not None]


def compute_liquidity_sharpe(pnls: list[float], spread: float = 1.5, slippage: float = 0.5) -> dict[str, Any]:
    """Calcule Sharpe brut vs liquidity-adjusted.

    Args:
        pnls: liste des PnL par trade (pips)
        spread: spread moyen par trade (pips)
        slippage: slippage estimé par trade (pips)

    Returns:
        dict avec Sharpe brut, coût, Sharpe ajusté, edge decay
    """
    if not pnls:
        return {"error": "Aucun PnL"}

    n = len(pnls)
    mean = sum(pnls) / n
    std = statistics.stdev(pnls) if n > 1 else 0
    sharpe_brut = (mean / std) * math.sqrt(252) if std else 0.0

    cost_per_trade = spread + slippage
    mean_adj = mean - cost_per_trade
    sharpe_adj = (mean_adj / std) * math.sqrt(252) if std else 0.0

    # Edge decay dû aux coûts
    edge_decay = ((sharpe_brut - sharpe_adj) / abs(sharpe_brut) * 100) if sharpe_brut != 0 else 0.0

    alerts: list[str] = []
    if sharpe_adj < 0.5:
        alerts.append(f"🔴 Sharpe ajusté {sharpe_adj:.3f} < 0.5 (edge détruit par coûts)")
    if edge_decay > 30:
        alerts.append(f"🔴 Edge decay coûts {edge_decay:.0f}% > 30% (coûts trop élevés)")

    return {
        "n_trades": n,
        "spread_pips": spread,
        "slippage_pips": slippage,
        "cost_per_trade_pips": round(cost_per_trade, 2),
        "mean_pnl_brut": round(mean, 2),
        "mean_pnl_net": round(mean_adj, 2),
        "sharpe_brut": round(sharpe_brut, 3),
        "sharpe_liquidity_adjusted": round(sharpe_adj, 3),
        "edge_decay_pct": round(edge_decay, 1),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 💧 V10 Liquidity-adjusted Sharpe"),
        BOLD("=" * 70),
        f"Trades            : {result['n_trades']}",
        f"Spread/trade      : {result['spread_pips']} pips",
        f"Slippage/trade    : {result['slippage_pips']} pips",
        f"Coût total/trade  : {result['cost_per_trade_pips']} pips",
        "",
        BOLD("📊 Sharpe"),
        f"  Brut             : {result['sharpe_brut']:.3f}",
        f"  Liquidity-adj    : {result['sharpe_liquidity_adjusted']:.3f}",
        f"  Edge decay coûts : {result['edge_decay_pct']:.0f}%",
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
    parser = argparse.ArgumentParser(description="V10 Liquidity-adjusted Sharpe")
    parser.add_argument("--spread", type=float, default=1.5, help="Spread moyen (pips)")
    parser.add_argument("--slippage", type=float, default=0.5, help="Slippage estimé (pips)")
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

    result = compute_liquidity_sharpe(pnls, spread=args.spread, slippage=args.slippage)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())