"""v9_bayesian_calibrator_smoke.py — Smoke CLI calibration bayésienne (Axe 1.1 J1).

Charge la DB live (lecture seule), calcule les posteriors Beta(α,β) par contexte
(principle × symbol × timeframe × session × regime) avec n ≥ seuil, et affiche :

  1. Top contextes par P(WR > 0.5)  (edge le plus crédible)
  2. Top contextes par multiplicateur Kelly fractionnel
  3. Brier score global sur la fenêtre récente (calibration confiance déclarée)

N'active RIEN (R25' — le kill switch V9_BAYESIAN_CALIBRATOR_ENABLED reste OFF) ;
n'écrit RIEN (lecture seule stricte). Pur outillage d'analyse.

Usage :
    python scripts/v9_bayesian_calibrator_smoke.py [--min-n 20] [--top 10]
                                                   [--window-days 30] [--brier-days 7]
                                                   [--db PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.v9._bayesian_db import read_confidence_outcomes  # noqa: E402
from core.v9.bayesian_calibrator import BayesianCalibrator, BrierScorer  # noqa: E402
from core.v9.config import DB_PATH  # noqa: E402


def _fmt_ctx(key: tuple) -> str:
    principle, symbol, timeframe, session, regime = key
    return f"{principle[:26]:26s} {symbol:8s} {timeframe:4s} {session:8s} {regime}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke calibration bayésienne V9")
    parser.add_argument("--db", default=str(DB_PATH), help="Chemin DB (défaut: DB_PATH)")
    parser.add_argument("--min-n", type=int, default=20, help="n minimum par contexte")
    parser.add_argument("--top", type=int, default=10, help="Nombre de lignes par classement")
    parser.add_argument("--window-days", type=int, default=30, help="Fenêtre agrégation contextes")
    parser.add_argument("--brier-days", type=int, default=7, help="Fenêtre Brier score")
    args = parser.parse_args()

    print(f"── Bayesian Calibrator smoke ── DB={args.db}")
    calib = BayesianCalibrator(db_path=args.db, window_days=args.window_days)
    contexts = calib.fit_all_contexts(min_n=args.min_n)
    print(f"Contextes avec n ≥ {args.min_n} (fenêtre {args.window_days}j) : {len(contexts)}")

    if not contexts:
        print("Aucun contexte suffisant — DB vide, hors fenêtre, ou inaccessible.")
    else:
        # 1. Top par P(WR > 0.5)
        by_edge = sorted(
            contexts.items(), key=lambda kv: kv[1].prob_above(0.5), reverse=True
        )[: args.top]
        print(f"\n### Top {args.top} contextes par P(WR > 0.5)")
        print(f"{'principle':26s} {'sym':8s} {'tf':4s} {'session':8s} regime  "
              f"| n     mean   P(>0.5)  IC95")
        for key, post in by_edge:
            lo, hi = post.credible_interval_95()
            print(f"{_fmt_ctx(key)}  | {post.n:5d} {post.mean:.3f}  "
                  f"{post.prob_above(0.5):.3f}   [{lo:.2f},{hi:.2f}]")

        # 2. Top par multiplicateur Kelly
        kelly_rows = []
        for key, post in contexts.items():
            k = calib.kelly_fraction(post)
            if k is not None:
                kelly_rows.append((key, post, k))
        kelly_rows.sort(key=lambda t: t[2], reverse=True)
        print(f"\n### Top {args.top} contextes par multiplicateur Kelly (edge confirmé)")
        print(f"{'principle':26s} {'sym':8s} {'tf':4s} {'session':8s} regime  "
              f"| n     mean   kelly_mult")
        for key, post, k in kelly_rows[: args.top]:
            print(f"{_fmt_ctx(key)}  | {post.n:5d} {post.mean:.3f}  {k:.3f}")
        if not kelly_rows:
            print("(aucun contexte avec edge confirmé P(WR>0.5) ≥ 0.6)")

    # 3. Brier score global
    preds, outs = read_confidence_outcomes(args.db, window_days=args.brier_days)
    print(f"\n### Brier score (confiance déclarée) — fenêtre {args.brier_days}j")
    if preds:
        brier = BrierScorer.brier_score(preds, outs)
        base_rate = sum(outs) / len(outs)
        print(f"n={len(preds)}  base_rate(WR)={base_rate:.3f}  Brier={brier:.4f}  "
              f"(0=parfait, 0.25=aléatoire ; cible <0.20)")
        print("Table de fiabilité (déciles de confiance déclarée) :")
        for b in BrierScorer.reliability_table(preds, outs, n_bins=10):
            if b["count"]:
                gap = b["mean_outcome"] - b["mean_pred"]
                print(f"  conf[{b['bin_lower']:.1f}-{b['bin_upper']:.1f}) "
                      f"n={b['count']:5d}  pred={b['mean_pred']:.3f}  "
                      f"obs_WR={b['mean_outcome']:.3f}  gap={gap:+.3f}")
    else:
        print("Aucune décision résolue dans la fenêtre — Brier indisponible.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
