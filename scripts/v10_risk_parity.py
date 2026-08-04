"""
V10 — Risk Parity 2.0 (cross-pair correlation).

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase B prerequisite : allocation optimale entre paires.

Méthodologie :
  Risk parity = chaque paire contribue EQUALEMENT au risque du portefeuille.
  On calcule la matrice de corrélation des PnL par paire, puis on
  résout les poids qui égalisent la contribution au risque.

  Contribution risque_i = w_i * (Σ_w * Σ)_i / (w^T Σ w)

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_risk_parity.py
  .venv/Scripts/python.exe scripts/v10_risk_parity.py --json
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


def fetch_pnls_by_symbol(con: sqlite3.Connection) -> dict[str, list[float]]:
    """Récupère les PnL groupés par symbole.

    Note (2026-08-04 06:20 UTC) : la table `paper_trades` (track record réel)
    n'a PAS de colonne `symbol` — elle n'est donc pas utilisable pour une
    cross-pair correlation. On tente `v9_paper_log` (20 rows, a symbol + details)
    puis `v9_paper_trades`. Si aucun PnL par symbole n'est dispo → dict vide
    (R6 fail-open : le script retourne un message clair au lieu de crasher).

    Returns:
        dict {symbole: [PnL]} — vide si aucune donnée par symbole exploitable.
    """
    # 1. Essayer v9_paper_log (a symbol + details json possible)
    try:
        rows = con.execute(
            "SELECT symbol, details FROM v9_paper_log LIMIT 100"
        ).fetchall()
        by_symbol: dict[str, list[float]] = {}
        for sym, details in rows:
            if not sym:
                continue
            pnl = None
            if details:
                try:
                    import json as _json
                    d = _json.loads(details)
                    pnl = d.get("pnl_pips") or d.get("pnl") or d.get("pips")
                except Exception:
                    pnl = None
            if pnl is not None:
                try:
                    by_symbol.setdefault(sym, []).append(float(pnl))
                except (ValueError, TypeError):
                    pass
        if by_symbol:
            return by_symbol
    except sqlite3.OperationalError:
        pass

    # 2. Fallback : v9_paper_trades (symbol + tp_pips, pas de pnl net réel)
    try:
        rows = con.execute(
            "SELECT symbol, tp_pips FROM v9_paper_trades WHERE symbol IS NOT NULL"
        ).fetchall()
        by_symbol = {}
        for sym, tp in rows:
            if tp is not None:
                try:
                    by_symbol.setdefault(sym, []).append(float(tp))
                except (ValueError, TypeError):
                    pass
        return by_symbol
    except sqlite3.OperationalError:
        return {}


def compute_risk_parity(by_symbol: dict[str, list[float]]) -> dict[str, Any]:
    """Calcule les poids risk parity entre paires.

    Args:
        by_symbol: dict {symbole: [PnL]}

    Returns:
        dict avec poids, corrélations, contribution risque
    """
    # Garder les paires avec >= 5 trades
    symbols = [s for s, p in by_symbol.items() if len(p) >= 5]
    if len(symbols) < 2:
        return {"error": "Moins de 2 paires avec >= 5 trades", "n_symbols": len(symbols)}

    # Matrice de corrélation
    n = len(symbols)
    corr = [[0.0] * n for _ in range(n)]
    vols = []
    for i, s1 in enumerate(symbols):
        p1 = by_symbol[s1]
        vols.append(statistics.stdev(p1) if len(p1) > 1 else 0)
        for j, s2 in enumerate(symbols):
            if i == j:
                corr[i][j] = 1.0
                continue
            p2 = by_symbol[s2]
            # Corrélation de Pearson (aligner les longueurs)
            m = min(len(p1), len(p2))
            a, b = p1[:m], p2[:m]
            if len(a) < 2 or statistics.stdev(a) == 0 or statistics.stdev(b) == 0:
                corr[i][j] = 0.0
                continue
            corr[i][j] = statistics.correlation(a, b)

    # Risk parity : poids inversement proportionnel à la volatilité
    # (approximation : inverse-vol, puis normaliser)
    inv_vol = [1.0 / v if v > 0 else 0.0 for v in vols]
    total_inv = sum(inv_vol)
    weights = [w / total_inv for w in inv_vol] if total_inv > 0 else [1.0 / n] * n

    # Contribution au risque (approximation inverse-vol)
    contributions = [w * v for w, v in zip(weights, vols)]
    total_contrib = sum(contributions)
    contrib_pct = [c / total_contrib * 100 if total_contrib > 0 else 0 for c in contributions]

    # Corrélation moyenne par paire
    avg_corr = sum(corr[i][j] for i in range(n) for j in range(i + 1, n)) / max(1, n * (n - 1) / 2)

    alerts: list[str] = []
    if avg_corr > 0.7:
        alerts.append(f"🔴 Corrélation moyenne {avg_corr:.2f} > 0.7 (paires trop corrélées, diversification faible)")
    if max(weights) > 0.5:
        alerts.append(f"🔴 Poids max {max(weights):.2f} > 0.5 (concentration excessive)")

    return {
        "n_symbols": n,
        "symbols": symbols,
        "weights": {s: round(w, 4) for s, w in zip(symbols, weights)},
        "volatility": {s: round(v, 2) for s, v in zip(symbols, vols)},
        "risk_contribution_pct": {s: round(c, 1) for s, c in zip(symbols, contrib_pct)},
        "avg_correlation": round(avg_corr, 3),
        "correlation_matrix": {s1: {s2: round(corr[i][j], 3) for j, s2 in enumerate(symbols)} for i, s1 in enumerate(symbols)},
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" ⚖️  V10 Risk Parity 2.0 (cross-pair)"),
        BOLD("=" * 70),
        f"Paires            : {result['n_symbols']}",
        f"Corrélation moy   : {result['avg_correlation']:.3f}",
        "",
        BOLD("📊 Poids risk parity"),
    ]
    for s in result["symbols"]:
        out.append(
            f"  {s:>10}  poids={result['weights'][s]:.3f}  "
            f"vol={result['volatility'][s]:.1f}  "
            f"contrib_risque={result['risk_contribution_pct'][s]:.0f}%"
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
    parser = argparse.ArgumentParser(description="V10 Risk Parity 2.0")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        by_symbol = fetch_pnls_by_symbol(con)
    finally:
        con.close()

    result = compute_risk_parity(by_symbol)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())