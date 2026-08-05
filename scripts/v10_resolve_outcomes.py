"""V10 Resolve Outcomes — résout le résultat réel des décisions journalisées (Sprint 18).

Chaque décision BUY/SELL persistée dans v10_decisions.db n'a pas encore de
pnl/is_win (None). Ce script résout l'outcome à partir de l'évolution de
prix forward (proxy : close[t+H] - close[t] via forces_snapshots), comme
is_win_proxy V9, puis met à jour le journal.

R9 honnête : proxy forward, pas PnL Fatman réel. R10 : compute only.
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
DEFAULT_DECISIONS_DB = ROOT / "data" / "v10_decisions.db"
DEFAULT_FORCES_DB = ROOT / "data" / "v9_forces.db"

# Horizon de résolution par TF (nb de barres forward)
HORIZON_BY_TF = {"M30": 3, "H1": 2, "H4": 1}


def resolve_outcomes(dec_db: Path, forces_db: Path) -> dict:
    """Résout pnl/is_win pour les décisions sans outcome, met à jour le journal."""
    if not dec_db.exists() or not forces_db.exists():
        return {"n_resolved": 0, "n_pending": 0, "reason": "db_missing"}

    dconn = sqlite3.connect(str(dec_db))
    fconn = sqlite3.connect(str(forces_db))

    pending = dconn.execute(
        "SELECT id, pair, timeframe, timestamp, action "
        "FROM v10_decisions WHERE is_win IS NULL AND action IN ('BUY','SELL')"
    ).fetchall()

    n_resolved = 0
    n_pending = 0
    errors = []
    for dec_id, pair, tf, ts, action in pending:
        try:
            horizon = HORIZON_BY_TF.get(tf or "H1", 2)
            # charge les closes après le timestamp de décision
            rows = fconn.execute(
                "SELECT close FROM forces_snapshots WHERE symbol=? AND timeframe=? "
                "AND timestamp >= ? ORDER BY bar_time LIMIT ?",
                (pair, tf or "H1", ts, horizon + 1)
            ).fetchall()
            if len(rows) < 2:
                n_pending += 1
                continue
            entry = float(rows[0][0])
            exit_ = float(rows[-1][0])
            direction = 1 if action == "BUY" else -1
            pnl = direction * (exit_ - entry)
            # normalise en pips (échelle ~0.0001 pour paires 4 décimales)
            pips = pnl / 0.0001
            is_win = 1 if pnl > 0 else 0
            dconn.execute(
                "UPDATE v10_decisions SET pnl_pips=?, is_win=? WHERE id=?",
                (round(pips, 2), is_win, dec_id))
            dconn.commit()
            n_resolved += 1
        except Exception as exc:
            errors.append(f"{pair}:{type(exc).__name__}")

    dconn.close()
    fconn.close()
    return {"n_resolved": n_resolved, "n_pending": n_pending,
            "n_errors": len(errors), "errors": errors[:10]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions-db", default=str(DEFAULT_DECISIONS_DB))
    ap.add_argument("--forces-db", default=str(DEFAULT_FORCES_DB))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    result = resolve_outcomes(Path(args.decisions_db), Path(args.forces_db))
    result["generated_at"] = datetime.now(timezone.utc).isoformat()

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_resolve_outcomes_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    log.info("Rapport résolution écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
