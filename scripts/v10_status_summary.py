"""V10 Status Summary — état consolidé du système (Phase R).

Agrège tous les rapports JSON V10 en une vue texte unique et actionable :
  - Décisions live (dernières BUY/SELL)
  - Résolution des outcomes (WR réel résolu)
  - Apprentissage (drift, recalibration, modèle persisté)
  - Edges (carte replay)
  - Bilan quotidien (reco R8)

R9 honnête : chaque chiffre est sourcé d'un rapport JSON traçable.
R10 : compute only.
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)


def _latest(pattern: str) -> dict:
    files = sorted(glob.glob(str(ROOT / pattern)))
    if not files:
        return {}
    try:
        return json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    except Exception:
        return {}


def decisions_status() -> str:
    """Décisions live + résolution."""
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


def edges_status() -> str:
    d = _latest("reports/v10_replay_batch_*.json")
    em = d.get("edge_map", {})
    yes = [k for k, v in em.items() if v.get("edge") == "YES"]
    top = sorted(yes, key=lambda k: -em[k]["wr"])[:5]
    lines = [f"  Edges: {len(yes)}/{len(em)} validés"]
    for k in top:
        v = em[k]
        lines.append(f"    {k}: WR {v['wr']:.2f} ({v['n']} trades, {v['direction']})")
    return "\n".join(lines)


def learning_status() -> str:
    d = _latest("reports/v10_learning_loop_*.json")
    if not d:
        return "  Apprentissage: n/a"
    ls = d.get("learner_state", {})
    rc = d.get("recalibration", {})
    n = ls.get("n_trades", 0)
    wr = f"{ls.get('n_wins', 0)/max(1, n):.2f}" if n else "n/a"
    drift = "⚠️ OUI" if ls.get("drift_detected") else "non"
    return (f"  Apprentissage: {n} trades appris · WR {wr} · drift {drift} · "
            f"recalib {rc.get('decision', 'n/a')}")


def bilan_status() -> str:
    d = _latest("reports/v10_daily_bilan_*.json")
    if not d:
        return "  Bilan: n/a"
    dec = d.get("decisions_today", {})
    rec = d.get("recommendation", "n/a")
    return (f"  Bilan {d.get('date')}: {dec.get('n_trades', 0)} trades · "
            f"WR {dec.get('wr', 0):.2f} · reco: {rec}")


def build_status() -> str:
    hmm = _latest("reports/v10_live_decision_latest.json")
    active = [r for r in hmm.get("tick_results", [])
              if r.get("action") in ("BUY", "SELL")]
    lines = ["═══ V10 STATUS ═══"]
    lines.append(f"  Signaux live: {len(active)} actifs")
    for r in active[:8]:
        lines.append(f"    {r['pair']} {r['action']} ({r.get('regime')})")
    lines.append(decisions_status())
    lines.append(edges_status())
    lines.append(learning_status())
    lines.append(bilan_status())
    lines.append("════════════════")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    status = build_status()
    print(status)

    if args.output:
        out = Path(args.output)
        out.write_text(status, encoding="utf-8")
        log.info("Status écrit: %s", out)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
