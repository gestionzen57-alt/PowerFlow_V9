"""Robustesse spread + horizon pour OVERLAP (avec direction correcte).

Vérifie que l'edge OVERLAP mag_forte survit au spread réaliste (0.5-1 pip)
et reste rentable à TP/SL symétrique (aucun avantage RR). Le signe BUY/SELL
est géré correctement (bug du test one-off corrigé).
"""
from __future__ import annotations

import datetime as dt
import sqlite3

DB = "data/v9_forces.db"
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF")
TFS = ("M15", "M30", "H1")
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")


def session_of(bar_time):
    h = dt.datetime.fromtimestamp(bar_time, tz=dt.UTC).hour
    if 7 <= h < 12:
        return "LONDON"
    if 12 <= h < 16:
        return "OVERLAP"
    return "OTHER"


def collect():
    sigs = []
    for pair in PAIRS:
        base, quote = pair[:3], pair[3:6]
        for tf in TFS:
            con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
            rows = con.execute(
                "SELECT bar_time, high, low, close, force_eur, force_usd, force_gbp, "
                "force_jpy, force_cad, force_chf, force_aud, force_nzd "
                "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
                "ORDER BY bar_time ASC",
                (pair, tf),
            ).fetchall()
            con.close()
            if len(rows) < 100:
                continue
            F = [float(r[4 + CUR.index(base)]) - float(r[4 + CUR.index(quote)]) for r in rows]
            cl = [float(r[3]) for r in rows]
            hi = [float(r[1]) for r in rows]
            lo = [float(r[2]) for r in rows]
            bt = [int(r[0]) for r in rows]
            for i in range(50, len(rows) - 8):
                d = F[i]
                if abs(d) < 15:
                    continue
                if session_of(bt[i]) != "OVERLAP":
                    continue
                entry = cl[i]
                atr = sum(hi[j] - lo[j] for j in range(i - 14, i)) / 14
                pip = 0.01 if pair.endswith("JPY") else 0.0001
                sigs.append((pair, 1 if d > 0 else -1, entry, atr / pip if pip else 0, cl, hi, lo, i, pip))
    return sigs


def sim(rec, hold=4, spread=0.0):
    _, m, entry, atr_pip, cl, hi, lo, i, pip = rec
    if atr_pip <= 0:
        return 0.0
    tp = atr_pip
    sl = atr_pip
    for j in range(i + 1, min(i + 1 + hold, len(cl))):
        if m == 1:
            if hi[j] >= entry + tp * pip:
                return tp - spread
            if lo[j] <= entry - sl * pip:
                return -sl - spread
        else:
            if lo[j] <= entry - tp * pip:
                return tp - spread
            if hi[j] >= entry + sl * pip:
                return -sl - spread
    return (cl[min(i + hold, len(cl) - 1)] - entry) * m / pip - spread


def main():
    sigs = collect()
    print(f"=== OVERLAP mag_forte (n={len(sigs)}) — robustesse spread + horizon ===")
    for sp in (0.0, 0.5, 1.0):
        pn = [sim(s, spread=sp) for s in sigs]
        wr = sum(1 for p in pn if p > 0) / len(pn)
        tot = sum(pn)
        print(f"  spread={sp}: WR={wr:.4f} PnL={tot:+.2f} pips")
    for hold in (2, 4, 6):
        pn = [sim(s, hold=hold) for s in sigs]
        wr = sum(1 for p in pn if p > 0) / len(pn)
        tot = sum(pn)
        print(f"  hold={hold}: WR={wr:.4f} PnL={tot:+.2f} pips")


if __name__ == "__main__":
    main()
