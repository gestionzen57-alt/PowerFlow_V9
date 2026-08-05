"""V10 Strategy Demo — compose la stack publique sur les données live DB (Sprint 12).

Enchaîne sur les bars OHLCV live (forces_snapshots) :
  1. ICT OTE (Kill Zone + zone 62-79%)
  2. SMC (BOS/MSS + Order Block + FVG)
  3. Régime HMM (hmmlearn) + changepoint (ruptures)
  4. Wyckoff consolidé (VSA + compression/extension)
  5. Filter compositor (session+OTE+SMC+regime) sur un niveau A1
  6. Risk shield (net exposure simulé)
→ rapport JSON d'exploitation des stratégies publiques.

R6 fail-open : chaque étape peut échouer sans casser le rapport. R10 : compute only.
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

from core.v10.v10_ict_ote import compute_ict_ote  # noqa: E402
from core.v10.v10_smc import detect_smc  # noqa: E402
from core.v10.v10_regime_hmm import compose_regime_signal  # noqa: E402
from core.v10.v10_wyckoff_consolidated import consolidate_wyckoff  # noqa: E402
from core.v10.v10_filter_compositor import compose_filters  # noqa: E402
from core.v10.v10_session_filter import get_session_quality  # noqa: E402

log = logging.getLogger(__name__)
DEFAULT_DB = ROOT / "data" / "v9_forces.db"


def load_bars(db_path: Path, symbol: str, timeframe: str, limit: int = 60) -> list:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT open, high, low, close, tick_volume, timestamp "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?", (symbol, timeframe, limit)
    ).fetchall()
    conn.close()
    rows.reverse()  # croissant
    return [{
        "open": float(o), "high": float(h), "low": float(lo),
        "close": float(c), "tick_volume": float(v or 0.0), "timestamp": ts,
    } for o, h, lo, c, v, ts in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--timeframe", default="H1")
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        log.error("DB introuvable: %s", db)
        return 2

    bars = load_bars(db, args.symbol, args.timeframe)
    if not bars:
        log.error("Aucune barre %s %s", args.symbol, args.timeframe)
        return 2
    closes = [b["close"] for b in bars]
    ts = bars[-1]["timestamp"]
    log.info("Chargé %d barres %s %s (dernière %s)", len(bars), args.symbol,
             args.timeframe, ts)

    report = {
        "symbol": args.symbol, "timeframe": args.timeframe,
        "n_bars": len(bars), "timestamp": ts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit": {"r10": "compute only, zero order real"},
    }

    # 1. ICT OTE
    try:
        ote = compute_ict_ote(args.symbol, args.timeframe, closes,
                              timestamp=ts)
        report["ict_ote"] = ote.as_dict()
    except Exception as e:
        report["ict_ote"] = {"error": type(e).__name__}

    # 2. SMC
    try:
        smc = detect_smc(bars, symbol=args.symbol, timeframe=args.timeframe,
                         timestamp=ts)
        report["smc"] = smc.as_dict()
    except Exception as e:
        report["smc"] = {"error": type(e).__name__}

    # 3. Régime HMM
    try:
        regime = compose_regime_signal(closes, symbol=args.symbol,
                                       timestamp=ts)
        report["regime_hmm"] = regime.as_dict()
    except Exception as e:
        report["regime_hmm"] = {"error": type(e).__name__}

    # 4. Wyckoff consolidé (utilise les états VSA/CE si dispo, sinon neutre)
    try:
        wyck = consolidate_wyckoff(
            args.symbol, args.timeframe, ts,
            vsa_state=None,  # pas de VSAEngineState ici — source externe
            ce_signal=None,
        )
        report["wyckoff"] = wyck.as_dict()
    except Exception as e:
        report["wyckoff"] = {"error": type(e).__name__}

    # 5. Filter compositor sur niveau A1
    try:
        session = get_session_quality(args.symbol, timestamp=ts)
        comp = compose_filters(
            "A1", symbol=args.symbol, timeframe=args.timeframe, timestamp=ts,
            session=session, ote=ote, smc=smc, regime=regime,
        )
        report["filter_compositor"] = comp.as_dict()
    except Exception as e:
        report["filter_compositor"] = {"error": type(e).__name__}

    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_strategy_demo_{args.symbol}_{args.timeframe}_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Rapport écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
