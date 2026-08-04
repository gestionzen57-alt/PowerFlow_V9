"""
V10 — Order Flow Imbalance / VPIN.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase C prerequisite : détecte la toxicité du flux d'ordres.

Méthodologie :
  Sans order book live, on approxime l'order flow imbalance (OFI) via
  le volume et la direction des bougies. Le VPIN (Volume-Synchronized
  Probability of Informed Trading) estime la probabilité qu'un trade
  soit initié par un informé (toxicité du flux).

  Approximation VPIN :
    VPIN ≈ |sum(buy_volume) - sum(sell_volume)| / total_volume

  On utilise le volume tick par bougie (forces_snapshots ou signals).

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_order_flow.py
  .venv/Scripts/python.exe scripts/v10_order_flow.py --json
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


def compute_order_flow(con: sqlite3.Connection) -> dict[str, Any]:
    """Calcule l'OFI/VPIN à partir des forces et des signaux."""
    # Récupère les directions des signals récents
    try:
        rows = con.execute(
            "SELECT direction FROM signals "
            "WHERE direction IN ('haussiere','baissiere') "
            "ORDER BY timestamp DESC LIMIT 500"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if not rows:
        return {"error": "Aucun signal directionnel", "n_signals": 0}

    n = len(rows)
    n_buy = sum(1 for r in rows if r[0] == 'haussiere')
    n_sell = sum(1 for r in rows if r[0] == 'baissiere')

    # OFI (Order Flow Imbalance) : (buy - sell) / (buy + sell)
    ofi = (n_buy - n_sell) / n if n > 0 else 0.0

    # VPIN approximation : |buy - sell| / total
    vpin = abs(n_buy - n_sell) / n if n > 0 else 0.0

    # Buy ratio
    buy_ratio = n_buy / n if n > 0 else 0.0

    alerts: list[str] = []
    if vpin > 0.6:
        alerts.append(f"🔴 VPIN {vpin:.2f} > 0.6 (flux très toxique, informé)")
    if abs(ofi) > 0.5:
        alerts.append(f"🔴 |OFI| {abs(ofi):.2f} > 0.5 (déséquilibre extrême)")

    return {
        "n_signals": n,
        "n_buy": n_buy,
        "n_sell": n_sell,
        "buy_ratio": round(buy_ratio, 3),
        "ofi": round(ofi, 3),
        "vpin": round(vpin, 3),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 🌊 V10 Order Flow Imbalance / VPIN"),
        BOLD("=" * 70),
        f"Signaux directionnels : {result['n_signals']}",
        f"  Buy (haussière)     : {result['n_buy']}",
        f"  Sell (baissière)    : {result['n_sell']}",
        "",
        BOLD("📊 Metrics"),
        f"  Buy ratio   : {result['buy_ratio']:.3f}",
        f"  OFI         : {result['ofi']:+.3f}",
        f"  VPIN        : {result['vpin']:.3f}",
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
    parser = argparse.ArgumentParser(description="V10 Order Flow / VPIN")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        result = compute_order_flow(con)
    finally:
        con.close()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())