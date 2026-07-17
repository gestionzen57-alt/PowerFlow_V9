"""v9_strategy_pole_run.py — CLI runner pour le pôle stratégie.

Usage :
    python scripts/v9_strategy_pole_run.py --meta
    python scripts/v9_strategy_pole_run.py --full
    python scripts/v9_strategy_pole_run.py --recommend PRICE_LAG_AT_NODE_BIRTH new_york NEUTRE
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.v9_strategy_pole import (  # noqa: E402
    StrategyCatalogue,
    StrategySelector,
    StrategyTuner,
    compute_meta_metrics,
    POLE_VERSION,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pôle stratégie V9 runner")
    parser.add_argument("--meta", action="store_true",
                        help="Métriques méta globales uniquement")
    parser.add_argument("--catalogue", action="store_true",
                        help="Recalcule et affiche le catalogue")
    parser.add_argument("--tune", action="store_true",
                        help="Lance le tuning grid search")
    parser.add_argument("--full", action="store_true",
                        help="Full pipeline : catalogue + tune + meta + save")
    parser.add_argument("--recommend", nargs=3, metavar=("PRINCIPLE", "SESSION", "REGIME"),
                        help="Recommandation stratégique pour (principle, session, regime)")
    parser.add_argument("--min-n", type=int, default=20)
    args = parser.parse_args()

    cat = StrategyCatalogue()
    tuner = StrategyTuner()
    selector = StrategySelector(catalogue=cat, tuner=tuner)

    if args.full or args.catalogue:
        n = cat.recompute(min_n=args.min_n)
        path = cat.save_cache()
        print(f"[catalogue v{POLE_VERSION}] {n} segments → {path}")

    if args.full or args.tune:
        results = tuner.tune_all(catalogue=cat)
        path = tuner.save_overrides(results)
        print(f"[tuner] {len(results)} segments optimisés → {path}")
        for r in results:
            print(
                f"  {r['principle'][:30]:>30} {r['session']:>10} {r['regime']:>15} "
                f"TP={r['best_tp']:.0f} SL={r['best_sl']:.0f} "
                f"exp={r['best_expectancy']:+.2f} n={r['n_trades']}"
            )

    if args.full or args.meta:
        meta = compute_meta_metrics()
        print("\n[meta metrics]")
        print(json.dumps(meta, indent=2, ensure_ascii=False))

    if args.recommend:
        principle, session, regime = args.recommend
        rec = selector.recommend(principle, session, regime)
        print(json.dumps({
            "principle": rec.principle,
            "session": rec.session,
            "regime": rec.regime,
            "recommended_tp": rec.recommended_tp,
            "recommended_sl": rec.recommended_sl,
            "recommended_strategy": rec.recommended_strategy,
            "confidence": rec.confidence,
            "sample_size": rec.sample_size,
            "source": rec.source,
            "rationale": rec.rationale,
        }, indent=2, ensure_ascii=False))

    if not (args.meta or args.catalogue or args.tune or args.full or args.recommend):
        # Default : meta + top catalogue
        cat.recompute(min_n=args.min_n)
        meta = compute_meta_metrics()
        print(json.dumps(meta["totals"], indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())