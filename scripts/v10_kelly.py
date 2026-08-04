"""
V10 — Kelly fraction ajusté au payoff.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase D prerequisite : taille de position optimale.

Méthodologie :
  Kelly fraction détermine la fraction optimale de capital à risquer
  par trade pour maximiser la croissance logarithmique.

  Kelly = (WR * avg_win - (1-WR) * avg_loss) / (avg_win / avg_loss)
  Ou, en termes de payoff :
  Kelly = (p * b - q) / b
    p = proba de gain (WR)
    b = payoff ratio (avg_win / avg_loss)
    q = 1 - p

  Fraction Kelly réelle (par sécurité) : souvent Kelly * 0.5 (half-Kelly).

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_kelly.py
  .venv/Scripts/python.exe scripts/v10_kelly.py --fraction 0.5 --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
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


def compute_kelly(pnls: list[float], fraction: float = 0.5) -> dict[str, Any]:
    """Calcule la fraction Kelly.

    Args:
        pnls: liste des PnL par trade
        fraction: fraction de Kelly à utiliser (0.5 = half-Kelly)

    Returns:
        dict avec Kelly brut, fraction, % capital recommandé
    """
    if not pnls:
        return {"error": "Aucun PnL"}

    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    wr = len(wins) / n if n > 0 else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0

    if avg_loss == 0:
        return {"error": "Aucune perte — Kelly indéfini", "n_trades": n}

    payoff = avg_win / avg_loss if avg_loss > 0 else 0.0
    p = wr
    b = payoff
    q = 1 - p

    # Kelly = (p*b - q) / b
    if b > 0:
        kelly_brut = (p * b - q) / b
    else:
        kelly_brut = 0.0

    # Clamp à [0, 1] (pas de levier optimal en fraction négative)
    kelly_clamped = max(0.0, min(1.0, kelly_brut))
    kelly_used = kelly_clamped * fraction

    alerts: list[str] = []
    if wr < 0.5:
        alerts.append(f"🔴 WR {wr:.1%} < 50% (stratégie perdante, Kelly ≤ 0)")
    if kelly_clamped <= 0:
        alerts.append(f"🔴 Kelly {kelly_clamped:.3f} ≤ 0 (aucun edge positif)")

    return {
        "n_trades": n,
        "win_rate": round(wr, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff_ratio": round(payoff, 3),
        "kelly_brut": round(kelly_brut, 4),
        "kelly_clamped": round(kelly_clamped, 4),
        "kelly_fraction": fraction,
        "kelly_recommended_pct": round(kelly_used * 100, 2),
        "interpretation": (
            f"Kelly brut {kelly_brut:.3f}, {fraction:.0%} Kelly = "
            f"risquer {kelly_used*100:.1f}% du capital par trade"
        ),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 🎰 V10 Kelly Criterion"),
        BOLD("=" * 70),
        f"Trades            : {result['n_trades']}",
        f"Win rate          : {result['win_rate']:.1%}",
        f"Avg win           : {result['avg_win']:+.2f} pips",
        f"Avg loss          : -{result['avg_loss']:.2f} pips",
        f"Payoff ratio      : {result['payoff_ratio']:.3f}",
        "",
        BOLD("📊 Kelly"),
        f"  Kelly brut      : {result['kelly_brut']:.3f}",
        f"  Kelly clampé    : {result['kelly_clamped']:.3f}",
        f"  Fraction        : {result['kelly_fraction']:.0%}",
        f"  Recommandation  : {result['kelly_recommended_pct']:.1f}% capital/trade",
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
    parser = argparse.ArgumentParser(description="V10 Kelly criterion")
    parser.add_argument("--fraction", type=float, default=0.5, help="Fraction Kelly (0.5 = half)")
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

    result = compute_kelly(pnls, fraction=args.fraction)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())