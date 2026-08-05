"""V10 Daily Bilan — bilan de la journée (décisions, outcomes, apprentissage) (Phase R).

Produit le bilan quotidien du pipeline V10 :
  - Décisions BUY/SELL de la journée (v10_decisions.db).
  - Outcomes résolus (WR, PnL, Sharpe-like).
  - Apprentissage (drift détecté, recalibration recommandée).
  - Recommandation pour demain (R8).

R9 honnête : pnl proxy, edge relatif. R10 : compute only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_decision_log import DecisionRecord, summarize_decisions  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DECISIONS_DB = ROOT / "data" / "v10_decisions.db"


def load_today_decisions(dec_db: Path, days: int = 1) -> list:
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
    return [
        DecisionRecord(pair=r[0], timeframe=r[1], timestamp=r[2], action=r[3],
                       signal_level=r[4], filtered_level=r[5], lot_size=r[6] or 0.0,
                       pnl_pips=r[7] or 0.0,
                       is_win=bool(r[8]) if r[8] is not None else None)
        for r in rows
    ]


def build_daily_bilan(decisions: list, learning: dict) -> dict:
    """Construit le bilan quotidien complet."""
    summ = summarize_decisions(decisions)
    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions_today": summ,
        "learning": learning,
        "recommendation": _recommendation(summ, learning),
        "audit": {
            "r9_honest": "pnl proxy is_win_proxy, edge relatif",
            "r10": "compute only, zero order real",
        },
    }


def _recommendation(summ: dict, learning: dict) -> str:
    """Recommandation R8 pour demain."""
    if learning.get("drift_detected"):
        return "CALIBRATE: drift détecté → re-calibrer les seuils avant trading"
    if summ["n_trades"] >= 10 and summ["wr"] < 0.40:
        return f"CALIBRATE: WR {summ['wr']:.2f} < 0.40 sur {summ['n_trades']} trades"
    if summ["n_trades"] >= 10 and summ["sharpe_like"] < 0:
        return "CALIBRATE: Sharpe-like négatif → réduire le risque"
    return "HOLD: edge stable, continuer"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions-db", default=str(DEFAULT_DECISIONS_DB))
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    decisions = load_today_decisions(Path(args.decisions_db), args.days)
    log.info("Chargé %d décisions sur %d jour(s)", len(decisions), args.days)

    # Learning state depuis la boucle d'apprentissage (si dispo)
    learning = {}
    loop_file = ROOT / "reports" / f"v10_learning_loop_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    if loop_file.exists():
        try:
            d = json.loads(loop_file.read_text(encoding="utf-8"))
            learning = d.get("learner_state", {})
        except Exception:
            pass

    report = build_daily_bilan(decisions, learning)

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_daily_bilan_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Bilan quotidien écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
