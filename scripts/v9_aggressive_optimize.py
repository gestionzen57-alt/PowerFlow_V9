#!/usr/bin/env python
"""v9_aggressive_optimize — grid search TP × SL × Kelly (lecture seule).

Chantier 4b (recadré motion CEO 2026-07-18). Recherche la configuration
(tp, sl, kelly_K) la plus performante ET la plus stable en walk-forward, sur
les décisions résolues de ``data/v9_forces.db``.

Le score pénalise l'instabilité walk-forward (leçon du backtest : un uplift
non stationnaire n'est pas exploitable) :

    score = total_pips · min(1, WF_STABILITY_MAX_SPREAD / wf_spread)

Réutilise la simulation first-touch, le sizing Kelly et les métriques de
``v9_aggressive_paper_trade``. Lecture seule.

Usage :
    python scripts/v9_aggressive_optimize.py --db data/v9_forces.db \
        --report docs/reports/AGGRESSIVE_OPTIMIZE_20260718.md
"""
from __future__ import annotations

import argparse
import bisect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9 import v9_aggressive_strategy as ags  # noqa: E402
from core.v9 import v9_sizing_confidence as szc  # noqa: E402
import scripts.v9_aggressive_paper_trade as bt  # noqa: E402

# Grilles (bornes mission : TP∈[10,30], SL∈[8,18]).
TP_GRID = (10.0, 15.0, 20.0, 25.0, 30.0)
SL_GRID = (8.0, 12.0, 15.0, 18.0)
K_GRID = (0.1, 0.25, 0.5)


@dataclass
class ConfigResult:
    tp: float
    sl: float
    kelly: float
    total_pips: float
    profit_factor: float
    win_rate: float
    max_drawdown: float
    wf_spread: float
    score: float


def stability_score(total_pips: float, wf_spread: float) -> float:
    """Pips pénalisés par l'instabilité walk-forward."""
    if wf_spread <= bt.WF_STABILITY_MAX_SPREAD:
        return total_pips
    penalty = bt.WF_STABILITY_MAX_SPREAD / wf_spread if wf_spread > 0 else 1.0
    return total_pips * penalty


def precompute_pwin(recs: list, market: dict, k_folds: int) -> list[float]:
    """p_win par décision via walk-forward (indépendant de tp/sl/K)."""
    global_wr = sum(r.baseline_win for r in recs) / max(1, len(recs))
    for r in recs:
        pip = ags._pip_size(r.symbol)
        times = market["times"].get((r.symbol, r.timeframe), [])
        bars = market["bars"].get((r.symbol, r.timeframe), [])
        pos = bisect.bisect_right(times, r.entry_bar_time)
        r.vol_atr = ags.compute_atr_pips(bars[:pos], pip)

    def cell_key(r) -> str:
        return f"{r.symbol}|{r.timeframe}|{ags._bucket_vol_atr(r.vol_atr)}|{r.direction}"

    n = len(recs)
    fold_size = max(1, n // k_folds)
    p_win = [global_wr] * n
    for f in range(k_folds):
        lo = f * fold_size
        hi = n if f == k_folds - 1 else (f + 1) * fold_size
        train = recs[:lo] + recs[hi:]
        agg: dict[str, list[int]] = {}
        for tr in train:
            agg.setdefault(cell_key(tr), []).append(tr.baseline_win)
        for r in recs[lo:hi]:
            w = agg.get(cell_key(r), [])
            p_win[r.idx] = bt.beta_shrunk_winrate(sum(w), len(w), global_wr)
    return p_win


def run_config(
    recs: list, market: dict, p_win: list[float],
    tp: float, sl: float, kelly: float, *, k_folds: int = 5, gate: bool = True,
) -> ConfigResult:
    """Simule une config (tp/sl fixes + Kelly K) et calcule score + stabilité."""
    pnls: list[float] = []
    for r in recs:
        fb = bt.forward_bars_for(r, market)
        pip = ags._pip_size(r.symbol)
        if not fb:
            pnls.append(0.0)
            continue
        out, _ = bt.simulate_first_touch(r.entry_close, r.direction, tp, sl, fb, pip)
        gated = gate and ags.is_short_gated(r.direction, r.regime)
        sd = szc.compute_size(p_win[r.idx], tp, sl, kelly_fraction=kelly, gated=gated)
        pnls.append(out * sd.size)

    m = bt.compute_metrics(pnls)
    n = len(pnls)
    fold_size = max(1, n // k_folds)
    wf = [bt.compute_metrics(pnls[f * fold_size:(n if f == k_folds - 1 else (f + 1) * fold_size)])
          for f in range(k_folds)]
    spread = bt.walk_forward_spread(wf)
    return ConfigResult(
        tp=tp, sl=sl, kelly=kelly, total_pips=m.total_pips,
        profit_factor=m.profit_factor, win_rate=m.win_rate,
        max_drawdown=m.max_drawdown, wf_spread=spread,
        score=stability_score(m.total_pips, spread),
    )


def grid_search(recs: list, market: dict, p_win: list[float], *, k_folds: int = 5) -> list[ConfigResult]:
    results = [run_config(recs, market, p_win, tp, sl, k, k_folds=k_folds)
               for tp in TP_GRID for sl in SL_GRID for k in K_GRID]
    results.sort(key=lambda c: c.score, reverse=True)
    return results


def build_report(results: list[ConfigResult], n_dec: int) -> str:
    lines = ["# Optimisation agressive — grid search TP×SL×Kelly (2026-07-18)\n"]
    lines.append(f"> Lecture seule, {n_dec} décisions, {len(results)} configs "
                 f"(TP×SL×K = {len(TP_GRID)}×{len(SL_GRID)}×{len(K_GRID)}). "
                 f"Score = pips pénalisés par l'instabilité walk-forward.\n")
    stable = [c for c in results if c.wf_spread <= bt.WF_STABILITY_MAX_SPREAD]
    lines.append(f"\n**Configs stables (WF spread ≤ {bt.WF_STABILITY_MAX_SPREAD:.0f} pts) : "
                 f"{len(stable)}/{len(results)}.**\n")
    lines.append("\n## Top 12 configurations (par score)\n")
    lines.append("| Rang | TP | SL | K | Pips | PF | WR | maxDD | WF spread | Score |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, c in enumerate(results[:12], 1):
        pf = "∞" if c.profit_factor == float("inf") else f"{c.profit_factor:.2f}"
        lines.append(f"| {i} | {c.tp:.0f} | {c.sl:.0f} | {c.kelly} | {c.total_pips:+.0f} "
                     f"| {pf} | {c.win_rate:.1f}% | {c.max_drawdown:.0f} "
                     f"| {c.wf_spread:.1f} | {c.score:+.0f} |")
    lines.append("\n## Lecture\n")
    if not stable:
        lines.append("- **Aucune configuration stable** : toutes dépassent le seuil de "
                     "variance walk-forward. Confirme le diagnostic NO-GO — l'edge est "
                     "période-spécifique quelle que soit la paramétrisation TP/SL/K.\n")
    else:
        best = stable[0]
        lines.append(f"- Meilleure config stable : TP={best.tp:.0f}/SL={best.sl:.0f}/"
                     f"K={best.kelly} → {best.total_pips:+.0f} pips, PF "
                     f"{best.profit_factor:.2f}, WF spread {best.wf_spread:.1f} pts.\n")
    lines.append("- Chiffres mesurés sur données réelles, non extrapolés. Aucune "
                 "promotion live sans revue Søn (R28).\n")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Grid search agressif V9 (lecture seule)")
    ap.add_argument("--db", default="data/v9_forces.db")
    ap.add_argument("--report", default=None)
    ap.add_argument("--horizon", type=int, default=bt.DEFAULT_HORIZON)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args(argv)

    if not Path(args.db).exists():
        print(f"[ERREUR] DB introuvable : {args.db}")
        return 2

    print("[1/3] chargement décisions…")
    recs, market = bt.load_decisions(args.db, args.horizon)
    print(f"      {len(recs)} décisions")
    print("[2/3] p_win walk-forward + grid search…")
    p_win = precompute_pwin(recs, market, args.folds)
    results = grid_search(recs, market, p_win, k_folds=args.folds)
    print("[3/3] rapport…")
    report = build_report(results, len(recs))
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"      écrit : {args.report}")
    else:
        print(report)
    top = results[0]
    print(f"  meilleur score : TP={top.tp:.0f}/SL={top.sl:.0f}/K={top.kelly} "
          f"pips={top.total_pips:+.0f} WFspread={top.wf_spread:.1f} score={top.score:+.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
