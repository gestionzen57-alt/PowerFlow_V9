"""V10 Cortex Live — câble le Cortex dans la boucle live (Phase 7, Cognitive Continuum).

Wrapper additif (R2) qui connecte le moteur d'interprétation continue
(`v10_cortex`) à la boucle live de décision. Ne modifie PAS `v10_live_decision.py`
(co-édité par ZCode) — fournit une boucle dédiée qui :
  1. Charge les bars live (forces_snapshots) pour chaque paire.
  2. Calcule les stratégies publiques (ICT OTE + SMC + régime HMM + session).
  3. Interprète via le Cortex (mémoire + cohérence + RAG).
  4. Décide via decide_entry enrichi.
  5. Mémorise l'interprétation dans le registre (v10_behaviors).

R6 fail-open : tick sans données → skip sans crash. R10 : paper-only strict.
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

from core.v10.v10_decision_pipeline import decide_entry  # noqa: E402
from core.v10.v10_decision_log import DecisionRecord, DecisionLogger  # noqa: E402
from core.v10.v10_edge_selector import EdgeSelector  # noqa: E402
from core.v10.v10_ict_ote import compute_ict_ote  # noqa: E402
from core.v10.v10_smc import detect_smc  # noqa: E402
from core.v10.v10_regime_hmm import compose_regime_signal  # noqa: E402
from core.v10.v10_session_filter import get_session_quality  # noqa: E402
from core.v10.v10_cortex import interpret, decide  # noqa: E402
from core.v10.v10_memory_bridge import recall_patterns  # noqa: E402
from core.v10.v10_behavior_registry import (  # noqa: E402
    record_behavior, query_coherence,
)

log = logging.getLogger(__name__)

DEFAULT_DB = ROOT / "data" / "v9_forces.db"
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD"]
TIMEFRAMES = ["H1"]


def load_bars(db: Path, symbol: str, tf: str) -> list:
    """Charge les bars OHLCV live (forces_snapshots)."""
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT timestamp, open, high, low, close, tick_volume "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? "
        "AND is_closed_bar=1 ORDER BY bar_time DESC LIMIT 60",
        (symbol, tf),
    ).fetchall()
    conn.close()
    return [{"timestamp": r[0], "open": r[1], "high": r[2], "low": r[3],
             "close": r[4], "volume": r[5]} for r in rows]


def tick_cortex(db: Path, symbol: str, tf: str,
                selector: EdgeSelector | None = None) -> dict:
    """Décision complète via le Cortex (interprétation + décision + mémorisation)."""
    bars = load_bars(db, symbol, tf)
    if not bars:
        return {"symbol": symbol, "tf": tf, "action": "WAIT", "reason": "no_bars"}
    closes = [b["close"] for b in bars]
    ts = bars[-1]["timestamp"]

    # Stratégies publiques (R6 fail-open)
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

    # Direction dérivée du régime (bias), pas forcée
    reg_name = "UNKNOWN"
    if regime is not None:
        rv = getattr(regime, "regime", None)
        reg_name = rv.value if hasattr(rv, "value") else str(rv)
    direction = "long"
    if reg_name in ("TRENDING_DOWN", "DISTRIBUTION", "MARKDOWN"):
        direction = "short"
        base_level = "A2"
    elif reg_name in ("UNKNOWN", "NEUTRAL", "RANGING", "VOLATILE"):
        base_level = "A3"
    else:
        base_level = "A2"

    # Filtre edge (sélectivité R3/R10)
    if selector is not None:
        dir_key = "BUY" if direction in ("long", "buy") else "SELL"
        filtered, down, reason = selector.apply(symbol, tf, dir_key, base_level)
        if down:
            base_level = filtered

    # Interprétation via le Cortex (mémoire + cohérence)
    interp = interpret(
        pair=symbol, timeframe=tf, timestamp=ts,
        observation_qualification=reg_name,
        regime_hmm=reg_name,
        memory_bridge=__import__("core.v10.v10_memory_bridge",
                                fromlist=["recall_patterns"]),
        behavior_registry=__import__("core.v10.v10_behavior_registry",
                                     fromlist=["query_coherence"]),
    )

    # Enrichissement : delta_flow + liquidity_map + grammar_final (lecture complète)
    try:
        from core.v10.v10_cortex_enrich import enrich_interp
        interp_dict = interp.as_dict()
        interp_dict = enrich_interp(
            interp_dict, symbol=symbol, timeframe=tf, bars=bars, timestamp=ts)
        interp_rich = interp_dict
    except Exception:
        interp_rich = interp.as_dict()

    # Décision via decide_entry enrichi
    dec = decide_entry(
        symbol, tf, ts, direction, base_level,
        session=session, ote=ote, smc=smc, regime=regime,
        candidate_risk_pct=1.0,
    )
    out = dec.as_dict()
    out["regime_direction"] = direction
    out["regime"] = reg_name
    out["cortex"] = interp_rich

    # Mémorisation (BASE 3) — enregistre l'interprétation dans le registre
    try:
        record_behavior(
            timestamp=ts, pair=symbol, timeframe=tf,
            observation_qualification=reg_name, regime_hmm=reg_name,
            is_win=None, pnl_pips=None, source_ref="cortex_live")
        out["memorized"] = True
    except Exception:
        out["memorized"] = False
    return out


def run_poll(db: Path, *, max_ticks: int = 1, interval: float = 5.0,
             log_db: str = "data/v10_decisions.db",
             use_edge_selector: bool = True) -> dict:
    """Boucle de polling Cortex (max_ticks=0 → infini)."""
    results = []
    logger = DecisionLogger(db_path=log_db)
    selector = EdgeSelector.from_replay_batch() if use_edge_selector else None
    n = 0
    while max_ticks == 0 or n < max_ticks:
        n += 1
        for symbol in PAIRS:
            for tf in TIMEFRAMES:
                dec = tick_cortex(db, symbol, tf, selector=selector)
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
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_ticks": n,
        "tick_results": results,
        "audit": {"r10": "paper-only, zero order real"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--ticks", type=int, default=1)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    report = run_poll(db, max_ticks=args.ticks)

    if args.output:
        Path(args.output).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
