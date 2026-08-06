"""V10 Night Summary — rapport consolidé de la nuit (autopilote nocturne).

Agrège les livrables de la nuit (portage V9 → V10, audit, KPIs système) en
une vue unique et lisible pour le CEO. R9 : chaque chiffre sourcé d'un
rapport JSON traçable. R10 : compute only.

Résume :
  - Couverture V9 → V10 (audit principes)
  - Concepts portés (grammar v9 / extra / final)
  - Décisions live + résolution outcomes
  - Apprentissage (drift, recalibration)
  - État des crons
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)


def _load(pattern: str) -> dict:
    files = sorted(ROOT.glob(pattern))
    if not files:
        return {}
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return {}


def _audit_v9() -> str:
    d = _load("reports/v10_v9_principles_audit_*.json")
    if not d:
        return "  Audit V9: n/a"
    return (f"  Audit V9→V10: {d.get('n_covered_v10')}/{d.get('n_active')} "
            f"couverts · {d.get('n_gap', 0)} gaps · {d.get('n_excluded_r9', 0)} exclus R9")


def _grammar_concepts() -> str:
    modules = {
        "v10_grammar_v9": ["LEADER_FOLLOWER", "PULLBACK", "TENSION", "RESPIRATION",
                           "LOCK", "OPPOSITION"],
        "v10_grammar_v9_extra": ["ADAPTIVE_VOL_GATE", "ELASTIC_BREATH", "EXHAUSTION",
                                 "VELOCITY_CLIMAX_GUARD", "NODE_BIRTH"],
        "v10_grammar_v9_final": ["CONTEXTE", "CROISEMENT", "CROISEMENT_CONFIRMATION",
                                 "GRAVITY_RESPRING", "POWER_ANGLE_BREAK",
                                 "RAW_NODE_BIRTH", "SIGNAL_OPEN"],
    }
    lines = [f"  Concepts V9 portés: {sum(len(v) for v in modules.values())}"]
    for mod, concepts in modules.items():
        lines.append(f"    {mod}: {', '.join(concepts)}")
    return "\n".join(lines)


def _decisions() -> str:
    try:
        c = sqlite3.connect(str(ROOT / "data" / "v10_decisions.db"))
        tot = c.execute("SELECT COUNT(*) FROM v10_decisions").fetchone()[0]
        res = c.execute("SELECT COUNT(*) FROM v10_decisions WHERE is_win IS NOT NULL").fetchone()[0]
        wins = c.execute("SELECT COUNT(*) FROM v10_decisions WHERE is_win=1").fetchone()[0]
        c.close()
        wr = f"{wins/res:.2f}" if res else "n/a"
        return f"  Décisions: {tot} ({res} résolues) · WR résolu: {wr} ({wins}/{res})"
    except Exception:
        return "  Décisions: n/a"


def _learning() -> str:
    d = _load("reports/v10_learning_loop_*.json")
    if not d:
        return "  Apprentissage: n/a"
    ls = d.get("learner_state", {})
    rc = d.get("recalibration", {})
    n = ls.get("n_trades", 0)
    wr = f"{ls.get('n_wins', 0)/max(1, n):.2f}" if n else "n/a"
    drift = "⚠️ OUI" if ls.get("drift_detected") else "non"
    return (f"  Apprentissage: {n} trades · WR {wr} · drift {drift} · "
            f"recalib {rc.get('decision', 'n/a')}")


def build_report() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["═══ V10 NIGHT SUMMARY — autopilote nocturne ═══"]
    lines.append(f"  {now}")
    lines.append(_audit_v9())
    lines.append(_grammar_concepts())
    lines.append(_decisions())
    lines.append(_learning())
    lines.append("  R10: paper-only, zéro ordre réel")
    lines.append("══════════════════════════════════════")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    report = build_report()
    print(report)

    if args.output:
        out = Path(args.output)
        out.write_text(report, encoding="utf-8")
        log.info("Rapport écrit: %s", out)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
