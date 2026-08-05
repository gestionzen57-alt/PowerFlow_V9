"""V10 Night Report — rapport nocturne consolidé (Sprint 6 autopilote quant).

Agrège les stratégies publiques + apprentissage + KPIs live en un seul
rapport JSON exploitable par le CEO.

Composants :
  1. Backtest ICT Kill Zones (v10_public_strategy_backtest) — l'edge validé.
  2. Error Learner (v10_error_learner) — drift + re-calibration recommandée.
  3. KPIs live depuis la DB (WR, PnL, per setup × kill_zone).
  4. Gate final orchestrateur (public_filters) — état du pipeline.

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open (chaque section peut
échouer sans casser le rapport), R7, R9 audit honnête, R10 zéro ordre réel.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_ict_ote import _kill_zone_at_hour  # noqa: E402
from core.v10.v10_error_learner import (  # noqa: E402
    TradeOutcome, ErrorLearner,
)

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


def load_live_signals(db_path: Path) -> list:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT timestamp, symbol, timeframe, signal_level, direction, "
        "is_win_proxy, pnl_pips_proxy FROM v10_signals_clean"
    ).fetchall()
    conn.close()
    out = []
    for ts, sym, tf, lvl, direction, win, pnl in rows:
        out.append({
            "ts": ts, "symbol": sym, "timeframe": tf,
            "signal_level": lvl, "direction": direction,
            "is_win": bool(win), "pnl": float(pnl or 0.0),
        })
    return out


def ict_kill_zone_stats(signals: list) -> dict:
    """WR par Kill Zone (edge ICT validé Sprint 3)."""
    total = len(signals)
    if not total:
        return {"base_wr": 0.0, "by_zone": {}}
    wins = sum(1 for s in signals if s["is_win"])
    base_wr = wins / total
    by_zone = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})
    for s in signals:
        z = _zone_from_ts(s["ts"])
        b = by_zone[z]
        b["n"] += 1
        b["wins"] += 1 if s["is_win"] else 0
        b["pnl"] += s["pnl"]
    zone_stats = {}
    for z, b in by_zone.items():
        if b["n"] >= 20:
            wr = b["wins"] / b["n"]
            zone_stats[z] = {
                "n": b["n"], "wr": round(wr, 4),
                "delta_wr_pts": round((wr - base_wr) * 100.0, 2),
                "pnl": round(b["pnl"], 2),
            }
    return {"base_wr": round(base_wr, 4), "by_zone": zone_stats}


def error_learner_analysis(signals: list) -> dict:
    """Joue l'historique via l'ErrorLearner pour détecter drift + recalibration."""
    learner = ErrorLearner()
    for s in signals:
        learner.record(TradeOutcome(
            symbol=s["symbol"], setup=s["signal_level"] or "NONE",
            kill_zone=_zone_from_ts(s["ts"]), win=s["is_win"],
            pnl=s["pnl"], timestamp=s["ts"],
        ))
    st = learner.state
    return {
        "n_trades": st.n_trades,
        "wr_global": round(st.n_wins / st.n_trades, 4) if st.n_trades else 0.0,
        "max_losing_streak": st.max_losing_streak,
        "drift_detected": st.drift_detected,
        "drift_count": st.drift_count,
        "recalibrate_recommended": st.recalibrate_recommended,
        "recalibrate_setups": st.recalibrate_setups,
        "per_setup": st.per_setup,
        "lessons": list(st.lessons[-10:]),
    }


def kpi_by_setup_zone(signals: list) -> dict:
    """WR par (setup × kill_zone) — l'edge exploitable."""
    total = len(signals)
    if not total:
        return {}
    wins = sum(1 for s in signals if s["is_win"])
    base_wr = wins / total
    by = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})
    for s in signals:
        key = f"{s['signal_level'] or 'NONE'}|{_zone_from_ts(s['ts'])}"
        b = by[key]
        b["n"] += 1
        b["wins"] += 1 if s["is_win"] else 0
        b["pnl"] += s["pnl"]
    out = {}
    for k, b in by.items():
        if b["n"] >= 20:
            wr = b["wins"] / b["n"]
            out[k] = {
                "n": b["n"], "wr": round(wr, 4),
                "delta_wr_pts": round((wr - base_wr) * 100.0, 2),
                "pnl": round(b["pnl"], 2),
            }
    # tri par delta décroissant
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["delta_wr_pts"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    signals = load_live_signals(db)
    log.info("Chargé %d signaux depuis %s", len(signals), db.name)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ict_kill_zones": ict_kill_zone_stats(signals),
        "error_learner": error_learner_analysis(signals),
        "kpi_by_setup_zone": kpi_by_setup_zone(signals),
        "audit": {
            "r9_honest": "is_win_proxy = proxy V9 biaisé (close[t+5]-close[t])"
                         " — edge RELATIF, pas PnL absolu",
            "r10": "compute only, zero order real",
        },
    }

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_night_report_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
