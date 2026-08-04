"""
V10 — Volatility Targeting (scaling dynamique du risque).

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase B prerequisite : scaling de la position selon la volatilité.

Méthodologie :
  Vol targeting = ajuster la taille de position pour maintenir une
  volatilité annualisée cible (ex. 8%).

  scale = vol_cible / vol_réalisée
  Si vol_réalisée > vol_cible → réduire position (scale < 1)
  Si vol_réalisée < vol_cible → augmenter position (scale > 1)

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_vol_targeting.py
  .venv/Scripts/python.exe scripts/v10_vol_targeting.py --target 0.08 --json
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


def compute_vol_targeting(pnls: list[float], target_vol: float = 0.08) -> dict[str, Any]:
    """Calcule le scaling vol targeting.

    Args:
        pnls: liste des PnL par trade (pips)
        target_vol: volatilité annualisée cible (0.08 = 8%)

    Returns:
        dict avec vol réalisée, scale, position ajustée
    """
    if not pnls:
        return {"error": "Aucun PnL"}

    n = len(pnls)
    std = statistics.stdev(pnls) if n > 1 else 0
    # Vol annualisée (approx : std par trade * sqrt(252))
    vol_annualized = std * math.sqrt(252)

    # Scale = vol_cible / vol_réalisée
    scale = target_vol / vol_annualized if vol_annualized > 0 else 1.0
    # Clamp scale à [0.1, 3.0] pour éviter positions extrêmes
    scale = max(0.1, min(3.0, scale))

    # Position ajustée (base 1.0 lot)
    position_scale = scale

    alerts: list[str] = []
    if vol_annualized > 0.5:
        alerts.append(f"🔴 Vol annualisée {vol_annualized:.2f} > 50% (très volatile)")
    if scale < 0.2:
        alerts.append(f"🔴 Scale {scale:.2f} < 0.2 (position réduite à 20% — vol trop élevée)")

    return {
        "n_trades": n,
        "std_per_trade": round(std, 2),
        "vol_annualized": round(vol_annualized, 3),
        "target_vol": target_vol,
        "scale": round(scale, 3),
        "position_scale": round(position_scale, 3),
        "interpretation": (
            f"Vol réalisée {vol_annualized:.1%} vs cible {target_vol:.0%} → "
            f"scale {scale:.2f}x (position {'réduite' if scale < 1 else 'augmentée'})"
        ),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(f" 🎯 V10 Volatility Targeting (cible {result['target_vol']:.0%})"),
        BOLD("=" * 70),
        f"Trades            : {result['n_trades']}",
        f"Std/trade         : {result['std_per_trade']:.2f} pips",
        f"Vol annualisée    : {result['vol_annualized']:.1%}",
        f"Vol cible         : {result['target_vol']:.0%}",
        "",
        BOLD("📊 Scaling"),
        f"  Scale           : {result['scale']:.2f}x",
        f"  Position        : {result['position_scale']:.2f} lot (base 1.0)",
        f"  {result['interpretation']}",
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
    parser = argparse.ArgumentParser(description="V10 Volatility Targeting")
    parser.add_argument("--target", type=float, default=0.08, help="Vol annualisée cible (0.08 = 8%)")
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

    result = compute_vol_targeting(pnls, target_vol=args.target)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())