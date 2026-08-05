"""V10 Live Decision Loop — boucle temps-réel du pipeline décision (Sprint 14).

Wrapper additif (R2) qui câble `v10_decision_pipeline.decide_entry` dans une
boucle de polling sur les bars live (forces_snapshots). Ne modifie pas
`v10_live_monitor` (ZCode) — fournit une boucle décision dédiée.

À chaque tick :
  1. Charge les bars OHLCV live (forces_snapshots) pour chaque paire.
  2. Calcule les stratégies publiques (ICT OTE + SMC + régime HMM).
  3. Exécute `decide_entry` → action + lot_size.
  4. Applique la politique d'exécution (paper-only, R10) : pas d'ordre réel.

R6 fail-open : tick sans données → skip sans crash. R10 : paper-only strict.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.v10.v10_decision_pipeline import decide_entry  # noqa: E402
from core.v10.v10_decision_log import DecisionRecord, DecisionLogger  # noqa: E402
from core.v10.v10_edge_selector import EdgeSelector  # noqa: E402
from core.v10.v10_calibrate_apply import (  # noqa: E402
    find_recalibrated_thresholds, ensure_active_thresholds,
)
from core.v10.v10_grammar_v9 import evaluate_grammar_v9  # noqa: E402
from core.v10.v10_ict_ote import compute_ict_ote  # noqa: E402
from core.v10.v10_smc import detect_smc  # noqa: E402
from core.v10.v10_regime_hmm import compose_regime_signal  # noqa: E402
from core.v10.v10_session_filter import get_session_quality  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DB = ROOT / "data" / "v9_forces.db"

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
TIMEFRAMES = ["H1"]


def load_bars(db_path: Path, symbol: str, timeframe: str, limit: int = 60) -> list:
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


def tick_decision(db: Path, symbol: str, tf: str,
                  selector: Optional[EdgeSelector] = None) -> dict:
    """Décision complète pour une paire sur un tick (direction = bias régime)."""
    bars = load_bars(db, symbol, tf)
    if not bars:
        return {"symbol": symbol, "tf": tf, "action": "WAIT",
                "reason": "no_bars"}
    closes = [b["close"] for b in bars]
    ts = bars[-1]["timestamp"]

    try:
        ote = compute_ict_ote(symbol, tf, closes, timestamp=ts)
    except Exception:
        ote = None
    try:
        smc = detect_smc(bars, symbol=symbol, timeframe=tf, timestamp=ts)
    except Exception:
        smc = None
    try:
        regime = compose_regime_signal(closes, symbol=symbol, timestamp=ts)
    except Exception:
        regime = None
    try:
        session = get_session_quality(symbol, timestamp=ts)
    except Exception:
        session = None

    # Direction dérivée du régime dominant (bias), pas forcée.
    reg_name = "UNKNOWN"
    if regime is not None:
        rv = getattr(regime, "regime", None)
        reg_name = rv.value if hasattr(rv, "value") else str(rv)
    direction = "long"
    if reg_name in ("TRENDING_DOWN", "DISTRIBUTION", "MARKDOWN"):
        direction = "short"
        base_level = "A2"
    elif reg_name in ("UNKNOWN", "NEUTRAL", "RANGING", "VOLATILE"):
        # Pas de tendance claire → niveau bas (pas d'edge directionnel)
        base_level = "A3"
    else:
        base_level = "A2"

    # Filtre edge (sélectivité R3/R10) : ne trade que les paires×TF×direction
    # validées par le replay. R6 : selector None → aucun impact.
    if selector is not None:
        dir_key = "BUY" if direction in ("long", "buy") else "SELL"
        filtered, down, reason = selector.apply(symbol, tf, dir_key, base_level)
        if down:
            base_level = filtered  # A1/A2 → A3 (no_edge)

    # Concepts de grammaire V9 (portage additif) — R6 fail-open.
    grammar = None
    try:
        grammar = evaluate_grammar_v9(
            regime_name=reg_name,
            leader=None, follower=None,  # leadership non dispo ici
            bascule_detectee=False, bascule_intensite=0.0,
            trend_direction=direction,
            pliure_detectee=False, tension_score=0.0, pente=0.0,
            zone_type="", compression_etat="",
            antagonismes_count=0,
        )
    except Exception:
        grammar = None

    dec = decide_entry(
        symbol, tf, ts, direction, base_level,
        session=session, ote=ote, smc=smc, regime=regime,
        candidate_risk_pct=1.0,
        grammar=grammar,
    )
    out = dec.as_dict()
    out["regime_direction"] = direction
    out["regime"] = reg_name
    return out


def run_poll(db: Path, *, max_ticks: int = 1, interval: float = 5.0,
             log_db: str = "data/v10_decisions.db",
             use_edge_selector: bool = True) -> dict:
    """Boucle de polling (max_ticks=0 → infini)."""
    results = []
    logger = DecisionLogger(db_path=log_db)
    # Sélecteur d'edges depuis la carte replay (sélectivité R3/R10).
    selector = EdgeSelector.from_replay_batch() if use_edge_selector else None
    if selector is not None and selector.edge_map:
        log.info("Edge selector actif (%d edges chargés)", len(selector.edge_map))
    n = 0
    while max_ticks == 0 or n < max_ticks:
        n += 1
        for symbol in PAIRS:
            for tf in TIMEFRAMES:
                # Décision avec direction dérivée du régime (pas forcée) + filtre edge.
                dec = tick_decision(db, symbol, tf, selector=selector)
                # Persiste les décisions actives BUY/SELL (journal R6/R9).
                if dec.get("action") in ("BUY", "SELL"):
                    logger.append(DecisionRecord(
                        pair=symbol, timeframe=tf, timestamp=dec.get("timestamp", ""),
                        action=dec["action"],
                        signal_level=dec.get("signal_level", "NONE"),
                        filtered_level=dec.get("filtered_level", "NONE"),
                        lot_size=dec.get("lot_size", 0.0),
                    ))
                results.append(dec)
        if max_ticks != 0:
            break
        time.sleep(interval)
    logger.close()
    # Statut de calibration R8 (seuils recalibrés actifs ?)
    calib = ensure_active_thresholds()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_ticks": n,
        "tick_results": results,
        "r8_calibration": calib,
        "audit": {"r10": "paper-only, zero order real"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--ticks", type=int, default=1)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    report = run_poll(db, max_ticks=args.ticks)

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_live_decision_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport live decision écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
