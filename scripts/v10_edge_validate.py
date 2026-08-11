"""Validation rigoureuse freestyle — walk-forward glissant + PnL réel TP/SL.

Les 2 règles candidates :
- A: OVERLAP + delta_forces>=15, horizon 5
- B: LONDON + delta_forces 7..15, horizon 3

Tests :
1. Walk-forward glissant 5 fenêtres (chaque fenêtre = 20% de la série, on
   teste hors-échantillon) — un edge réel passe sur >=4/5 fenêtres.
2. PnL réel avec TP=2xATR, SL=1xATR, timeout (comme la doctrine) — un edge
   réel est rentable en pips.
3. Breakdown par paire : l'edge ne doit pas reposer sur 1 seule paire.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

DB = "data/v9_forces.db"
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF")
TFS = ("M15", "M30", "H1")
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")
FC = {c: f"force_{c.lower()}" for c in CUR}
COL = ["bar_time", "open", "high", "low", "close", "tick_volume", "spread_price", "direction", "vitesse"] + list(FC.values())


def session_of(bar_time):
    h = dt.datetime.fromtimestamp(bar_time, tz=dt.UTC).hour
    if 7 <= h < 12:
        return "LONDON"
    if 12 <= h < 16:
        return "OVERLAP"
    if 16 <= h < 20:
        return "NY"
    if 0 <= h < 7:
        return "ASIA"
    return "OTHER"


def collect_signals():
    """Retourne pour chaque règle une liste de (bar_time, pair, tf, sign, bars_idx_info)."""
    sigs = {"A": [], "B": []}
    for pair in PAIRS:
        base, quote = pair[:3], pair[3:6]
        for tf in TFS:
            con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            rows = con.execute(
                f"SELECT {', '.join(COL)} FROM forces_snapshots "
                "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 ORDER BY bar_time ASC",
                (pair, tf),
            ).fetchall()
            con.close()
            if len(rows) < 100:
                continue
            F = [float(r[9 + CUR.index(base)]) - float(r[9 + CUR.index(quote)]) for r in rows]
            closes = [float(r[4]) for r in rows]
            highs = [float(r[2]) for r in rows]
            lows = [float(r[3]) for r in rows]
            bts = [int(r[0]) for r in rows]
            for i in range(50, len(rows) - 10):
                d = F[i]
                ad = abs(d)
                sess = session_of(bts[i])
                sign = "BUY" if d > 0 else "SELL"
                entry = closes[i]
                # ATR approx (range moyen sur 14 barres)
                atr = sum(highs[j] - lows[j] for j in range(i - 14, i)) / 14
                pip = 0.01 if pair.endswith("JPY") else 0.0001
                atr_pip = atr / pip if pip else 0
                rec = (bts[i], pair, tf, sign, entry, atr_pip, closes, highs, lows, i)
                if sess == "OVERLAP" and ad >= 15:
                    sigs["A"].append(rec)
                if sess == "LONDON" and 7 <= ad < 15:
                    sigs["B"].append(rec)
    return sigs


def sim_trade(rec, tp_mult=2.0, sl_mult=1.0, max_hold=4):
    """Simule un trade avec TP/SL/ATR. Retourne pnl en pips."""
    bts, pair, tf, sign, entry, atr_pip, closes, highs, lows, i = rec
    if atr_pip <= 0:
        return 0.0
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    tp = atr_pip * tp_mult
    sl = atr_pip * sl_mult
    sign_m = 1 if sign == "BUY" else -1
    for j in range(i + 1, min(i + 1 + max_hold, len(closes))):
        hi = highs[j]
        lo = lows[j]
        if sign_m == 1:
            if hi >= entry + tp * pip:
                return tp
            if lo <= entry - sl * pip:
                return -sl
        else:
            if lo <= entry - tp * pip:
                return tp
            if hi >= entry + sl * pip:
                return -sl
    exit_p = closes[min(i + max_hold, len(closes) - 1)]
    return (exit_p - entry) * sign_m / pip


def main():
    sigs = collect_signals()
    for rule, label in (("A", "OVERLAP mag_forte h5"), ("B", "LONDON mag_moyenne h3")):
        obs = sorted(sigs[rule], key=lambda x: x[0])
        n = len(obs)
        if n < 200:
            print(f"=== {label}: n={n} insuffisant ===")
            continue
        print(f"\n=== {label} (n={n}) ===")
        # 1. Walk-forward glissant 5 fenêtres (direction)
        print("  Walk-forward glissant 5 fenêtres (acc direction):")
        n_wins_wf = 0
        for w in range(5):
            lo = int(n * w / 5)
            hi = int(n * (w + 1) / 5)
            win = obs[lo:hi]
            corr = 0
            for rec in win:
                bts, pair, tf, sign, entry, atr, closes, highs, lows, i = rec
                # résolution simple : close[i+5]
                fut = closes[min(i + 5, len(closes) - 1)] > entry
                corr += 1 if (sign == "BUY") == fut else 0
            acc = corr / len(win) if win else 0
            ok = "✅" if acc >= 0.54 else ("🔶" if acc >= 0.52 else "❌")
            if acc >= 0.52:
                n_wins_wf += 1
            print(f"    W{w+1}: n={len(win)} acc={acc:.4f} {ok}")
        print(f"  => {n_wins_wf}/5 fenêtres ≥52%")
        # 2. PnL réel TP/SL
        pnls = [sim_trade(rec) for rec in obs]
        wins = [p for p in pnls if p > 0]
        total = sum(pnls)
        wr = len(wins) / len(pnls) if pnls else 0
        print(f"  PnL réel (TP=2xATR, SL=1xATR, hold4): WR={wr:.4f} PnL={total:+.2f} pips")
        # 3. par paire
        by_pair = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0})
        for rec, p in zip(obs, pnls, strict=True):
            pr = rec[1]
            by_pair[pr]["n"] += 1
            by_pair[pr]["pnl"] += p
            by_pair[pr]["wins"] += 1 if p > 0 else 0
        print("  Par paire (PnL):")
        for pr, v in sorted(by_pair.items(), key=lambda kv: -kv[1]["pnl"]):
            print(f"    {pr}: n={v['n']} PnL={v['pnl']:+.2f} WR={v['wins']/v['n']:.2f}")


if __name__ == "__main__":
    main()
