"""V10 Edge OVERLAP Benchmark — grid search (delta_min × TP/SL ratio) pour Sharpe.

L'edge OVERLAP (12-16 UTC + |delta_forces|≥15) est prouvé (WR 58-67%) mais
échoue le gate Sharpe (0.17-0.32 vs 0.5 requis). Cause : payoff symétrique
(TP=SL=1xATR) + bucket delta 20-25 perdant (WR 46%, PnL négatif).

Ce script rejoue l'historique avec des combinaisons (delta_min, tp_ratio,
sl_ratio, hold_max) et mesure WR / PnL / Sharpe / DD pour chaque config.
Objectif : trouver la config qui maximise le Sharpe SANS casser WR ≥ 54%.

Méthode : point_in_time strict (signal à la barre i, résolution i+1..i+hold),
mêmes barres que le replay officiel. R9 : chaque chiffre = 1 query SQL.

R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.v10_shadow_edge_overlap import _load_bars, _delta_forces  # noqa: E402

DB = ROOT / "data" / "v9_forces.db"
PAIRS = ("EURUSD", "USDCHF", "AUDUSD")
TF = "M15"
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")
SPREAD_PIP = 0.3

# Grid
DELTA_GRID = [15.0, 20.0, 25.0, 30.0]
TP_RATIO_GRID = [1.0, 1.5, 2.0]
SL_RATIO_GRID = [0.75, 1.0]
HOLD_GRID = [4, 6]


def _sharpe(pnls: list) -> float:
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return mean / sd * math.sqrt(252)  # annualisé proxy


def _max_dd(pnls: list) -> float:
    peak = cum = 0.0
    dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


def _resolve(signal, bars, tp_ratio, sl_ratio, hold_max):
    """Résout un trade avec TP/SL paramétrables (ratio × ATR)."""
    atr_pip = signal["atr_pip"]
    if atr_pip <= 0:
        return {"pnl_pips": 0.0, "reason": "atr_zero"}
    pair = signal["pair"]
    entry = signal["entry"]
    m = 1 if signal["direction"] == "BUY" else -1
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    tp, sl = atr_pip * tp_ratio, atr_pip * sl_ratio
    i = signal.get("index", len(bars) - 1)
    for j in range(i + 1, min(i + 1 + hold_max, len(bars))):
        hi, lo = bars[j]["high"], bars[j]["low"]
        if m == 1:
            if hi >= entry + tp * pip:
                return {"pnl_pips": round(tp - SPREAD_PIP, 2), "reason": "TP"}
            if lo <= entry - sl * pip:
                return {"pnl_pips": round(-sl - SPREAD_PIP, 2), "reason": "SL"}
        else:
            if lo <= entry - tp * pip:
                return {"pnl_pips": round(tp - SPREAD_PIP, 2), "reason": "TP"}
            if hi >= entry + sl * pip:
                return {"pnl_pips": round(-sl - SPREAD_PIP, 2), "reason": "SL"}
    exit_price = bars[min(i + hold_max, len(bars) - 1)]["close"]
    pnl = (exit_price - entry) * m / pip - SPREAD_PIP
    return {"pnl_pips": round(pnl, 2), "reason": "TIMEOUT"}


def _signal_index(pair, bars, i, delta_min):
    """Règle OVERLAP sur la barre i (point_in_time)."""
    if i < 60:
        return None
    cur = bars[i]
    hour = dt.datetime.fromtimestamp(int(cur["bar_time"]), tz=dt.UTC).hour
    if not (12 <= hour < 16):
        return None
    d = _delta_forces(cur, pair)
    if abs(d) < delta_min:
        return None
    entry = cur["close"]
    atr = sum(bars[j]["high"] - bars[j]["low"] for j in range(i - 15, i - 1)) / 14
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    return {
        "pair": pair, "direction": "BUY" if d > 0 else "SELL",
        "entry": entry, "atr_pip": round(atr / pip if pip else 0, 2),
        "delta": round(d, 2), "bar_time": int(cur["bar_time"]), "index": i,
    }


def _replay_config(pair, bars, delta_min, tp_ratio, sl_ratio, hold_max):
    """Rejoue une config sur une paire. Retourne liste de trades."""
    trades = []
    for i in range(60, len(bars) - hold_max - 1):
        sig = _signal_index(pair, bars, i, delta_min)
        if sig is None:
            continue
        res = _resolve(sig, bars, tp_ratio, sl_ratio, hold_max)
        trades.append({"pair": pair, "direction": sig["direction"],
                       "bar_time": sig["bar_time"], "delta": sig["delta"],
                       "atr_pip": sig["atr_pip"], "pnl_pips": res["pnl_pips"],
                       "reason": res["reason"]})
    return trades


def main():
    print(f"[{dt.datetime.now(dt.UTC).isoformat()}] EDGE OVERLAP — BENCHMARK grid")
    print(f"Grid: delta={DELTA_GRID} tp_ratio={TP_RATIO_GRID} sl_ratio={SL_RATIO_GRID} hold={HOLD_GRID}")
    print("=" * 100)

    # Charger les barres une fois par paire (1500 barres ≈ 15 jours M15)
    bars_by_pair = {p: _load_bars(p, 1500) for p in PAIRS}
    print(f"Barres chargées: { {p: len(b) for p, b in bars_by_pair.items()} }")

    results = []
    for delta_min, tp_ratio, sl_ratio, hold_max in itertools.product(
            DELTA_GRID, TP_RATIO_GRID, SL_RATIO_GRID, HOLD_GRID):
        all_trades = []
        for pair in PAIRS:
            all_trades += _replay_config(pair, bars_by_pair[pair], delta_min,
                                         tp_ratio, sl_ratio, hold_max)
        n = len(all_trades)
        if n < 30:
            continue
        pnls = [t["pnl_pips"] for t in all_trades]
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n
        pnl = sum(pnls)
        sharpe = _sharpe(pnls)
        dd = _max_dd(pnls)
        results.append({
            "delta_min": delta_min, "tp_ratio": tp_ratio, "sl_ratio": sl_ratio,
            "hold_max": hold_max, "n": n, "wr": round(wr, 4),
            "pnl_pips": round(pnl, 2), "sharpe": round(sharpe, 3),
            "max_dd_pips": round(dd, 2),
        })

    # Tri par Sharpe décroissant
    results.sort(key=lambda r: -r["sharpe"])

    print(f"\n{'delta':>6} {'tp':>4} {'sl':>4} {'hold':>5} {'n':>5} {'WR':>7} {'PnL':>8} {'Sharpe':>8} {'DD':>7}")
    print("-" * 100)
    for r in results[:25]:
        print(f"{r['delta_min']:>6.0f} {r['tp_ratio']:>4.1f} {r['sl_ratio']:>4.2f} "
              f"{r['hold_max']:>5d} {r['n']:>5d} {r['wr']:>7.4f} {r['pnl_pips']:>8.2f} "
              f"{r['sharpe']:>8.3f} {r['max_dd_pips']:>7.2f}")

    # Configs qui passent la gate (WR≥54% ET Sharpe≥0.5)
    print("\n=== CONFIGS GATE-PASS (WR≥54% ET Sharpe≥0.5) ===")
    gate_pass = [r for r in results if r["wr"] >= 0.54 and r["sharpe"] >= 0.5]
    if gate_pass:
        for r in gate_pass[:10]:
            print(f"  delta≥{r['delta_min']:.0f} TP={r['tp_ratio']}x SL={r['sl_ratio']}x "
                  f"hold={r['hold_max']} → n={r['n']} WR={r['wr']:.4f} PnL={r['pnl_pips']:.2f} "
                  f"Sharpe={r['sharpe']:.3f} DD={r['max_dd_pips']:.2f}")
    else:
        print("  AUCUNE config ne passe la gate complète. Meilleures approches :")
        for r in results[:5]:
            print(f"  delta≥{r['delta_min']:.0f} TP={r['tp_ratio']}x SL={r['sl_ratio']}x "
                  f"hold={r['hold_max']} → n={r['n']} WR={r['wr']:.4f} PnL={r['pnl_pips']:.2f} "
                  f"Sharpe={r['sharpe']:.3f}")

    # Persist
    out = ROOT / "reports" / f"v10_edge_overlap_benchmark_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps({
        "ts": dt.datetime.now(dt.UTC).isoformat(),
        "grid": {"delta": DELTA_GRID, "tp_ratio": TP_RATIO_GRID,
                 "sl_ratio": SL_RATIO_GRID, "hold": HOLD_GRID},
        "results": results,
        "gate_pass": gate_pass[:10],
        "audit": {"r9": "point_in_time strict, mêmes barres que replay officiel",
                  "r10": "compute only, zero order real"},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport: {out}")


if __name__ == "__main__":
    main()