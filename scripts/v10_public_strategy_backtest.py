"""V10 Public Strategy Backtest — évalue l'edge des stratégies publiques.

Backtest quantitatif sur le dataset V10 propre `v10_signals_clean` :
- **ICT Kill Zones** : est-ce que les signaux émis pendant les Kill Zones
  (ASIAN/LONDON/NY) ont un WR supérieur à la moyenne ? (dérivé du timestamp)
- **Direction × Signal Level** : le WR par direction × niveau setup.
- **ICT OTE proxy** : filtre par kill zone sur les signaux A1/A2.

R9 honnête : les colonnes `is_win_proxy`/`pnl_pips_proxy` portent le PROXY
pnl V9 (close[t+5]-close[t]), biaisé (cf. Pitfall 9). Ce backtest mesure un
**signal d'edge relatif** (écart de WR par bucket), pas un PnL absolu.

Usage :
    python scripts/v10_public_strategy_backtest.py [--db data/v9_forces.db]
Sortie : JSON `reports/v10_public_strategy_backtest_YYYYMMDD.json` + log.
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

from core.v10.v10_ict_ote import KillZone, _kill_zone_at_hour  # noqa: E402

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
        return KillZone.UNKNOWN.value


def load_signals(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT timestamp, symbol, timeframe, signal_level, direction, "
        "is_win_proxy, pnl_pips_proxy FROM v10_signals_clean"
    ).fetchall()
    conn.close()
    signals = []
    for ts, sym, tf, lvl, direction, win, pnl in rows:
        signals.append({
            "ts": ts, "symbol": sym, "timeframe": tf,
            "signal_level": lvl, "direction": direction,
            "is_win": bool(win), "pnl": float(pnl or 0.0),
        })
    return signals


def backtest(signals) -> dict:
    total = len(signals)
    wins = sum(1 for s in signals if s["is_win"])
    base_wr = wins / total if total else 0.0

    # WR par Kill Zone
    by_zone = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})
    for s in signals:
        zone = _zone_from_ts(s["ts"])
        b = by_zone[zone]
        b["n"] += 1
        b["wins"] += 1 if s["is_win"] else 0
        b["pnl"] += s["pnl"]

    zone_stats = {}
    for zone, b in by_zone.items():
        if b["n"] >= 20:  # skip buckets trop petits
            zone_stats[zone] = {
                "n": b["n"],
                "wr": round(b["wins"] / b["n"], 4),
                "delta_wr_pts": round((b["wins"] / b["n"] - base_wr) * 100.0, 2),
                "pnl": round(b["pnl"], 2),
            }

    # WR par signal_level
    by_level = defaultdict(lambda: {"n": 0, "wins": 0})
    for s in signals:
        lvl = s["signal_level"] or "NONE"
        by_level[lvl]["n"] += 1
        by_level[lvl]["wins"] += 1 if s["is_win"] else 0
    level_stats = {
        lvl: {"n": b["n"], "wr": round(b["wins"] / b["n"], 4)}
        for lvl, b in by_level.items() if b["n"] >= 20
    }

    # WR par (kill_zone × level A1/A2) — l'edge ICT OTE
    by_zone_level = defaultdict(lambda: {"n": 0, "wins": 0})
    for s in signals:
        zone = _zone_from_ts(s["ts"])
        lvl = s["signal_level"]
        if lvl in ("A1", "A2"):
            key = (zone, lvl)
            by_zone_level[key]["n"] += 1
            by_zone_level[key]["wins"] += 1 if s["is_win"] else 0
    zone_level_stats = {}
    for (zone, lvl), b in by_zone_level.items():
        if b["n"] >= 20:
            wr = b["wins"] / b["n"]
            zone_level_stats[f"{zone}|{lvl}"] = {
                "n": b["n"], "wr": round(wr, 4),
                "delta_wr_pts": round((wr - base_wr) * 100.0, 2),
            }

    return {
        "total_signals": total,
        "base_wr": round(base_wr, 4),
        "base_wins": wins,
        "by_kill_zone": dict(sorted(zone_stats.items(), key=lambda kv: -kv[1]["wr"])),
        "by_signal_level": dict(sorted(level_stats.items(), key=lambda kv: -kv[1]["wr"])),
        "by_zone_level_A1A2": dict(sorted(
            zone_level_stats.items(), key=lambda kv: -kv[1]["wr"])),
        "audit": {
            "r9_honest": "is_win_proxy/pnl_pips_proxy = proxy V9 biaisé "
                         "(close[t+5]-close[t]) — signal d'edge RELATIF, pas PnL absolu",
            "min_bucket": 20,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    signals = load_signals(db)
    log.info("Chargé %d signaux depuis %s", len(signals), db.name)
    result = backtest(signals)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_public_strategy_backtest_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    log.info("Rapport écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
