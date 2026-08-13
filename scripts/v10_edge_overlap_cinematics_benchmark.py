"""V10 Edge OVERLAP + Cinématique — benchmark du filtre cinématique.

Mesure l'impact du filtre cinématique (divergence + exhaustion) sur l'edge
OVERLAP : combien de signaux sont bloqués, et le WR/PnL AVEC vs SANS filtre.

Méthode : replay point_in_time strict (mêmes barres que le replay officiel,
config optimisée delta≥25, TP=2xATR, SL=1xATR, hold 4). Pour chaque signal,
on calcule la cinématique de la force sur les 60 dernières barres M15 et on
applique le verdict (BLOCK si divergence/exhaustion contre la direction).

R9 : chaque chiffre = 1 query SQL. R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v10.v10_cinematics import analyze_series, cinematics_verdict  # noqa: E402
from scripts.v10_edge_overlap_benchmark import (  # noqa: E402
    _load_bars, _signal_index, _resolve,
)

DB = ROOT / "data" / "v9_forces.db"
PAIRS = ("EURUSD", "USDCHF", "AUDUSD")
TF = "M15"
SPREAD_PIP = 0.3
TP_RATIO, SL_RATIO, HOLD_MAX = 2.0, 1.0, 4
DELTA_MIN = 25.0


def _force_series(bars, pair, up_to):
    """Série de delta_forces + prix jusqu'à l'index up_to (inclus)."""
    base, quote = pair[:3], pair[3:6]
    forces, prices = [], []
    for j in range(max(0, up_to - 60), up_to + 1):
        b = bars[j]
        forces.append(float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0)))
        prices.append(float(b["close"]))
    return forces, prices


def main():
    print(f"[{dt.datetime.now(dt.UTC).isoformat()}] EDGE OVERLAP + CINÉMATIQUE — benchmark")
    print(f"Config: delta≥{DELTA_MIN} TP={TP_RATIO}x SL={SL_RATIO}x hold={HOLD_MAX}")
    print("=" * 100)

    bars_by_pair = {p: _load_bars(p, 1500) for p in PAIRS}

    # Signaux avec/sans filtre cinématique
    all_trades_raw = []   # sans filtre (baseline)
    all_trades_filt = []  # avec filtre
    blocked_count = 0
    blocked_reasons = {}

    for pair in PAIRS:
        bars = bars_by_pair[pair]
        for i in range(60, len(bars) - HOLD_MAX - 1):
            sig = _signal_index(pair, bars, i, DELTA_MIN)
            if sig is None:
                continue
            res = _resolve(sig, bars, TP_RATIO, SL_RATIO, HOLD_MAX)
            trade = {"pair": pair, "direction": sig["direction"],
                     "bar_time": sig["bar_time"], "delta": sig["delta"],
                     "atr_pip": sig["atr_pip"], "pnl_pips": res["pnl_pips"],
                     "reason": res["reason"]}
            all_trades_raw.append(trade)

            # Cinématique sur les 60 barres M15 précédant le signal
            forces, prices = _force_series(bars, pair, i)
            pip = 0.01 if pair.endswith("JPY") else 0.0001
            ana = analyze_series(forces, prices, label=f"{pair} M15", pip_size=pip)
            verdict = cinematics_verdict(ana, sig["direction"])
            if verdict["action"] == "BLOCK":
                blocked_count += 1
                for r in verdict["reasons"]:
                    blocked_reasons[r.split(" : ")[0]] = blocked_reasons.get(r.split(" : ")[0], 0) + 1
            else:
                all_trades_filt.append(trade)

    def stats(trades):
        if not trades:
            return {"n": 0}
        pnls = [t["pnl_pips"] for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        sharpe = (sum(pnls) / len(pnls)) / (__import__("statistics").stdev(pnls) or 1e-9) * math.sqrt(252) if len(pnls) > 1 else 0
        return {"n": len(trades), "wr": round(wins / len(trades), 4),
                "pnl_pips": round(sum(pnls), 2), "sharpe": round(sharpe, 3)}

    raw = stats(all_trades_raw)
    filt = stats(all_trades_filt)

    print(f"\n{'':>14} {'n':>5} {'WR':>7} {'PnL':>9} {'Sharpe':>8}")
    print("-" * 100)
    print(f"{'SANS filtre':>14} {raw['n']:>5} {raw['wr']:>7.4f} {raw['pnl_pips']:>9.2f} {raw['sharpe']:>8.3f}")
    print(f"{'AVEC filtre':>14} {filt['n']:>5} {filt['wr']:>7.4f} {filt['pnl_pips']:>9.2f} {filt['sharpe']:>8.3f}")
    print(f"\nSignaux bloqués : {blocked_count} ({blocked_count/max(len(all_trades_raw),1):.1%})")
    print("Raisons de blocage :")
    for r, c in sorted(blocked_reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {r}: {c}")

    out = ROOT / "reports" / f"v10_edge_overlap_cinematics_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps({
        "ts": dt.datetime.now(dt.UTC).isoformat(),
        "config": {"delta_min": DELTA_MIN, "tp_ratio": TP_RATIO, "sl_ratio": SL_RATIO,
                   "hold": HOLD_MAX, "spread_pip": SPREAD_PIP},
        "sans_filtre": raw, "avec_filtre": filt,
        "blocked": {"n": blocked_count, "by_reason": blocked_reasons},
        "audit": {"r9": "point_in_time strict, mêmes barres que replay officiel",
                  "r10": "compute only, zero order real"},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport: {out}")


if __name__ == "__main__":
    main()