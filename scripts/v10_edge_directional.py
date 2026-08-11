"""Test décisif : edge directionnel PUR (TP=SL=1xATR, ratio symétrique).

Si l'edge est réel, même avec TP=SL symétrique (aucun avantage RR), le WR
doit rester > 50% et le PnL positif. Si le PnL positif précédent venait
seulement du ratio 2:1 (favorable au hasard), alors à ratio symétrique le
PnL s'effondre et le WR retombe à ~50% = PAS d'edge réel.

Règles :
- A: OVERLAP + delta_forces>=15
- B: LONDON + delta_forces 7..15
"""
from __future__ import annotations

import datetime as dt
import sqlite3

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
    return "OTHER"


def collect():
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
            for i in range(50, len(rows) - 6):
                d = F[i]
                ad = abs(d)
                sess = session_of(bts[i])
                sign = "BUY" if d > 0 else "SELL"
                entry = closes[i]
                atr = sum(highs[j] - lows[j] for j in range(i - 14, i)) / 14
                pip = 0.01 if pair.endswith("JPY") else 0.0001
                atr_pip = atr / pip if pip else 0
                rec = (bts[i], pair, sign, entry, atr_pip, closes, highs, lows, i)
                if sess == "OVERLAP" and ad >= 15:
                    sigs["A"].append(rec)
                if sess == "LONDON" and 7 <= ad < 15:
                    sigs["B"].append(rec)
    return sigs


def sim(rec, ratio=1.0, max_hold=4):
    _, pair, sign, entry, atr_pip, closes, highs, lows, i = rec
    if atr_pip <= 0:
        return 0.0
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    tp = atr_pip * ratio
    sl = atr_pip * ratio
    m = 1 if sign == "BUY" else -1
    for j in range(i + 1, min(i + 1 + max_hold, len(closes))):
        hi, lo = highs[j], lows[j]
        if m == 1:
            if hi >= entry + tp * pip:
                return tp
            if lo <= entry - sl * pip:
                return -sl
        else:
            if lo <= entry - tp * pip:
                return tp
            if hi >= entry + sl * pip:
                return -sl
    return (closes[min(i + max_hold, len(closes) - 1)] - entry) * m / pip


def main():
    sigs = collect()
    for rule, label in (("A", "OVERLAP mag_forte"), ("B", "LONDON mag_moyenne")):
        obs = sorted(sigs[rule], key=lambda x: x[0])
        n = len(obs)
        print(f"\n=== {label} (n={n}) — TEST DIRECTIONNEL PUR ===")
        for ratio in (1.0, 0.5, 0.0):
            pnls = [sim(rec, ratio=ratio) for rec in obs]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]
            wr = len(wins) / len(pnls) if pnls else 0
            total = sum(pnls)
            print(f"  ratio TP/SL={ratio}: WR={wr:.4f} PnL={total:+.2f} pips "
                  f"(gains={sum(wins):+.2f} pertes={sum(losses):+.2f})")
        # verdict
        pnls_sym = [sim(rec, ratio=1.0) for rec in obs]
        wr_sym = sum(1 for p in pnls_sym if p > 0) / len(pnls_sym) if pnls_sym else 0
        tot_sym = sum(pnls_sym)
        verdict = "EDGE DIRECTIONNEL RÉEL" if wr_sym >= 0.51 and tot_sym > 0 else "PAS D'EDGE (bruit RR)"
        print(f"  => VERDICT: {verdict}")


if __name__ == "__main__":
    main()
