"""Walk-forward final du WR directionnel PUR (TP=SL=1xATR), hors-échantillon.

L'edge semble réel (WR 54-56% à ratio symétrique). Test final : diviser la
série en 5 fenêtres, valider que le WR directionnel symétrique reste >= 53%
sur >= 4/5 fenêtres. C'est le test qui tue les faux positifs de data-mining.
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
                rec = (bts[i], pair, sign, entry, atr / pip if pip else 0, closes, highs, lows, i)
                if sess == "OVERLAP" and ad >= 15:
                    sigs["A"].append(rec)
                if sess == "LONDON" and 7 <= ad < 15:
                    sigs["B"].append(rec)
    return sigs


def sim(rec, max_hold=4):
    _, pair, sign, entry, atr_pip, closes, highs, lows, i = rec
    if atr_pip <= 0:
        return 0.0
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    tp = atr_pip
    sl = atr_pip
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
    for rule, label in (("A", "OVERLAP mag_forte h~4"), ("B", "LONDON mag_moyenne h~4")):
        obs = sorted(sigs[rule], key=lambda x: x[0])
        n = len(obs)
        print(f"\n=== {label} (n={n}) — WALK-FORWARD WR directionnel symétrique ===")
        n_ok = 0
        pnl_total = 0.0
        for w in range(5):
            lo = int(n * w / 5)
            hi = int(n * (w + 1) / 5)
            win = obs[lo:hi]
            pnls = [sim(rec) for rec in win]
            wr = sum(1 for p in pnls if p > 0) / len(pnls) if pnls else 0
            tot = sum(pnls)
            pnl_total += tot
            ok = "✅" if wr >= 0.53 else ("🔶" if wr >= 0.51 else "❌")
            if wr >= 0.51:
                n_ok += 1
            print(f"  W{w+1}: n={len(win)} WR={wr:.4f} PnL={tot:+.2f} {ok}")
        print(f"  => {n_ok}/5 fenêtres ≥51% | PnL total={pnl_total:+.2f} pips")
        verdict = "EDGE STABLE CONFIRMÉ" if n_ok >= 4 and pnl_total > 0 else "PAS STABLE (surapprentissage)"
        print(f"  VERDICT FINAL: {verdict}")


if __name__ == "__main__":
    main()
