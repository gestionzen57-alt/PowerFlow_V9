"""V10 Shadow Promotion — validation SHADOW→ACTIVE sur paper trades (Sprint 6).

Évalue si un setup V10 (ou un setup × kill_zone) mérite la promotion
SHADOW→ACTIVE selon les gates R10, sur les 100 derniers paper trades.

Gates R10 (alignés sur v10_rl_promotion) :
  - WR ≥ 50% (proxy is_win_proxy — R9 caveat)
  - Sharpe-like ≥ 0.3 (sur pnl proxy)
  - Max DD ≤ 50 pips
  - Consistency ≥ 75% (fraction de trades positifs, proxy)

R6 fail-open : données insuffisantes (< 30 trades) → gate_non_atteint,
pas de promotion. R10 : ce module NE passe JAMAIS d'ordre réel — il produit
une recommandation (promote_eligible bool) à consommer par le CEO.

Doctrine : R1-AGIR (peut recommander la promotion), R2 additif pur,
R6 fail-open, R7 tests, R9 audit honnête, R10 zéro ordre réel.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_ict_ote import _kill_zone_at_hour  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DB = ROOT / "data" / "v9_forces.db"

# Gates R10
GATE_WR = 0.50
GATE_SHARPE = 0.30
GATE_MAX_DD_PIPS = 50.0
GATE_CONSISTENCY = 0.75
MIN_TRADES = 30


def _zone_from_ts(ts: str) -> str:
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return _kill_zone_at_hour(dt.hour).value
    except (ValueError, OSError):
        return "UNKNOWN"


def _sharpe_like(pnls: list) -> float:
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return mean / sd


def evaluate_setup(trades: list) -> dict:
    """Évalue un bucket de trades contre les gates R10."""
    n = len(trades)
    result = {"n_trades": n, "gates_passed": 0, "promote_eligible": False}

    if n < MIN_TRADES:
        result["verdict"] = "insufficient_data"
        result["reasons"] = [f"n<{MIN_TRADES}"]
        return result

    wins = sum(1 for t in trades if t["is_win"])
    wr = wins / n
    pnls = [t["pnl"] for t in trades]
    sharpe = _sharpe_like(pnls)
    # Max DD en pips (cumul des pertes consécutives max, proxy)
    max_dd = 0.0
    cum = 0.0
    for p in pnls:
        if p < 0:
            cum += p
            max_dd = min(max_dd, cum)
        else:
            cum = 0.0
    max_dd_pips = abs(max_dd)
    consistency = sum(1 for p in pnls if p > 0) / n

    gates = {
        "wr": wr >= GATE_WR,
        "sharpe": sharpe >= GATE_SHARPE,
        "max_dd": max_dd_pips <= GATE_MAX_DD_PIPS,
        "consistency": consistency >= GATE_CONSISTENCY,
    }
    passed = sum(1 for v in gates.values() if v)

    result.update({
        "wr": round(wr, 4), "sharpe_like": round(sharpe, 3),
        "max_dd_pips": round(max_dd_pips, 2),
        "consistency": round(consistency, 4),
        "gates": gates,
        "gates_passed": passed,
        "promote_eligible": passed == 4,
        "verdict": "PROMOTE" if passed == 4 else "HOLD",
    })
    return result


def load_paper_trades(db_path: Path, limit: int = 100) -> list:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT timestamp, symbol, timeframe, signal_level, direction, "
        "is_win_proxy, pnl_pips_proxy FROM v10_signals_clean "
        "ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [{
        "ts": ts, "symbol": sym, "timeframe": tf,
        "signal_level": lvl or "NONE", "direction": direction,
        "is_win": bool(win), "pnl": float(pnl or 0.0),
    } for ts, sym, tf, lvl, direction, win, pnl in rows]


def evaluate_all(trades: list) -> dict:
    """Évalue par (setup × kill_zone) + global + par setup + par zone."""
    buckets = defaultdict(list)
    for t in trades:
        key = f"{t['signal_level']}|{_zone_from_ts(t['ts'])}"
        buckets[key].append(t)

    per_bucket = {k: evaluate_setup(v) for k, v in buckets.items()}

    # Global
    global_eval = evaluate_setup(trades)

    return {
        "n_total": len(trades),
        "global": global_eval,
        "per_setup_zone": dict(sorted(
            per_bucket.items(), key=lambda kv: -kv[1].get("wr", 0))),
        "audit": {
            "gates": {"wr": GATE_WR, "sharpe": GATE_SHARPE,
                      "max_dd_pips": GATE_MAX_DD_PIPS,
                      "consistency": GATE_CONSISTENCY},
            "r10": "recommandation only, zero order real",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    trades = load_paper_trades(db, args.limit)
    log.info("Chargé %d trades depuis %s", len(trades), db.name)
    result = evaluate_all(trades)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_shadow_promotion_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    log.info("Rapport écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
