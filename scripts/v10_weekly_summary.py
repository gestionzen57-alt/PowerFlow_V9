"""V10 Weekly Summary — synthèse hebdomadaire de performance réelle (Sprint 17).

Ferme la boucle R8 : mesure la performance réelle des décisions produites
par le pipeline sur la semaine écoulée.

Sources :
  - `data/v10_decisions.db` (journal des décisions BUY/SELL/WAIT persistées).
  - `data/v9_forces.db` (v10_signals_clean pour contexte + proxy pnl).

Sortie : WR, PnL, Sharpe-like par (paire × action × kill_zone), comparaison
vs benchmark, recommandation de recalibration.

R9 honnête : pnl/is_win sont des proxies (is_win_proxy / pips_simulated) —
edge RELATIF, pas PnL absolu. R10 : compute only.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_decision_log import summarize_decisions  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DECISIONS_DB = ROOT / "data" / "v10_decisions.db"
DEFAULT_FORCES_DB = ROOT / "data" / "v9_forces.db"


def load_weekly_decisions(dec_db: Path, days: int = 7) -> list:
    """Charge les décisions des N derniers jours depuis le journal."""
    if not dec_db.exists():
        return []
    conn = sqlite3.connect(str(dec_db))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT pair, timeframe, timestamp, action, signal_level, "
        "filtered_level, lot_size, pnl_pips, is_win "
        "FROM v10_decisions WHERE timestamp >= ? ORDER BY timestamp",
        (cutoff,)
    ).fetchall()
    conn.close()
    from core.v10.v10_decision_log import DecisionRecord
    return [
        DecisionRecord(pair=r[0], timeframe=r[1], timestamp=r[2], action=r[3],
                       signal_level=r[4], filtered_level=r[5], lot_size=r[6] or 0.0,
                       pnl_pips=r[7] or 0.0,
                       is_win=bool(r[8]) if r[8] is not None else None)
        for r in rows
    ]


def load_context_wr(forces_db: Path, days: int = 7) -> dict:
    """WR de contexte (v10_signals_clean) sur N jours — benchmark."""
    if not forces_db.exists():
        return {"n": 0, "wr": 0.0}
    conn = sqlite3.connect(str(forces_db))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT is_win_proxy FROM v10_signals_clean WHERE timestamp >= ?",
        (cutoff,)
    ).fetchall()
    conn.close()
    if not rows:
        return {"n": 0, "wr": 0.0}
    wins = sum(1 for r in rows if r[0])
    return {"n": len(rows), "wr": round(wins / len(rows), 4)}


def build_weekly_summary(decisions: list, context_wr: dict) -> dict:
    """Synthèse hebdomadaire complète."""
    summ = summarize_decisions(decisions)
    # WR vs benchmark
    wr_delta_pts = None
    if summ["n_trades"] and context_wr["n"]:
        wr_delta_pts = round((summ["wr"] - context_wr["wr"]) * 100.0, 2)

    # Recommandation de recalibration
    recalibrate = False
    reasons = []
    if summ["n_trades"] >= 10 and summ["wr"] < 0.40:
        recalibrate = True
        reasons.append(f"WR {summ['wr']:.2f} < 0.40 sur {summ['n_trades']} trades")
    if summ["n_trades"] >= 10 and summ["sharpe_like"] < 0:
        recalibrate = True
        reasons.append(f"Sharpe-like {summ['sharpe_like']:.2f} < 0")
    if not summ["n_trades"]:
        reasons.append("pas de trades cette semaine")

    return {
        "period_days": 7,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions": summ,
        "context_benchmark": context_wr,
        "wr_delta_pts": wr_delta_pts,
        "recalibrate_recommended": recalibrate,
        "recalibrate_reasons": reasons,
        "audit": {
            "r9_honest": "pnl/is_win proxies — edge relatif, pas PnL absolu",
            "r10": "compute only, zero order real",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions-db", default=str(DEFAULT_DECISIONS_DB))
    ap.add_argument("--forces-db", default=str(DEFAULT_FORCES_DB))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    dec_db = Path(args.decisions_db)
    forces_db = Path(args.forces_db)

    decisions = load_weekly_decisions(dec_db, args.days)
    context_wr = load_context_wr(forces_db, args.days)
    log.info("Chargé %d décisions semaine, contexte WR=%s",
             len(decisions), context_wr.get("wr"))

    report = build_weekly_summary(decisions, context_wr)

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_weekly_summary_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport hebdo écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
