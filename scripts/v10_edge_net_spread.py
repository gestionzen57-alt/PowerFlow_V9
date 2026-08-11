"""Edge OVERLAP — PnL net avec le VRAI spread distribué de chaque paire.

Décisif : au lieu d'un spread fixe, on utilise le spread réel observé de la
paire en session Overlap. Si PnL net > 0 avec le spread réel, l'edge est
actionnable. R10 : chiffre final avant toute décision micro-lot.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

DB = "data/v9_forces.db"
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF")
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")


def collect():
    # {pair: {"sigs": [(sign, entry, atr_pip, cl, hi, lo, i, pip)], "spreads": [pip]}}
    data = defaultdict(lambda: {"sigs": [], "spreads": []})
    for pair in PAIRS:
        base, quote = pair[:3], pair[3:6]
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT bar_time, high, low, close, spread_price, force_eur, force_usd, force_gbp, "
            "force_jpy, force_cad, force_chf, force_aud, force_nzd "
            "FROM forces_snapshots WHERE symbol=? AND timeframe='M15' AND is_closed_bar=1 "
            "ORDER BY bar_time ASC",
            (pair,),
        ).fetchall()
        con.close()
        if len(rows) < 100:
            continue
        F = [float(r[5 + CUR.index(base)]) - float(r[5 + CUR.index(quote)]) for r in rows]
        cl = [float(r[3]) for r in rows]
        hi = [float(r[1]) for r in rows]
        lo = [float(r[2]) for r in rows]
        sp = [float(r[4]) for r in rows]
        bt = [int(r[0]) for r in rows]
        pip = 0.01 if pair.endswith("JPY") else 0.0001
        for i in range(50, len(rows) - 8):
            h = dt.datetime.fromtimestamp(bt[i], tz=dt.UTC).hour
            if not (12 <= h < 16):
                continue
            d = F[i]
            if abs(d) < 15:
                continue
            entry = cl[i]
            atr = sum(hi[j] - lo[j] for j in range(i - 14, i)) / 14
            data[pair]["sigs"].append((1 if d > 0 else -1, entry, atr / pip if pip else 0, cl, hi, lo, i, pip))
            if sp[i] and sp[i] > 0:
                data[pair]["spreads"].append(sp[i] / pip)
    return data


def sim(rec, spread_pip):
    m, entry, atr_pip, cl, hi, lo, i, pip = rec
    if atr_pip <= 0:
        return 0.0
    tp, sl = atr_pip, atr_pip
    for j in range(i + 1, min(i + 1 + 4, len(cl))):
        if m == 1:
            if hi[j] >= entry + tp * pip:
                return tp - spread_pip
            if lo[j] <= entry - sl * pip:
                return -sl - spread_pip
        else:
            if lo[j] <= entry - tp * pip:
                return tp - spread_pip
            if hi[j] >= entry + sl * pip:
                return -sl - spread_pip
    return (cl[min(i + 4, len(cl) - 1)] - entry) * m / pip - spread_pip


def main():
    data = collect()
    print("=== EDGE OVERLAP — PnL net avec VRAI spread médian par paire ===")
    tot_n = tot_pnl = tot_wins = 0
    for pair, d in data.items():
        sigs = d["sigs"]
        if not sigs:
            continue
        spread = sum(d["spreads"]) / len(d["spreads"]) if d["spreads"] else 0.0
        pnls = [sim(s, spread) for s in sigs]
        wr = sum(1 for p in pnls if p > 0) / len(pnls)
        tot = sum(pnls)
        tot_n += len(pnls)
        tot_pnl += tot
        tot_wins += sum(1 for p in pnls if p > 0)
        print(f"  {pair:7s} n={len(pnls):4d} spread_med={spread:.2f} WR={wr:.4f} PnL_net={tot:+.2f} pips")
    print(f"\n  TOTAL: n={tot_n} WR={tot_wins/tot_n:.4f} PnL_net={tot_pnl:+.2f} pips")
    verdict = "ACTIONNABLE (PnL net > 0)" if tot_pnl > 0 else "NON ACTIONNABLE (spread tue l'edge)"
    print(f"  VERDICT: {verdict}")


if __name__ == "__main__":
    main()
