"""V10 Replay Engine — replay historique bars → décisions → apprentissage (Phase R).

Rejoue l'historique OHLCV bar par bar pour produire des décisions BUY/SELL,
résoudre les outcomes forward (proxy), et nourrir l'ErrorLearner — l'apprentissage
continue même en replay (boucle R8 : mesure → apprentissage → recalibration).

Chaque bar rejouée :
  1. Calcule les stratégies publiques (ICT OTE + SMC + régime HMM).
  2. Exécute decide_entry → action + lot_size.
  3. Résout l'outcome (close[t+H] - close[t], proxy forward).
  4. Enregistre dans l'ErrorLearner (drift/recalibration/leçons).

Sortie : dataset d'apprentissage + décisions + KPIs par paire×TF.

Doctrine : R1-AGIR, R2 additif pur, R6 fail-open, R7, R9 honnête (proxy pnl),
R10 zéro ordre réel.
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
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_decision_pipeline import decide_entry  # noqa: E402
from core.v10.v10_error_learner import ErrorLearner, TradeOutcome  # noqa: E402
from core.v10.v10_ict_ote import compute_ict_ote  # noqa: E402
from core.v10.v10_smc import detect_smc  # noqa: E402
from core.v10.v10_regime_hmm import compose_regime_signal  # noqa: E402
from core.v10.v10_session_filter import get_session_quality  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DB = ROOT / "data" / "v9_forces.db"

HORIZON_BY_TF = {"M30": 3, "H1": 2, "H4": 1}
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]


def load_bars(db_path: Path, symbol: str, timeframe: str,
              limit: int = 300) -> list:
    """Charge les bars fermées croissantes (OHLCV + timestamp)."""
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT open, high, low, close, tick_volume, timestamp "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?", (symbol, timeframe, limit)
    ).fetchall()
    conn.close()
    rows.reverse()
    return [{
        "open": float(o), "high": float(h), "low": float(lo),
        "close": float(c), "tick_volume": float(v or 0.0), "timestamp": ts,
    } for o, h, lo, c, v, ts in rows]


def _regime_direction(regime) -> str:
    """Direction dérivée du régime HMM (bias)."""
    if regime is None:
        return "long", "A3"
    rv = getattr(regime, "regime", None)
    name = rv.value if hasattr(rv, "value") else str(rv)
    if name in ("TRENDING_DOWN", "DISTRIBUTION", "MARKDOWN"):
        return "short", "A2"
    if name in ("UNKNOWN", "NEUTRAL", "RANGING", "VOLATILE"):
        return "long", "A3"
    return "long", "A2"


def replay_pair(db_path: Path, symbol: str, timeframe: str,
                limit: int = 300) -> dict:
    """Rejoue l'historique d'une paire et produit décisions + apprentissage."""
    bars = load_bars(db_path, symbol, timeframe, limit)
    if not bars:
        return {"symbol": symbol, "tf": timeframe, "n_bars": 0,
                "decisions": [], "error": "no_bars"}

    horizon = HORIZON_BY_TF.get(timeframe, 2)
    learner = ErrorLearner()
    decisions = []

    # Replay : chaque barre i est un point de décision (besoin de bars passées
    # + bars forward pour résoudre l'outcome).
    min_lookback = 30
    # Optimisation perf : le régime HMM est coûteux à refit (hmmlearn).
    #   - On ne le recalcule que toutes les `regime_stride` barres.
    #   - On borne la fenêtre HMM à `hmm_window` barres (rolling window) pour
    #     éviter un coût O(N²) sur les gros TF (M30/H4 avec 4000+ bars). Le
    #     régime est stable sur cette profondeur, pas de perte de décision.
    regime_stride = 15
    hmm_window = 200
    regime = None
    for i in range(min_lookback, len(bars) - horizon):
        window = bars[: i + 1]  # passé inclusif
        cur = bars[i]
        closes = [b["close"] for b in window]
        ts = cur["timestamp"]

        try:
            ote = compute_ict_ote(symbol, timeframe, closes, timestamp=ts)
        except Exception:
            ote = None
        try:
            smc = detect_smc(window, symbol=symbol, timeframe=timeframe,
                             timestamp=ts)
        except Exception:
            smc = None
        # Régime HMM : refit périodique (stride) sur fenêtre BORNÉE (perf).
        if i % regime_stride == 0 or regime is None:
            try:
                hmm_closes = closes[-hmm_window:]  # rolling window cap
                regime = compose_regime_signal(hmm_closes, symbol=symbol, timestamp=ts)
            except Exception:
                regime = None
        try:
            session = get_session_quality(symbol, timestamp=ts)
        except Exception:
            session = None

        direction, base_level = _regime_direction(regime)
        dec = decide_entry(
            symbol, timeframe, ts, direction, base_level,
            session=session, ote=ote, smc=smc, regime=regime,
            candidate_risk_pct=1.0,
        )

        action = dec.action
        if action in ("BUY", "SELL"):
            # Résout l'outcome forward (proxy)
            entry = cur["close"]
            exit_ = bars[i + horizon]["close"]
            direction_sign = 1 if action == "BUY" else -1
            pnl = direction_sign * (exit_ - entry)
            pips = pnl / 0.0001
            is_win = pnl > 0

            decisions.append({
                "bar_index": i, "timestamp": ts, "action": action,
                "direction": direction, "level": dec.filtered_level,
                "lot_size": dec.lot_size, "pnl_pips": round(pips, 2),
                "is_win": is_win,
            })

            # Apprentissage des erreurs
            learner.record(TradeOutcome(
                symbol=symbol, setup=dec.filtered_level,
                kill_zone=getattr(ote, "kill_zone", "UNKNOWN"),
                win=is_win, pnl=pips, timestamp=ts,
            ))

    return {
        "symbol": symbol, "tf": timeframe, "n_bars": len(bars),
        "n_decisions": len(decisions),
        "n_buys": sum(1 for d in decisions if d["action"] == "BUY"),
        "n_sells": sum(1 for d in decisions if d["action"] == "SELL"),
        "wr": round(learner.state.n_wins / max(1, learner.state.n_trades), 4),
        "n_wins": learner.state.n_wins,
        "n_losses": learner.state.n_losses,
        "max_losing_streak": learner.state.max_losing_streak,
        "drift_detected": learner.state.drift_detected,
        "recalibrate_recommended": learner.state.recalibrate_recommended,
        "lessons": learner.state.lessons[-5:],
        "decisions": decisions,
    }


def replay_all(db_path: Path, limit: int = 300) -> dict:
    """Rejoue toutes les paires × TF et agrège le rapport d'apprentissage."""
    results = []
    for symbol in PAIRS:
        for tf in ("H1", "M30"):
            try:
                res = replay_pair(db_path, symbol, tf, limit)
                results.append(res)
                log.info("Replay %s %s: %d décisions, WR=%.2f",
                         symbol, tf, res["n_decisions"], res["wr"])
            except Exception as exc:
                log.warning("Replay %s %s échoué (R6): %s", symbol, tf,
                            type(exc).__name__)
                results.append({"symbol": symbol, "tf": tf, "error": type(exc).__name__})

    # Agrégation
    total_dec = sum(r.get("n_decisions", 0) for r in results)
    total_wins = sum(r.get("n_wins", 0) for r in results)
    total_losses = sum(r.get("n_losses", 0) for r in results)
    drift = any(r.get("drift_detected") for r in results)
    recalib = any(r.get("recalibrate_recommended") for r in results)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_pairs_tf": len(results),
        "total_decisions": total_dec,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "aggregate_wr": round(total_wins / max(1, total_dec), 4),
        "drift_detected_any": drift,
        "recalibrate_recommended_any": recalib,
        "per_pair_tf": results,
        "audit": {
            "r9_honest": "pnl proxy forward close[t+H]-close[t], pas PnL Fatman",
            "r10": "compute only, zero order real",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--pair", default="")       # optionnel : 1 paire
    ap.add_argument("--timeframe", default="")  # optionnel : 1 TF
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    if args.pair:
        tf = args.timeframe or "H1"
        report = replay_pair(db, args.pair, tf, args.limit)
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        report["audit"] = {"r9_honest": "proxy", "r10": "compute only"}
    else:
        report = replay_all(db, args.limit)

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_replay_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False)[:3000])
    log.info("Rapport replay écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
