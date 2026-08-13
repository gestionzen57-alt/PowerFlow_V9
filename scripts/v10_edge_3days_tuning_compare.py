"""V10 Edge 3 jours — comparaison tuning TP (1x vs 2x) avec cinématique.

Objectif (Søn) : comprendre si le "drift" du 13/08 est réel ou un artefact de
config, et quel TP (1xATR vs 2xATR) est le meilleur — avec la lecture
cinématique pour voir la logique de chaque trade.

Méthode : replay point_in_time strict des 3 jours (11, 12, 13/08) avec la
MÊME config pour tous : delta≥25, SL=1xATR, hold=4, spread 0.3p, filtre
cinématique ON. Chaque signal ALLOW est résolu avec TP=1x ET TP=2x
(2 résolutions indépendantes sur les mêmes barres).

Pour chaque trade : signal (delta, direction), cinématique (verdict + raisons
+ valeurs : pic, retombée, pente), résolution (TP/SL/timeout), PnL ×2.

R9 : point_in_time strict, mêmes barres que le replay officiel.
R10 : compute only, zéro ordre réel.
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
from scripts.v10_shadow_edge_overlap import _load_bars, _delta_forces  # noqa: E402

DB = ROOT / "data" / "v9_forces.db"
PAIRS = ("EURUSD", "USDCHF", "AUDUSD")
TF = "M15"
DELTA_MIN = 25.0
SL_RATIO = 1.0
HOLD_MAX = 4
SPREAD_PIP = 0.3
DAYS = ("2026-08-11", "2026-08-12", "2026-08-13")


def _day_epoch(day: str) -> int:
    return int(dt.datetime(int(day[:4]), int(day[5:7]), int(day[8:10]),
                           tzinfo=dt.UTC).timestamp())


def _resolve_tp(sig, bars, tp_ratio):
    """Résout un trade avec TP paramétrable (ratio × ATR), SL=1xATR, hold=4."""
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


def _cinematics_detail(bars, pair, i, block_momentum_dead=True):
    """Analyse cinématique complète (verdict + valeurs) pour la barre i."""
    base, quote = pair[:3], pair[3:6]
    forces, prices = [], []
    for j in range(max(0, i - 60), i + 1):
        b = bars[j]
        forces.append(float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0)))
        prices.append(float(b["close"]))
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    ana = analyze_series(forces, prices, label=f"{pair} M15", pip_size=pip)
    d = _delta_forces(bars[i], pair)
    verdict = cinematics_verdict(ana, "BUY" if d > 0 else "SELL",
                                 block_momentum_dead=block_momentum_dead)
    return {
        "action": verdict["action"],
        "reasons": verdict["reasons"],
        "pic": ana.get("force_pic"),
        "pic_bars_ago": ana.get("pic_bars_ago"),
        "last_force": ana.get("last_force"),
        "slope_force_5": ana.get("slope_force_5"),
        "acceleration": ana.get("acceleration_force"),
        "divergence": ana.get("divergence_force_price"),
        "exhaustion": ana.get("exhaustion_pic"),
    }


def main():
    print(f"[{dt.datetime.now(dt.UTC).isoformat()}] EDGE 3 JOURS — tuning TP 1x vs 2x, cinématique ON")
    print(f"Config: delta≥{DELTA_MIN} SL={SL_RATIO}x hold={HOLD_MAX} spread={SPREAD_PIP}p")
    print("=" * 120)

    bars_by_pair = {p: _load_bars(p, 2000) for p in PAIRS}
    all_trades = []
    summary = {}

    for day in DAYS:
        day_epoch = _day_epoch(day)
        day_end = day_epoch + 86400
        day_trades = []
        for pair in PAIRS:
            bars = bars_by_pair[pair]
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
                # Cinématique — 2 verdicts : avant (sans momentum dead) / après
                cine_avant = _cinematics_detail(bars, pair, i, block_momentum_dead=False)
                cine_apres = _cinematics_detail(bars, pair, i, block_momentum_dead=True)
                entry = float(bars[i]["close"])
                atr = sum(bars[j]["high"] - bars[j]["low"] for j in range(i - 15, i - 1)) / 14
                pip = 0.01 if pair.endswith("JPY") else 0.0001
                atr_pip = atr / pip if pip else 0
                sig = {"pair": pair, "direction": "BUY" if d > 0 else "SELL",
                       "entry": entry, "atr_pip": atr_pip, "index": i}
                r1 = _resolve_tp(sig, bars, 1.0)
                r2 = _resolve_tp(sig, bars, 2.0)
                trade = {
                    "day": day, "pair": pair, "direction": sig["direction"],
                    "delta": round(d, 2), "atr_pip": round(atr_pip, 2),
                    "bar_time": bt, "cinematics": cine_apres,
                    "cinematics_avant": cine_avant,
                    "tp1x": r1, "tp2x": r2,
                }
                day_trades.append(trade)
                all_trades.append(trade)

        # Stats du jour — 3 populations : tous / ALLOW avant / ALLOW après
        for tp_key, tp_ratio in (("tp1x", 1.0), ("tp2x", 2.0)):
            for pop_key, pop_filter in (
                ("tous", lambda t: True),
                ("allow_avant", lambda t: t["cinematics_avant"]["action"] == "ALLOW"),
                ("allow_apres", lambda t: t["cinematics"]["action"] == "ALLOW"),
            ):
                pop = [t for t in day_trades if pop_filter(t)]
                pnls = [t[tp_key]["pnl_pips"] for t in pop]
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

    # Affichage tableau — avant/après momentum dead
    print(f"\n{'Jour':>12} {'TP':>4} {'pop':>11} {'n':>4} {'WR':>7} {'PnL':>9} {'Sharpe':>8}")
    print("-" * 75)
    for day in DAYS:
        for tp_key in ("tp1x", "tp2x"):
            pops = summary.get(day, {}).get(tp_key, {})
            for pop_key, label in (("tous", "tous"), ("allow_avant", "ALLOW avant"),
                                   ("allow_apres", "ALLOW après")):
                s = pops.get(pop_key)
                if s:
                    print(f"{day:>12} {tp_key[2:]:>4} {label:>11} {s['n']:>4} {s['wr']:>7.4f} {s['pnl']:>9.2f} {s['sharpe']:>8.3f}")
                else:
                    print(f"{day:>12} {tp_key[2:]:>4} {label:>11}  —  aucun")

    # Logique détaillée : tous les trades avec cinématique
    print("\n" + "=" * 120)
    print("LOGIC DÉTAILLÉE — chaque signal (delta≥25, OVERLAP) avec verdict cinématique")
    print("=" * 120)
    for t in all_trades:
        c = t["cinematics"]
        verdict = "✅ ALLOW" if c["action"] == "ALLOW" else "❌ BLOCK"
        reasons = "; ".join(c["reasons"]) if c["reasons"] else "extension saine"
        r1, r2 = t["tp1x"], t["tp2x"]
        print(f"\n[{t['day']}] {t['pair']} {t['direction']} delta={t['delta']:+.1f} ATR={t['atr_pip']}p")
        print(f"  Cinématique: {verdict} | pic={c['pic']} (il y a {c['pic_bars_ago']}b) → now={c['last_force']} "
              f"| pente={c['slope_force_5']} accel={c['acceleration']} | div={c['divergence']} exh={c['exhaustion']}")
        if c["reasons"]:
            print(f"    → {reasons}")
        print(f"  Résolution: TP1x → {r1['reason']} {r1['pnl_pips']:+.2f}p | TP2x → {r2['reason']} {r2['pnl_pips']:+.2f}p")

    # Persist
    out = ROOT / "reports" / f"v10_edge_3days_tuning_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps({
        "ts": dt.datetime.now(dt.UTC).isoformat(),
        "config": {"delta_min": DELTA_MIN, "sl_ratio": SL_RATIO, "hold": HOLD_MAX,
                   "spread_pip": SPREAD_PIP, "cinematics": True},
        "summary": summary, "trades": all_trades,
        "audit": {"r9": "point_in_time strict, config identique 3 jours",
                  "r10": "compute only, zero order real"},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport: {out}")


if __name__ == "__main__":
    main()