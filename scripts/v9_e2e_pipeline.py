"""v9_e2e_pipeline.py — Phase 72 motion CEO 48H.

End-to-end pipeline test : simule flux complet.
Verifie integration de tous les modules.

Auteur : Hermes (Phase 72 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.e2e")


def e2e_pipeline(symbol: str = "GBPUSD", n_signals: int = 10) -> dict:
    """Pipeline E2E : signal -> decision -> sizing -> execution."""
    from scripts.v9_strategy_ensemble import compute_ensemble
    from scripts.v9_ftmo_compliance import compute_sizing
    from scripts.v9_kalman_forecast import kalman_projection
    # 1. Generate signals
    signals = []
    for i in range(n_signals):
        res = compute_ensemble(symbol, hour=12, weekday=4,
                                  regime="FAVORABLE", sentiment_score=0.2)
        signals.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "decision": res["decision"],
            "score": res["score"],
        })
    # 2. Kalman projection
    closes = [1.30 + i * 0.001 for i in range(30)]
    proj = kalman_projection(closes, horizon=4)
    # 3. Sizing
    sizing = compute_sizing(10000.0, 25.0, 8.0, daily_dd_pct=0.5)
    return {
        "symbol": symbol,
        "n_signals": n_signals,
        "signals": signals,
        "kalman_projection": proj,
        "sizing": sizing,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 E2E pipeline (Phase 72)",
    )
    parser.add_argument("--symbol", default="GBPUSD")
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args(argv)

    print("=" * 70)
    print("V9 E2E PIPELINE")
    print("=" * 70)
    result = e2e_pipeline(args.symbol, args.n)
    print(f"Symbol      : {result['symbol']}")
    print(f"N signals   : {result['n_signals']}")
    print()
    print("Signals (3) :")
    for s in result["signals"][:3]:
        print(f"  {s['ts'][:19]}  {s['decision']:12s}  "
              f"score={s['score']:+.3f}")
    print()
    print("Kalman projection:")
    proj = result["kalman_projection"]
    if "error" not in proj:
        print(f"  Direction : {proj['direction']}")
        print(f"  Confidence: {proj['confidence']}")
    else:
        print(f"  Error: {proj['error']}")
    print()
    print("Sizing :")
    print(f"  Lot size  : {result['sizing']['lot_size']}")
    print(f"  Reduction : {result['sizing']['reduction_pct']}%")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())
