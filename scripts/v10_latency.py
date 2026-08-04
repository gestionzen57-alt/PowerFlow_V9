"""
V10 — Latence pipeline (capture → décision).

R2 additif pur : nouveau fichier scripts/. Pas de modif core/.
Phase C prerequisite : mesure le délai entre ingestion données et décision.

Méthodologie :
  Lit les timestamps du pipeline (forces_snapshots → signals → decisions)
  et calcule la latence de bout en bout. Compare au budget institutionnel
  (< 10ms) et au budget V9 (< 100ms).

Doctrine : R1-AGIR, R6-EXPLIQUER, R7-MESURER, R9-AUDITABLE, R10.

Usage :
  .venv/Scripts/python.exe scripts/v10_latency.py
  .venv/Scripts/python.exe scripts/v10_latency.py --json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
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


def _parse_ts(ts: Any) -> float | None:
    """Convertit un timestamp DB en epoch (si possible)."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts)
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def compute_latency(con: sqlite3.Connection) -> dict[str, Any]:
    """Calcule la latence pipeline entre les tables."""
    # Récupère les timestamps récents des forces, signals, decisions
    try:
        forces = con.execute(
            "SELECT timestamp FROM forces_snapshots ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
    except sqlite3.OperationalError:
        forces = []
    try:
        signals = con.execute(
            "SELECT timestamp FROM signals ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
    except sqlite3.OperationalError:
        signals = []
    try:
        decisions = con.execute(
            "SELECT timestamp FROM decisions ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
    except sqlite3.OperationalError:
        decisions = []

    f_ts = [_parse_ts(r[0]) for r in forces]
    s_ts = [_parse_ts(r[0]) for r in signals]
    d_ts = [_parse_ts(r[0]) for r in decisions]
    f_ts = [t for t in f_ts if t is not None]
    s_ts = [t for t in s_ts if t is not None]
    d_ts = [t for t in d_ts if t is not None]

    # Latence capture → signal (différence des dernières entrées par seconde)
    # Approximation : compare les timestamps les plus récents alignés.
    latency_capture_signal_ms = None
    if f_ts and s_ts:
        # Dernière paire forcé/signal proche en temps
        s_latest = max(s_ts)
        # Trouver le force le plus proche avant le signal
        prior = [t for t in f_ts if t <= s_latest]
        if prior:
            latency_capture_signal_ms = (s_latest - max(prior)) * 1000

    latency_signal_decision_ms = None
    if s_ts and d_ts:
        d_latest = max(d_ts)
        prior = [t for t in s_ts if t <= d_latest]
        if prior:
            latency_signal_decision_ms = (d_latest - max(prior)) * 1000

    total_ms = None
    if latency_capture_signal_ms is not None and latency_signal_decision_ms is not None:
        total_ms = latency_capture_signal_ms + latency_signal_decision_ms

    # Kill criteria (budget institutionnel)
    alerts: list[str] = []
    if total_ms is not None and total_ms > 100:
        alerts.append(f"🔴 Latence totale {total_ms:.1f}ms > 100ms (budget V9 dépassé)")
    if total_ms is not None and total_ms > 10:
        alerts.append(f"⚠️  Latence totale {total_ms:.1f}ms > 10ms (cible institutionnelle HFT)")

    verdict = "GO" if total_ms is None or total_ms <= 100 else "NO-GO"

    return {
        "n_forces": len(f_ts),
        "n_signals": len(s_ts),
        "n_decisions": len(d_ts),
        "latency_capture_signal_ms": round(latency_capture_signal_ms, 2) if latency_capture_signal_ms is not None else None,
        "latency_signal_decision_ms": round(latency_signal_decision_ms, 2) if latency_signal_decision_ms is not None else None,
        "latency_total_ms": round(total_ms, 2) if total_ms is not None else None,
        "budget_v9_ms": 100,
        "budget_institutionnel_ms": 10,
        "kill_criteria": alerts,
        "verdict": verdict,
    }


def format_console(result: dict) -> str:
    if "error" in result:
        return RED(f"❌ {result['error']}")
    out = [
        BOLD("=" * 70),
        BOLD(" ⏱️  V10 Latence pipeline"),
        BOLD("=" * 70),
        f"Forces snapshots   : {result['n_forces']}",
        f"Signals           : {result['n_signals']}",
        f"Decisions         : {result['n_decisions']}",
        "",
        BOLD("📊 Latence"),
        f"  Capture → Signal : {result['latency_capture_signal_ms']} ms" if result['latency_capture_signal_ms'] is not None else "  Capture → Signal : N/A",
        f"  Signal → Decision: {result['latency_signal_decision_ms']} ms" if result['latency_signal_decision_ms'] is not None else "  Signal → Decision: N/A",
        f"  Total           : {result['latency_total_ms']} ms" if result['latency_total_ms'] is not None else "  Total           : N/A",
        f"  Budget V9       : {result['budget_v9_ms']} ms",
        f"  Budget HFT      : {result['budget_institutionnel_ms']} ms",
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
    parser = argparse.ArgumentParser(description="V10 Latence pipeline")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(RED(f"❌ DB introuvable: {DB_PATH}"))
        return 1

    con = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        result = compute_latency(con)
    finally:
        con.close()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_console(result))

    return 0 if result.get("verdict") == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())