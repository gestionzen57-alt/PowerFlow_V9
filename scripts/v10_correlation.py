"""
V10 — Matrice de corrélation inter-stratégies.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase D prerequisite : mesure la diversification du portefeuille.

Méthodologie :
  Calcule la matrice de corrélation entre les performances des
  principes (stratégies). Une corrélation moyenne basse = bonne
  diversification = Sharpe amplifié.

  Corrélation moyenne > 0.7 = paires trop corrélées (diversification
  faible). < 0.3 = bonne diversification.

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_correlation.py
  .venv/Scripts/python.exe scripts/v10_correlation.py --json
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


def compute_correlation(by_strategy: dict[str, list[float]]) -> dict[str, Any]:
    """Calcule la corrélation moyenne entre stratégies."""
    strategies = [s for s, p in by_strategy.items() if len(p) >= 5]
    if len(strategies) < 2:
        return {"error": "Moins de 2 stratégies avec ≥5 trades", "n_strategies": len(strategies)}

    n = len(strategies)
    corrs: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            a = by_strategy[strategies[i]]
            b = by_strategy[strategies[j]]
            m = min(len(a), len(b))
            x, y = a[:m], b[:m]
            if len(x) < 2 or statistics.stdev(x) == 0 or statistics.stdev(y) == 0:
                continue
            corrs.append(statistics.correlation(x, y))

    if not corrs:
        return {"error": "Aucune corrélation calculable", "n_strategies": n}

    avg_corr = sum(corrs) / len(corrs)

    alerts: list[str] = []
    if avg_corr > 0.7:
        alerts.append(f"🔴 Corrélation moyenne {avg_corr:.2f} > 0.7 (diversification faible)")
    if avg_corr > 0.5:
        alerts.append(f"⚠️  Corrélation moyenne {avg_corr:.2f} > 0.5 (diversification modérée)")

    return {
        "n_strategies": n,
        "n_pairs": len(corrs),
        "avg_correlation": round(avg_corr, 3),
        "min_correlation": round(min(corrs), 3),
        "max_correlation": round(max(corrs), 3),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 🔗 V10 Corrélation inter-stratégies"),
        BOLD("=" * 70),
        f"Stratégies        : {result['n_strategies']}",
        f"Paires comparées  : {result['n_pairs']}",
        "",
        BOLD("📊 Corrélation"),
        f"  Moyenne         : {result['avg_correlation']:.3f}",
        f"  Min             : {result['min_correlation']:.3f}",
        f"  Max             : {result['max_correlation']:.3f}",
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
    parser = argparse.ArgumentParser(description="V10 Corrélation inter-stratégies")
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

    result = compute_correlation(by_strategy)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())