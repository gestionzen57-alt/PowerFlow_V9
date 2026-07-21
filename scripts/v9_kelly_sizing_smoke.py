"""v9_kelly_sizing_smoke.py — Smoke CLI câblage Kelly fractionnel (Axe 1.2 J2).

Charge la DB live (lecture seule), sélectionne N contextes réels (principle ×
symbol × timeframe × session × regime) parmi ceux qui ont ≥ MIN_N observations,
et pour chacun affiche le multiplicateur Kelly bayésien-borné produit par
`KellySizingEngine.compute_multiplier` :

  posterior (α, β, n, mean, P(WR>0.5)) | kelly_full | kelly_fractional | multiplier | applied

Vérifie ensuite que TOUS les multiplicateurs restent dans [floor=0.3, cap=2.0]
et affiche la distribution (min / moyenne / max) sur l'échantillon.

N'active RIEN (le kill switch V9_KELLY_FRACTIONAL_ENABLED reste OFF — le smoke
appelle `compute_multiplier` directement, calcul pur) ; n'écrit RIEN (lecture
seule stricte). Pur outillage d'analyse / preuve de câblage.

Usage :
    python scripts/v9_kelly_sizing_smoke.py [--n 5] [--min-n 20]
                                            [--window-days 30] [--seed 42]
                                            [--db PATH]
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.v9.bayesian_calibrator import BayesianCalibrator  # noqa: E402
from core.v9.config import DB_PATH  # noqa: E402
from core.v9.v9_kelly_sizing import KellySizingEngine  # noqa: E402


def _fmt_ctx(key: tuple) -> str:
    principle, symbol, timeframe, session, regime = key
    return f"{principle[:24]:24s} {symbol:7s} {timeframe:4s} {session:7s} {regime}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke câblage Kelly fractionnel V9")
    parser.add_argument("--db", default=str(DB_PATH), help="Chemin DB (défaut: DB_PATH)")
    parser.add_argument("--n", type=int, default=5, help="Nombre de contextes échantillonnés")
    parser.add_argument("--min-n", type=int, default=20, help="n minimum par contexte")
    parser.add_argument("--window-days", type=int, default=30, help="Fenêtre agrégation")
    parser.add_argument("--seed", type=int, default=42, help="Graine du tirage aléatoire")
    args = parser.parse_args()

    print(f"── Kelly Fractionnel smoke ── DB={args.db}")
    calib = BayesianCalibrator(db_path=args.db, window_days=args.window_days)
    engine = KellySizingEngine(calib, db_path=args.db)
    ks_state = "ON" if engine.is_enabled() else "OFF (défaut R25')"
    print(f"Kill switch V9_KELLY_FRACTIONAL_ENABLED = {ks_state}")

    contexts = calib.fit_all_contexts(min_n=args.min_n)
    print(f"Contextes avec n ≥ {args.min_n} (fenêtre {args.window_days}j) : {len(contexts)}")
    if not contexts:
        print("Aucun contexte suffisant — DB vide, hors fenêtre, ou inaccessible.")
        return 0

    keys = list(contexts.keys())
    random.Random(args.seed).shuffle(keys)
    sample = keys[: args.n]

    floor = KellySizingEngine.DEFAULT_FLOOR
    cap = KellySizingEngine.DEFAULT_CAP
    multipliers: list[float] = []

    print(f"\n### {len(sample)} contextes échantillonnés (seed={args.seed})")
    print(f"{'principle':24s} {'sym':7s} {'tf':4s} {'sess':7s} regime  "
          f"| n     mean  P>0.5  k_full k_frac  MULT   applied")
    for key in sample:
        out = engine.compute_multiplier(key)
        post = out["posterior"] or {}
        multipliers.append(out["multiplier"])
        print(
            f"{_fmt_ctx(key)}  | {post.get('n', 0):5d} "
            f"{post.get('mean', 0.0):.3f} {post.get('prob_above_0_5', 0.0):.3f} "
            f"{out['kelly_full']:+.3f} {out['kelly_fractional']:+.3f} "
            f"{out['multiplier']:.3f}  "
            f"{'YES' if out['applied'] else 'no  '} ({out['reason']})"
        )

    lo, hi = min(multipliers), max(multipliers)
    avg = sum(multipliers) / len(multipliers)
    print(f"\n### Distribution des multiplicateurs (n={len(multipliers)})")
    print(f"  min={lo:.3f}  moyenne={avg:.3f}  max={hi:.3f}")

    in_range = all(floor <= m <= cap for m in multipliers)
    print(f"  bornes [{floor}, {cap}] respectées : {'OUI ✓' if in_range else 'NON ✗'}")
    if not in_range:
        print("  ⚠️  ANOMALIE : un multiplicateur est hors bornes — investigation requise.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
