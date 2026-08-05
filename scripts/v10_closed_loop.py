"""V10 Closed Loop — boucle R8 auto-apprentissage (error learner → recalibrator).

Enchaîne la boucle fermée (doctrine R8) sans ordre réel :
  signaux live → ErrorLearner (drift/erreurs) → si déclenché →
  Auto-Recalibrator (recalibration bayésienne par pair-TF) →
  décision DEPLOY/REVERT/HOLD → audit JSON.

Usage :
    python scripts/v10_closed_loop.py --db data/v9_forces.db [--limit 100]
Sortie : JSON rapport boucle + log.

R9 honnête : WR/PnL sur proxy (is_win_proxy) — edge RELATIF. R10 : zéro ordre réel.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_auto_recalibrator import run_auto_recalibration  # noqa: E402
from core.v10.v10_error_learner import TradeOutcome, ErrorLearner  # noqa: E402
from core.v10.v10_ict_ote import _kill_zone_at_hour  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DB = ROOT / "data" / "v9_forces.db"


def _zone_from_ts(ts: str) -> str:
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return _kill_zone_at_hour(dt.hour).value
    except (ValueError, OSError):
        return "UNKNOWN"


def load_signals(db_path: Path, limit: int) -> list:
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT timestamp, symbol, signal_level, is_win_proxy, pnl_pips_proxy "
        "FROM v10_signals_clean ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [{
        "ts": ts, "symbol": sym, "setup": lvl or "NONE",
        "win": bool(win), "pnl": float(pnl or 0.0),
    } for ts, sym, lvl, win, pnl in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    signals = load_signals(db, args.limit)
    log.info("Chargé %d signaux", len(signals))

    # 1. Jouer l'historique dans l'ErrorLearner
    learner = ErrorLearner()
    for s in signals:
        learner.record(TradeOutcome(
            symbol=s["symbol"], setup=s["setup"],
            kill_zone=_zone_from_ts(s["ts"]), win=s["win"],
            pnl=s["pnl"], timestamp=s["ts"],
        ))

    # 2. Décision de recalibration (boucle R8)
    decision = run_auto_recalibration(
        learner.state, db_path=str(db), min_losses=10,
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "learner_state": learner.state.as_dict(),
        "recalibration": decision.as_dict(),
        "audit": {
            "r9_honest": "proxy is_win_proxy — edge relatif, pas PnL absolu",
            "r10": "recommandation only, zero order real",
        },
    }

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_closed_loop_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport boucle écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
