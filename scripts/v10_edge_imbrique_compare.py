"""V10 Edge OVERLAP — lecture IMBRIQUÉE M5+M15 → anticipation M30/H1.

Søn : "pourquoi il lit pas le 5, 15, 30 pour le 5 et le 15 pour une
anticipation du 30 et h1 ? car les confirmations de croisement sont
retardées, les zones doivent être lues correctement avec imbrication."

Principe (Pilier 2 — imbrication temporelle) :
  - M5  : cinématique rapide (pics/creux/divergence précoces) — l'ANTICIPATION
  - M15 : le TF de décision actuel (delta_forces ≥ 25)
  - M30 : la confirmation (le mouvement M15 doit être aligné avec M30)
  - H1  : le juge (la direction H1 donne le biais, M15 le timing)

Lecture imbriquée pour chaque signal M15 :
  1. M5  : cinématique rapide (pente, accélération, exhaustion précoce)
  2. M15 : delta_forces + cinématique (comme aujourd'hui)
  3. M30 : delta_forces aligné ? (même direction que M15)
  4. H1  : delta_forces aligné ? (biais directionnel)

Verdict : ALLOW si M15 signal ET alignement M30/H1 (confluence), sinon
BLOCK avec la raison (conflit de TF). L'anticipation M5 est un signal
d'alerte (pas un blocage).

Rejoue sur une journée donnée (--day) pour comparer avec la lecture M15
seule. R9 : point_in_time strict. R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations

import argparse
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
DELTA_MIN = 25.0
SL_RATIO = 1.0
HOLD_MAX = 4
SPREAD_PIP = 0.3


def _load_tf_bars(pair, tf, limit=2000):
    """Barres d'un TF donné (chronologique ascendant)."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, force_eur, force_usd, force_gbp, "
        "force_jpy, force_cad, force_chf, force_aud, force_nzd "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (pair, tf, limit),
    ).fetchall()
    con.close()
    return [dict(r) for r in reversed(rows)]


def _delta_at(b, pair):
    base, quote = pair[:3], pair[3:6]
    return float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0))


def _tf_delta_at_time(bars_tf, pair, ts):
    """Delta forces du TF au moment ts (dernière barre fermée ≤ ts)."""
    best = None
    for b in bars_tf:
        if int(b["bar_time"]) <= ts:
            best = b
        else:
            break
    return _delta_at(best, pair) if best else None


def _cinematics_detail(bars, pair, i):
    """Cinématique M15 (verdict + valeurs) pour la barre i."""
    base, quote = pair[:3], pair[3:6]
    forces, prices = [], []
    for j in range(max(0, i - 60), i + 1):
        b = bars[j]
        forces.append(float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0)))
        prices.append(float(b["close"]))
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    ana = analyze_series(forces, prices, label=f"{pair} M15", pip_size=pip)
    d = _delta_forces(bars[i], pair)
    verdict = cinematics_verdict(ana, "BUY" if d > 0 else "SELL")
    return {
        "action": verdict["action"], "reasons": verdict["reasons"],
        "pic": ana.get("force_pic"), "pic_bars_ago": ana.get("pic_bars_ago"),
        "last_force": ana.get("last_force"), "slope_force_5": ana.get("slope_force_5"),
        "acceleration": ana.get("acceleration_force"),
        "divergence": ana.get("divergence_force_price"), "exhaustion": ana.get("exhaustion_pic"),
    }


def _m5_anticipation(bars_m5, pair, ts):
    """Cinématique M5 (anticipation) au moment ts — pente/accélération rapides."""
    base, quote = pair[:3], pair[3:6]
    forces, prices = [], []
    for b in bars_m5:
        if int(b["bar_time"]) <= ts:
            forces.append(_delta_at(b, pair))
            prices.append(float(b["close"]))
    if len(forces) < 10:
        return {"available": False}
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    ana = analyze_series(forces, prices, label=f"{pair} M5", pip_size=pip)
    return {
        "available": True,
        "slope_force_5": ana.get("slope_force_5"),
        "acceleration": ana.get("acceleration_force"),
        "exhaustion": ana.get("exhaustion_pic"),
        "divergence": ana.get("divergence_force_price"),
        "last_force": ana.get("last_force"),
    }


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-08-12", help="Jour à rejouer (YYYY-MM-DD)")
    args = ap.parse_args()
    day = args.day
    day_epoch = int(dt.datetime(int(day[:4]), int(day[5:7]), int(day[8:10]),
                                tzinfo=dt.UTC).timestamp())
    day_end = day_epoch + 86400

    print(f"[{dt.datetime.now(dt.UTC).isoformat()}] EDGE OVERLAP — lecture IMBRIQUÉE M5+M15→M30/H1 sur {day}")
    print(f"Config: delta≥{DELTA_MIN} SL={SL_RATIO}x hold={HOLD_MAX} spread={SPREAD_PIP}p")
    print("=" * 130)

    bars_m15 = {p: _load_tf_bars(p, "M15", 2000) for p in PAIRS}
    bars_m5 = {p: _load_tf_bars(p, "M5", 4000) for p in PAIRS}
    bars_m30 = {p: _load_tf_bars(p, "M30", 2000) for p in PAIRS}
    bars_h1 = {p: _load_tf_bars(p, "H1", 2000) for p in PAIRS}

    all_trades = []
    stats = {"m15_seul": [], "imbrique": []}

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

            # Cinématique M15
            cine = _cinematics_detail(bars, pair, i)
            # Anticipation M5
            m5 = _m5_anticipation(bars_m5[pair], pair, bt)
            # Alignement M30 / H1
            d_m30 = _tf_delta_at_time(bars_m30[pair], pair, bt)
            d_h1 = _tf_delta_at_time(bars_h1[pair], pair, bt)
            align_m30 = (d_m30 is not None) and (d_m30 * d > 0)
            align_h1 = (d_h1 is not None) and (d_h1 * d > 0)

            # Verdict M15 seul (comme aujourd'hui)
            m15_allow = cine["action"] == "ALLOW"

            # Verdict imbriqué : M15 ALLOW ET alignement M30/H1 (confluence)
            imbrique_allow = m15_allow and align_m30 and align_h1
            if not m15_allow:
                imbrique_reason = "cinematics_block"
            elif not align_m30:
                imbrique_reason = "conflit_M30"
            elif not align_h1:
                imbrique_reason = "conflit_H1"
            else:
                imbrique_reason = "confluence_OK"

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
                "bar_time": bt, "cinematics": cine,
                "m5_anticipation": m5,
                "align_m30": align_m30, "d_m30": round(d_m30, 2) if d_m30 else None,
                "align_h1": align_h1, "d_h1": round(d_h1, 2) if d_h1 else None,
                "m15_allow": m15_allow, "imbrique_allow": imbrique_allow,
                "imbrique_reason": imbrique_reason,
                "tp1x": r1, "tp2x": r2,
            }
            all_trades.append(trade)
            if m15_allow:
                stats["m15_seul"].append(trade)
            if imbrique_allow:
                stats["imbrique"].append(trade)

    def show(label, trades, tp_key):
        pnls = [t[tp_key]["pnl_pips"] for t in trades]
        n = len(pnls)
        if not n:
            print(f"{label:>12} {tp_key[2:]:>4}  —  aucun")
            return
        wins = sum(1 for p in pnls if p > 0)
        mean = sum(pnls) / n
        sd = math.sqrt(sum((p - mean) ** 2 for p in pnls) / (n - 1)) if n > 1 else 0
        sharpe = mean / sd * math.sqrt(252) if sd else 0
        print(f"{label:>12} {tp_key[2:]:>4} n={n:>3} WR={wins/n:.4f} PnL={sum(pnls):+8.2f} Sharpe={sharpe:6.3f}")

    print(f"\n{'Population':>12} {'TP':>4} {'n':>4} {'WR':>8} {'PnL':>10} {'Sharpe':>8}")
    print("-" * 60)
    for tp_key in ("tp1x", "tp2x"):
        show("M15 seul", stats["m15_seul"], tp_key)
        show("IMBRIQUÉ", stats["imbrique"], tp_key)

    # Détail des conflits
    print("\n" + "=" * 130)
    print("LOGIC IMBRIQUÉE — chaque signal M15 avec alignement M30/H1 + anticipation M5")
    print("=" * 130)
    for t in all_trades:
        c = t["cinematics"]
        m5 = t["m5_anticipation"]
        verdict = "✅" if t["imbrique_allow"] else "❌"
        m5s = f"M5 pente={m5.get('slope_force_5')} accel={m5.get('acceleration')} exh={m5.get('exhaustion')}" if m5.get("available") else "M5 n/a"
        print(f"\n[{t['day']}] {t['pair']} {t['direction']} delta={t['delta']:+.1f} | {verdict} {t['imbrique_reason']}")
        print(f"  M15: {c['action']} | pic={c['pic']}→{c['last_force']} pente={c['slope_force_5']} accel={c['acceleration']}")
        print(f"  {m5s}")
        print(f"  M30: delta={t['d_m30']} aligné={t['align_m30']} | H1: delta={t['d_h1']} aligné={t['align_h1']}")
        print(f"  Résolution: TP1x → {t['tp1x']['reason']} {t['tp1x']['pnl_pips']:+.2f}p | TP2x → {t['tp2x']['reason']} {t['tp2x']['pnl_pips']:+.2f}p")

    out = ROOT / "reports" / f"v10_edge_imbrique_{day}.json"
    out.write_text(json.dumps({
        "ts": dt.datetime.now(dt.UTC).isoformat(), "day": day,
        "config": {"delta_min": DELTA_MIN, "sl_ratio": SL_RATIO, "hold": HOLD_MAX,
                   "spread_pip": SPREAD_PIP},
        "stats": {k: [{"n": len(v), "wr": round(sum(1 for t in v if t[tp]["pnl_pips"] > 0) / len(v), 4) if v else 0,
                        "pnl": round(sum(t[tp]["pnl_pips"] for t in v), 2) if v else 0}
                       for tp in ("tp1x", "tp2x")] for k, v in stats.items()},
        "trades": all_trades,
        "audit": {"r9": "point_in_time strict, imbrication M5/M15/M30/H1",
                  "r10": "compute only, zero order real"},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport: {out}")


if __name__ == "__main__":
    main()