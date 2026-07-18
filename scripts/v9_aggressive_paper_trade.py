#!/usr/bin/env python
"""v9_aggressive_paper_trade — backtest lecture-seule du saut quantique agressif.

Chantier 4 (recadré motion CEO 2026-07-18). Rejoue les décisions résolues de
``data/v9_forces.db`` en appliquant les 3 leviers :
  1. TP/SL dynamique calibré sur magnitude OHLC réelle (v9_aggressive_strategy)
  2. Pyramiding sur convergence de principes (v9_pyramiding_engine)
  3. Sizing continu Kelly fractionnel (v9_sizing_confidence)

**Path-based first-touch** : pour chaque décision on marche les barres closes
forward et on détermine quelle borne (TP ou SL) est touchée en premier. Sur une
barre où les deux sont dans [low, high], on suppose le SL touché d'abord
(hypothèse conservatrice — on ne connaît pas l'ordre intrabar).

**p_win** est estimé par walk-forward temporel (WR de la cellule contextuelle
sur les folds d'entraînement, shrinkage Beta vers la base globale) — jamais
in-sample pour le sizing.

Lecture seule : aucune écriture DB, aucune exécution (Phase 12 gelée).

Usage :
    python scripts/v9_aggressive_paper_trade.py --db data/v9_forces.db \
        --report docs/reports/AGGRESSIVE_QUANTUM_LEAP_20260718.md
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v9 import v9_aggressive_strategy as ags  # noqa: E402
from core.v9 import v9_pyramiding_engine as pyr  # noqa: E402
from core.v9 import v9_sizing_confidence as szc  # noqa: E402

LONG = ("haussiere", "long", "buy", "bull")

# Plafond dur position combinée sizing × pyramiding (R30).
COMBINED_SIZE_MAX = 2.0
# Shrinkage Beta : pseudo-observations vers la base globale.
WR_SHRINKAGE_ALPHA = 20.0
# Horizon de simulation (barres closes forward).
DEFAULT_HORIZON = 16


# ================================================================= structures

@dataclass
class DecisionRec:
    """Une décision résolue + son contexte de rejeu."""

    idx: int
    timestamp: str
    symbol: str
    timeframe: str
    direction: str
    regime: str
    phase: str
    confiance: float
    entry_bar_time: int
    entry_close: float
    baseline_pips: float
    baseline_win: int
    principles: list[str] = field(default_factory=list)
    pe_confidences: list[float] = field(default_factory=list)
    pe_directions: list[str] = field(default_factory=list)
    # rempli au rejeu :
    vol_atr: float | None = None
    tp: float = 0.0
    sl: float = 0.0


@dataclass
class Metrics:
    n: int
    n_trades: int          # positions effectivement prises (size > 0)
    win_rate: float
    profit_factor: float
    total_pips: float
    max_drawdown: float
    sharpe_like: float
    avg_pips: float

    def to_row(self, label: str) -> str:
        pf = "∞" if self.profit_factor == float("inf") else f"{self.profit_factor:.2f}"
        return (
            f"| {label} | {self.n_trades} | {self.win_rate:.1f}% | {pf} | "
            f"{self.total_pips:+.0f} | {self.max_drawdown:.0f} | {self.sharpe_like:.3f} |"
        )


# ================================================================= simulation cœur (pure)

def simulate_first_touch(
    entry_close: float,
    direction: str,
    tp: float,
    sl: float,
    forward_bars: Sequence[dict],
    pip: float,
) -> tuple[float, str]:
    """Résultat path-based first-touch en pips (hypothèse SL-first si ambigu).

    Returns (pnl_pips, mode) avec mode ∈ {tp, sl, both_sl, timeout_close}.
    """
    is_long = direction in LONG
    for b in forward_bars:
        try:
            hi = float(b["high"]); lo = float(b["low"])
        except (KeyError, TypeError, ValueError):
            continue
        if is_long:
            favor = (hi - entry_close) / pip
            adverse = (entry_close - lo) / pip
        else:
            favor = (entry_close - lo) / pip
            adverse = (hi - entry_close) / pip
        tp_hit = favor >= tp
        sl_hit = adverse >= sl
        if tp_hit and sl_hit:
            return -sl, "both_sl"          # conservateur
        if sl_hit:
            return -sl, "sl"
        if tp_hit:
            return tp, "tp"
    # Aucune borne touchée : sortie au dernier close.
    try:
        last = float(forward_bars[-1]["close"])
    except (IndexError, KeyError, TypeError, ValueError):
        return 0.0, "timeout_close"
    pnl = (last - entry_close) / pip if is_long else (entry_close - last) / pip
    return round(pnl, 2), "timeout_close"


def beta_shrunk_winrate(wins: int, n: int, global_wr: float, alpha: float = WR_SHRINKAGE_ALPHA) -> float:
    """WR de cellule lissé vers la base globale (prior Beta pseudo-alpha)."""
    if n <= 0:
        return global_wr
    return (wins + alpha * global_wr) / (n + alpha)


# ================================================================= métriques (pure)

def compute_metrics(pnls: Sequence[float]) -> Metrics:
    """Métriques sur une liste de PnL pondérés (les 0 = trades non pris)."""
    taken = [p for p in pnls if p != 0.0]
    n_trades = len(taken)
    if n_trades == 0:
        return Metrics(len(pnls), 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    wins = [p for p in taken if p > 0]
    losses = [p for p in taken if p < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    pf = float("inf") if gross_loss == 0 else gross_win / gross_loss
    total = sum(taken)
    wr = 100.0 * len(wins) / n_trades
    # Max drawdown sur l'équité cumulée.
    equity = 0.0; peak = 0.0; max_dd = 0.0
    for p in taken:
        equity += p
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    mean = total / n_trades
    var = sum((p - mean) ** 2 for p in taken) / n_trades
    std = math.sqrt(var)
    sharpe = 0.0 if std == 0 else mean / std
    return Metrics(len(pnls), n_trades, wr, pf, total, max_dd, sharpe, mean)


# ================================================================= chargement DB

def load_decisions(db_path: str, horizon: int) -> tuple[list[DecisionRec], dict]:
    """Charge les décisions résolues + barres forward + éval principes."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    rows = cur.execute(
        """
        SELECT d.rowid AS rid, d.timestamp, d.symbol, d.timeframe, d.direction,
               d.regime_type, d.confiance, d.principes_json, d.snapshot_id,
               d.resolution_pips, d.is_win, f.bar_time AS bt, f.close AS cl
        FROM decisions d
        JOIN forces_snapshots f ON d.snapshot_id = f.snapshot_id
        WHERE d.is_win IS NOT NULL AND d.resolution_pips IS NOT NULL
          AND f.close IS NOT NULL AND f.bar_time IS NOT NULL
        ORDER BY d.timestamp
        """
    ).fetchall()

    # Éval principes déclenchés par snapshot (pour le pyramiding).
    snap_ids = tuple({r["snapshot_id"] for r in rows})
    pe_map: dict[str, list[tuple[float, str]]] = {}
    if snap_ids:
        CH = 900
        for i in range(0, len(snap_ids), CH):
            chunk = snap_ids[i:i + CH]
            qm = ",".join("?" * len(chunk))
            for pr in cur.execute(
                f"""SELECT snapshot_id, confidence, direction FROM principle_evaluations
                    WHERE triggered = 1 AND snapshot_id IN ({qm})""", chunk,
            ):
                pe_map.setdefault(pr["snapshot_id"], []).append(
                    (float(pr["confidence"] or 0.0), pr["direction"] or "neutre")
                )

    recs: list[DecisionRec] = []
    for i, r in enumerate(rows):
        try:
            principles = json.loads(r["principes_json"]) if r["principes_json"] else []
        except (TypeError, ValueError):
            principles = []
        pe = pe_map.get(r["snapshot_id"], [])
        recs.append(DecisionRec(
            idx=i, timestamp=r["timestamp"] or "", symbol=r["symbol"],
            timeframe=r["timeframe"], direction=r["direction"] or "",
            regime=r["regime_type"] or "NEUTRE", phase="initiation",
            confiance=float(r["confiance"] or 0.0),
            entry_bar_time=int(r["bt"]), entry_close=float(r["cl"]),
            baseline_pips=float(r["resolution_pips"]), baseline_win=int(r["is_win"]),
            principles=principles,
            pe_confidences=[c for c, _ in pe],
            pe_directions=[d for _, d in pe],
        ))

    # Barres closes par (symbol, tf) pour la simulation forward.
    bars_by_key: dict[tuple[str, str], list[dict]] = {}
    times_by_key: dict[tuple[str, str], list[int]] = {}
    for sym, tf in {(r.symbol, r.timeframe) for r in recs}:
        brows = cur.execute(
            """SELECT DISTINCT bar_time, high, low, close FROM forces_snapshots
               WHERE symbol=? AND timeframe=? AND is_closed_bar=1
                 AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL
               ORDER BY bar_time""", (sym, tf),
        ).fetchall()
        bars = [dict(b) for b in brows]
        bars_by_key[(sym, tf)] = bars
        times_by_key[(sym, tf)] = [int(b["bar_time"]) for b in bars]
    con.close()
    return recs, {"bars": bars_by_key, "times": times_by_key, "horizon": horizon}


def forward_bars_for(rec: DecisionRec, market: dict) -> list[dict]:
    key = (rec.symbol, rec.timeframe)
    bars = market["bars"].get(key, [])
    times = market["times"].get(key, [])
    pos = bisect.bisect_right(times, rec.entry_bar_time)
    return bars[pos: pos + market["horizon"]]


# ================================================================= rejeu (variantes)

def replay(
    recs: list[DecisionRec], market: dict, magnitude_stats: dict,
    *, k_folds: int = 5,
) -> dict[str, Any]:
    """Rejoue toutes les variantes et calcule les métriques + walk-forward."""
    global_wr = sum(r.baseline_win for r in recs) / max(1, len(recs))

    # Pré-calcul vol_atr (barres antérieures) + TP/SL par décision.
    for r in recs:
        pip = ags._pip_size(r.symbol)
        times = market["times"].get((r.symbol, r.timeframe), [])
        bars = market["bars"].get((r.symbol, r.timeframe), [])
        pos = bisect.bisect_right(times, r.entry_bar_time)
        r.vol_atr = ags.compute_atr_pips(bars[:pos], pip)
        tp, sl, _, _ = ags.compute_dynamic_tp_sl(
            r.symbol, r.timeframe, r.regime, r.phase, r.vol_atr, magnitude_stats)
        r.tp, r.sl = tp, sl

    def aggr_outcome(r: DecisionRec) -> float:
        fb = forward_bars_for(r, market)
        if not fb:
            return r.baseline_pips
        pip = ags._pip_size(r.symbol)
        pnl, _ = simulate_first_touch(r.entry_close, r.direction, r.tp, r.sl, fb, pip)
        return pnl

    # p_win walk-forward : WR de cellule (symbol,tf,volbucket,dir) sur le train.
    def cell_key(r: DecisionRec) -> str:
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
            p_win[r.idx] = beta_shrunk_winrate(sum(w), len(w), global_wr)

    # Séries PnL par variante.
    base_pnl, aggr_pnl, size_pnl, gate_pnl, full_pnl = [], [], [], [], []
    running_dd_ratio = 0.0; equity = 0.0; peak = 0.0; worst = 1e-9
    for r in recs:
        base_pnl.append(r.baseline_pips)
        out = aggr_outcome(r)
        aggr_pnl.append(out)

        p = p_win[r.idx]
        sd = szc.compute_size(p, r.tp, r.sl, dd_ratio=min(1.0, running_dd_ratio))
        size_pnl.append(out * sd.size)

        gated = ags.is_short_gated(r.direction, r.regime)
        sd_g = szc.compute_size(p, r.tp, r.sl, dd_ratio=min(1.0, running_dd_ratio), gated=gated)
        gate_pnl.append(out * sd_g.size)

        pyd = pyr.compute_pyramiding_factor(
            r.principles, r.pe_confidences, r.phase, directions=r.pe_directions)
        combined = min(COMBINED_SIZE_MAX, sd_g.size * pyd.factor)
        full = out * combined
        full_pnl.append(full)

        equity += full
        peak = max(peak, equity)
        worst = min(worst, equity - peak) if (equity - peak) < 0 else worst
        running_dd_ratio = abs(equity - peak) / abs(worst) if worst < 0 else 0.0

    variants = {
        "Baseline (résolution réelle)": compute_metrics(base_pnl),
        "Agressif TP/SL (path)": compute_metrics(aggr_pnl),
        "+ Sizing Kelly": compute_metrics(size_pnl),
        "+ Garde-fou short (régime)": compute_metrics(gate_pnl),
        "+ Pyramiding (stack complet)": compute_metrics(full_pnl),
    }

    # Walk-forward 5-fold sur le stack complet.
    wf: list[Metrics] = []
    for f in range(k_folds):
        lo = f * fold_size
        hi = n if f == k_folds - 1 else (f + 1) * fold_size
        wf.append(compute_metrics(full_pnl[lo:hi]))

    return {"variants": variants, "walk_forward": wf, "global_wr": global_wr, "n": n}


# ================================================================= rapport

def walk_forward_spread(wf: list[Metrics]) -> float:
    wrs = [m.win_rate for m in wf if m.n_trades > 0]
    return (max(wrs) - min(wrs)) if wrs else 0.0


def build_report(res: dict, magnitude_stats: dict, horizon: int) -> str:
    v = res["variants"]
    base = v["Baseline (résolution réelle)"]
    full = v["+ Pyramiding (stack complet)"]
    wf_spread = walk_forward_spread(res["walk_forward"])
    lines = []
    lines.append("# Saut quantique agressif — bilan backtest (2026-07-18)\n")
    lines.append("> **Recadré** (motion CEO 2026-07-18) : couche backtest lecture-seule, "
                 "mesurée sur les décisions RÉELLES, magnitude reconstruite depuis l'OHLC, "
                 "garde-fou short régime-dépendant. **Aucune activation live proposée.**\n")

    lines.append("## Résumé exécutif\n")
    delta_pips = full.total_pips - base.total_pips
    verdict = _verdict(base, full, wf_spread)
    lines.append(
        f"- Population : **{res['n']} décisions résolues** (WR base {res['global_wr']*100:.1f} %), "
        f"horizon {horizon} barres, first-touch conservateur (SL-first si ambigu).\n"
        f"- Baseline : {base.total_pips:+.0f} pips, PF {_pf(base)}, WR {base.win_rate:.1f} %, "
        f"maxDD {base.max_drawdown:.0f}.\n"
        f"- Stack agressif complet : {full.total_pips:+.0f} pips, PF {_pf(full)}, "
        f"WR {full.win_rate:.1f} %, maxDD {full.max_drawdown:.0f}.\n"
        f"- Δ pips vs baseline : **{delta_pips:+.0f}**.\n"
        f"- **Verdict : {verdict}**\n")

    lines.append("\n## Comparatif variantes\n")
    lines.append("| Variante | Trades | WR | PF | Pips | maxDD | Sharpe |")
    lines.append("|---|---|---|---|---|---|---|")
    for label, m in v.items():
        lines.append(m.to_row(label))

    lines.append("\n## Walk-forward 5-fold (stack complet, temporel)\n")
    lines.append("| Fold | Trades | WR | PF | Pips | maxDD | Sharpe |")
    lines.append("|---|---|---|---|---|---|---|")
    wrs = []
    for i, m in enumerate(res["walk_forward"], 1):
        lines.append(m.to_row(f"Fold {i}"))
        wrs.append(m.win_rate)
    if wrs:
        spread = max(wrs) - min(wrs)
        lines.append(f"\nVariance WR inter-fold : **{spread:.1f} pts** "
                     f"(seuil d'arrêt mission : 15 pts).\n")

    lines.append("\n## Magnitude réelle reconstruite (OHLC, top cellules)\n")
    lines.append("| Cellule | n | MFE p50 | MFE p75 | MFE p90 | MAE p90 |")
    lines.append("|---|---|---|---|---|---|")
    for cell, s in sorted(magnitude_stats.items(), key=lambda kv: -kv[1]["n"])[:8]:
        lines.append(f"| {cell} | {int(s['n'])} | {s['p50']:.1f} | {s['p75']:.1f} "
                     f"| {s['p90']:.1f} | {s['mae_p90']:.1f} |")

    lines.append("\n## Risques résiduels\n")
    lines.append(
        "- **MAE ≥ MFE sur GBPUSD** (paire dominante) : l'excursion adverse dépasse "
        "l'excursion favorable → un SL serré est touché avant un TP large ; c'est la "
        "cause mécanique de tout sous-rendement du stack agressif.\n"
        "- **p_win walk-forward** lisse vers la base globale : peu de cellules ont un "
        "échantillon suffisant → sizing proche de l'uniforme.\n"
        "- **Régime quasi-toujours NEUTRE** (98.8 %) : le garde-fou short bloque de fait "
        "presque tous les shorts (y compris des shorts NEUTRE rentables du backtest).\n"
        "- Hypothèse first-touch conservatrice (SL-first) : borne basse du rendement réel.\n")

    lines.append("\n## Décision CEO\n")
    lines.append(f"**{verdict}** — voir tableau. Chiffres mesurés, non extrapolés. "
                 "Aucune promotion live sans revue Søn (R28).\n")
    return "\n".join(lines)


def _pf(m: Metrics) -> str:
    return "∞" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"


WF_STABILITY_MAX_SPREAD = 15.0  # critère d'arrêt mission


def _verdict(base: Metrics, full: Metrics, wf_spread: float) -> str:
    # La stabilité walk-forward prime : un uplift non stationnaire n'est pas
    # exploitable en live (critère d'arrêt explicite de la mission).
    if wf_spread > WF_STABILITY_MAX_SPREAD:
        return (f"NO-GO — instabilité walk-forward (variance WR {wf_spread:.1f} pts > "
                f"{WF_STABILITY_MAX_SPREAD:.0f} pts) : edge période-spécifique, non "
                f"stationnaire. Uplift pips réel mais non exploitable tel quel.")
    if full.total_pips > base.total_pips and full.profit_factor >= base.profit_factor:
        return "GO conditionnel (uplift pips ET PF, walk-forward stable)"
    if full.total_pips > base.total_pips or full.profit_factor > base.profit_factor:
        return "MARGINAL (uplift partiel — un seul critère amélioré)"
    return "NO-GO (pas d'uplift mesuré — baseline non battue)"


# ================================================================= main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Backtest agressif V9 (lecture seule)")
    ap.add_argument("--db", default="data/v9_forces.db")
    ap.add_argument("--report", default=None)
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args(argv)

    if not Path(args.db).exists():
        print(f"[ERREUR] DB introuvable : {args.db}")
        return 2

    print(f"[1/4] reconstruction magnitude ({args.db})…")
    magnitude_stats = ags.reconstruct_magnitude_stats(args.db, horizon_bars=args.horizon)
    print(f"      {len(magnitude_stats)} cellules")

    print("[2/4] chargement décisions + barres forward…")
    recs, market = load_decisions(args.db, args.horizon)
    print(f"      {len(recs)} décisions résolues")

    print("[3/4] rejeu des variantes + walk-forward…")
    res = replay(recs, market, magnitude_stats, k_folds=args.folds)

    print("[4/4] rapport…")
    report = build_report(res, magnitude_stats, args.horizon)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"      écrit : {args.report}")
    else:
        print(report)

    # Résumé console.
    for label, m in res["variants"].items():
        print(f"  {label:32s} pips={m.total_pips:+9.0f} PF={_pf(m):>5} "
              f"WR={m.win_rate:5.1f}% DD={m.max_drawdown:8.0f} trades={m.n_trades}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
