"""
V10 — Black-Litterman portfolio construction.

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase D prerequisite : combiner vues quantitatives + équilibre de marché.

Méthodologie :
  Black-Litterman combine l'équilibre de marché (prix implicites)
  avec des vues quantitatives (features V10) pour produire des poids
  de portefeuille optimaux.

  Sans données live complètes, on implémente une version simplifiée :
  - Équilibre = répartition égale (prior)
  - Vues = performance historique par stratégie (les principes V9)
  - Combinaison = prior pondéré + vues pondérées par confiance

  C'est un template réutilisable quand les données V10 réelles seront
  disponibles (après TA lecture CEO + track record).

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_black_litterman.py
  .venv/Scripts/python.exe scripts/v10_black_litterman.py --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
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


def fetch_principle_perf(con: sqlite3.Connection) -> dict[str, float]:
    """Récupère la performance par principe (via principes_source)."""
    try:
        rows = con.execute(
            "SELECT principes_source, pips_net_of_spread, is_win FROM paper_trades "
            "WHERE closed_at IS NOT NULL AND pips_net_of_spread IS NOT NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    # Map each trade to its first principle (simplification)
    perf_by_principle: dict[str, list[float]] = {}
    for src, pnl, _ in rows:
        if not src:
            continue
        # src is a JSON list of principle names
        try:
            import json as _json
            principles = _json.loads(src)
        except (json.JSONDecodeError, TypeError):
            principles = []
        if principles:
            first = principles[0] if isinstance(principles, list) else str(principles)
            perf_by_principle.setdefault(str(first), []).append(float(pnl))

    return {p: sum(v) for p, v in perf_by_principle.items() if len(v) >= 3}


def compute_black_litterman(perf_by_principle: dict[str, float]) -> dict[str, Any]:
    """Calcule les poids Black-Litterman simplifiés.

    Args:
        perf_by_principle: dict {principe: PnL total}

    Returns:
        dict avec poids équilibrés, poids vues, poids combinés
    """
    if not perf_by_principle:
        return {"error": "Aucune performance par principe (≥3 trades) disponible"}

    principles = list(perf_by_principle.keys())
    n = len(principles)

    # Prior : équilibre de marché = égalité
    prior_weight = 1.0 / n

    # Vues : performance normalisée (softmax-like sur PnL positif)
    # On normalise les PnL en poids [0,1]
    total_pnl = sum(perf_by_principle.values())
    view_weights = {
        p: (perf_by_principle[p] / total_pnl) if total_pnl > 0 else prior_weight
        for p in principles
    }

    # Combinaison : 50% prior + 50% vue
    combined = {
        p: 0.5 * prior_weight + 0.5 * view_weights[p]
        for p in principles
    }

    # Normaliser la somme à 1
    total = sum(combined.values())
    if total > 0:
        combined = {p: w / total for p, w in combined.items()}

    # Concentration (HHI)
    hhi = sum(w ** 2 for w in combined.values())

    alerts: list[str] = []
    if max(combined.values()) > 0.4:
        alerts.append(f"🔴 Poids max {max(combined.values()):.2f} > 40% (concentration excessive)")
    if hhi > 0.5:
        alerts.append(f"🔴 HHI {hhi:.2f} > 0.5 (portefeuille trop concentré)")

    return {
        "n_principes": n,
        "principes": principles,
        "prior_weights": {p: round(prior_weight, 4) for p in principles},
        "view_weights": {p: round(view_weights[p], 4) for p in principles},
        "combined_weights": {p: round(combined[p], 4) for p in principles},
        "hhi_concentration": round(hhi, 3),
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 🏛️  V10 Black-Litterman (simplifié)"),
        BOLD("=" * 70),
        f"Principes          : {result['n_principes']}",
        f"HHI concentration  : {result['hhi_concentration']}",
        "",
        BOLD("📊 Poids combinés (prior + vues)"),
    ]
    for p in result["principes"]:
        out.append(
            f"  {p[:35]:<35}  prior={result['prior_weights'][p]:.3f}  "
            f"vue={result['view_weights'][p]:.3f}  "
            f"combiné={result['combined_weights'][p]:.3f}"
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
    parser = argparse.ArgumentParser(description="V10 Black-Litterman")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        perf = fetch_principle_perf(con)
    finally:
        con.close()

    result = compute_black_litterman(perf)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())