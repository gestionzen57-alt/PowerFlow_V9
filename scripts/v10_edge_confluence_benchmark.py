"""V10 Edge OVERLAP + Confluence TF — benchmark sizing modulé (3 jours).

Compare la lecture M15 seule (actuelle) vs la lecture imbriquée avec score
de confluence (M5+M15+M30+H1) qui module le SIZING au lieu de bloquer.

Méthode : replay point_in_time strict des 3 jours (11, 12, 13/08), même
config (delta≥25, SL=1x, hold=4, spread 0.3p). Pour chaque signal M15 :
  - M15 seul : PnL × 1.0 (baseline)
  - Confluence : PnL × sizing_multiplier (0.5 → 1.0 selon score 0-4)

Le sizing modulé simule un lot réduit quand la confluence est faible
(conflit H1 = -1, pas de blocage). R9 : point_in_time strict.
R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.v10.v10_confluence_tf import confluence_score, load_tf_bars  # noqa: E402
from scripts.v10_shadow_edge_overlap import _load_bars, _delta_forces  # noqa: E402

DB = ROOT / "data" / "v9_forces.db"
PAIRS = ("EURUSD", "USDCHF", "AUDUSD")
DELTA_MIN = 25.0
SL_RATIO = 1.0
HOLD_MAX = 4
SPREAD_PIP = 0.3
DAYS = ("2026-08-11", "2026-08-12", "2026-08-13")


def _day_epoch(day: str) -> int:
    return int(dt.datetime(int(day[:4]), int(day[5:7]), int(day[8:10]),
                           tzinfo=dt.UTC).timestamp())


def _resolve_tp(sig, bars, tp_ratio):
    atr_pip = sig["atr_pip"]
    if atr_pip <= 0:
        return {"pnl_pips": 0.0, "reason": "atr_zero"}
    pair = sig["pair"]
    entry = sig["entry"]
    m = 1 if sig["direction"] == "BUY" else -1
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    tp, sl = atr_pip * tp_ratio, atr_pip * SL_RATIO
    i = sig["index"]
    for j in range(i + 1, min(i + 1 + HOLD_MAX, len(bars))):
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
    exit_price = bars[min(i + HOLD_MAX, len(bars) - 1)]["close"]
    pnl = (exit_price - entry) * m / pip - SPREAD_PIP
    return {"pnl_pips": round(pnl, 2), "reason": "TIMEOUT"}


def main():
    print(f"[{dt.datetime.now(dt.UTC).isoformat()}] EDGE OVERLAP + CONFLUENCE TF — benchmark 3 jours")
    print(f"Config: delta≥{DELTA_MIN} SL={SL_RATIO}x hold={HOLD_MAX} spread={SPREAD_PIP}p")
    print("=" * 100)

    bars_m15 = {p: _load_bars(p, 2000) for p in PAIRS}
    bars_m5 = {p: load_tf_bars(str(DB), p, "M5", 4000) for p in PAIRS}
    bars_m30 = {p: load_tf_bars(str(DB), p, "M30", 2000) for p in PAIRS}
    bars_h1 = {p: load_tf_bars(str(DB), p, "H1", 2000) for p in PAIRS}

    all_trades = []
    summary = {}

    for day in DAYS:
        day_epoch = _day_epoch(day)
        day_end = day_epoch + 86400
        day_trades = []
        for pair in PAIRS:
            bars = bars_m15[pair]
            for i in range(60, len(bars) - HOLD_MAX - 1):
                bt = int(bars[i]["bar_time"])
                if not (day_epoch <= bt < day_end):
                    continue
                hour = dt.datetime.fromtimestamp(bt, tz=dt.UTC).hour
                if not (12 <= hour < 16):
                    continue
                d = _delta_forces(bars[i], pair)
                if abs(d) < DELTA_MIN:
                    continue
                entry = float(bars[i]["close"])
                atr = sum(bars[j]["high"] - bars[j]["low"] for j in range(i - 15, i - 1)) / 14
                pip = 0.01 if pair.endswith("JPY") else 0.0001
                atr_pip = atr / pip if pip else 0
                sig = {"pair": pair, "direction": "BUY" if d > 0 else "SELL",
                       "entry": entry, "atr_pip": atr_pip, "index": i}
                r1 = _resolve_tp(sig, bars, 1.0)
                r2 = _resolve_tp(sig, bars, 2.0)

                # Score de confluence (sizing modulé)
                conf = confluence_score(
                    str(DB), pair, bt, sig["direction"],
                    bars_m15=bars, bars_m5=bars_m5[pair],
                    bars_m30=bars_m30[pair], bars_h1=bars_h1[pair],
                )
                mult = conf["sizing_multiplier"]

                trade = {
                    "day": day, "pair": pair, "direction": sig["direction"],
                    "delta": round(d, 2), "atr_pip": round(atr_pip, 2),
                    "bar_time": bt, "confluence": conf,
                    "tp1x": r1, "tp2x": r2,
                    "pnl1x_plein": r1["pnl_pips"], "pnl2x_plein": r2["pnl_pips"],
                    "pnl1x_module": round(r1["pnl_pips"] * mult, 2),
                    "pnl2x_module": round(r2["pnl_pips"] * mult, 2),
                }
                day_trades.append(trade)
                all_trades.append(trade)

        # Stats du jour
        for tp_key, pnl_key in (("tp1x", "pnl1x"), ("tp2x", "pnl2x")):
            plein = [t[f"{pnl_key}_plein"] for t in day_trades]
            module = [t[f"{pnl_key}_module"] for t in day_trades]
            for pop_key, pnls in (("plein", plein), ("module", module)):
                n = len(pnls)
                if n:
                    wins = sum(1 for p in pnls if p > 0)
                    mean = sum(pnls) / n
                    sd = math.sqrt(sum((p - mean) ** 2 for p in pnls) / (n - 1)) if n > 1 else 0
                    sharpe = mean / sd * math.sqrt(252) if sd else 0
                    summary.setdefault(day, {}).setdefault(tp_key, {})[pop_key] = {
                        "n": n, "wr": round(wins / n, 4), "pnl": round(sum(pnls), 2),
                        "sharpe": round(sharpe, 3),
                    }

    # Affichage
    print(f"\n{'Jour':>12} {'TP':>4} {'pop':>8} {'n':>4} {'WR':>7} {'PnL':>9} {'Sharpe':>8}")
    print("-" * 70)
    for day in DAYS:
        for tp_key in ("tp1x", "tp2x"):
            pops = summary.get(day, {}).get(tp_key, {})
            for pop_key, label in (("plein", "plein"), ("module", "module")):
                s = pops.get(pop_key)
                if s:
                    print(f"{day:>12} {tp_key[2:]:>4} {label:>8} {s['n']:>4} {s['wr']:>7.4f} {s['pnl']:>9.2f} {s['sharpe']:>8.3f}")

    # Distribution des scores de confluence
    print("\n=== DISTRIBUTION SCORE CONFLUENCE (3 jours cumulés) ===")
    from collections import Counter
    scores = Counter(t["confluence"]["score"] for t in all_trades)
    for s in range(5):
        print(f"  score {s}: {scores.get(s, 0)} signaux")

    # Détail des conflits H1 (le plus informatif)
    print("\n=== CONFLITS H1 (sizing réduit, pas bloqué) ===")
    for t in all_trades:
        c = t["confluence"]
        if not c["components"]["h1"] and c["score"] >= 2:
            print(f"  [{t['day']}] {t['pair']} {t['direction']} delta={t['delta']:+.1f} "
                  f"score={c['score']}/4 mult={c['sizing_multiplier']} "
                  f"H1={c['detail']['d_h1']} M30={c['detail']['d_m30']} "
                  f"→ TP1x {t['pnl1x_plein']:+.2f}p (module {t['pnl1x_module']:+.2f}p)")

    out = ROOT / "reports" / f"v10_edge_confluence_benchmark_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps({
        "ts": dt.datetime.now(dt.UTC).isoformat(),
        "config": {"delta_min": DELTA_MIN, "sl_ratio": SL_RATIO, "hold": HOLD_MAX,
                   "spread_pip": SPREAD_PIP},
        "summary": summary, "trades": all_trades,
        "audit": {"r9": "point_in_time strict, sizing modulé par confluence",
                  "r10": "compute only, zero order real"},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport: {out}")


if __name__ == "__main__":
    main()