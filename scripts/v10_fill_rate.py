"""
V10 — Fill rate (paper vs live).

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase C prerequisite : mesure le taux de remplissage des ordres.

Méthodologie :
  Sans broker live, on estime le fill rate à partir de la cohérence
  du pipeline : combien de signaux directionnels aboutissent à une
  décision exploitable. Un fill rate < 70% indique un problème
  d'exécution ou de slippage.

  fill_rate_estime = decisions_exploitables / signals_directionnels

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_fill_rate.py
  .venv/Scripts/python.exe scripts/v10_fill_rate.py --json
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


def compute_fill_rate(con: sqlite3.Connection) -> dict[str, Any]:
    """Estime le fill rate à partir de la cohérence du pipeline."""
    # Signaux directionnels (candidats à l'exécution)
    try:
        n_dir = con.execute(
            "SELECT COUNT(*) FROM signals WHERE direction IN ('haussiere','baissiere')"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        n_dir = 0

    # Décisions avec action (exploitables / exécutées)
    try:
        n_actions = con.execute(
            "SELECT COUNT(*) FROM decisions WHERE action IS NOT NULL AND action != 'aucune_action'"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        n_actions = 0

    if n_dir == 0:
        return {"error": "Aucun signal directionnel", "n_dir": 0}

    fill_rate = (n_actions / n_dir) * 100 if n_dir > 0 else 0.0

    alerts: list[str] = []
    if fill_rate < 70:
        alerts.append(f"🔴 Fill rate {fill_rate:.0f}% < 70% (exécution inefficace)")
    if fill_rate > 130:
        alerts.append(f"⚠️  Fill rate {fill_rate:.0f}% > 130% (décompte incohérent)")

    return {
        "n_signals_directionnels": n_dir,
        "n_decisions_action": n_actions,
        "fill_rate_pct": round(fill_rate, 1),
        "target_min_pct": 70,
        "kill_criteria": alerts,
        "verdict": "GO" if not alerts else "NO-GO",
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" 📦 V10 Fill Rate"),
        BOLD("=" * 70),
        f"Signaux directionnels : {result['n_signals_directionnels']}",
        f"Décisions avec action  : {result['n_decisions_action']}",
        "",
        BOLD("📊 Metrics"),
        f"  Fill rate estime  : {result['fill_rate_pct']:.0f}%",
        f"  Target minimum    : {result['target_min_pct']}%",
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
    parser = argparse.ArgumentParser(description="V10 Fill rate")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        result = compute_fill_rate(con)
    finally:
        con.close()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())