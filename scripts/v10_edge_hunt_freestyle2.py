"""Edge hunt V10 freestyle 2 — magnitude + session + seuils (SANS lookahead).

Le scan de signe (freestyle 1) = bruit. Ici on teste si la MAGNITUDE du
déséquilibre de forces prédit la continuation : delta forces fort → la
direction se poursuit plus souvent ? Et par session / par paire.

Rien à perdre. On jette tout ce qui ne passe pas.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

DB = "data/v9_forces.db"
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF")
TFS = ("M15", "M30", "H1")
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")
FC = {c: f"force_{c.lower()}" for c in CUR}
COL = ["bar_time", "open", "high", "low", "close", "tick_volume", "spread_price", "direction", "vitesse"] + list(FC.values())


def session_of(bar_time):
    import datetime as dt
    h = dt.datetime.fromtimestamp(bar_time, tz=dt.UTC).hour
    if 7 <= h < 12:
        return "LONDON"
    if 13 <= h < 16:
        return "OVERLAP"
    if 16 <= h < 20:
        return "NY"
    if 0 <= h < 7:
        return "ASIA"
    return "OTHER"


def run():
    agg = defaultdict(lambda: {"n": 0, "correct": 0})
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
            bts = [int(r[0]) for r in rows]
            for h in (1, 3, 5):
                for i in range(50, len(rows) - h):
                    fut = closes[i + h] > closes[i]
                    d = F[i]
                    ad = abs(d)
                    sess = session_of(bts[i])
                    # magnitude : fort / moyen / faible déséquilibre
                    if ad >= 15:
                        mag = "forte"
                    elif ad >= 7:
                        mag = "moyenne"
                    elif ad >= 3:
                        mag = "faible"
                    else:
                        mag = "nulle"
                    keys = [
                        f"sign_all_h{h}",
                        f"mag_{mag}_h{h}",
                        f"{sess}_h{h}",
                        f"{sess}_mag_{mag}_h{h}",
                        f"mag_{mag}_{sess}_h{h}",
                    ]
                    for k in keys:
                        agg[k]["n"] += 1
                        agg[k]["correct"] += 1 if (d > 0) == fut else 0
    print("=== SCAN MAGNITUDE + SESSION (direction forces vs future) ===")
    ranked = sorted(agg.items(), key=lambda kv: -kv[1]["correct"] / max(1, kv[1]["n"]))
    for name, v in ranked:
        n = v["n"]
        acc = v["correct"] / n if n else 0
        edge = acc - 0.5
        verdict = "EDGE" if acc >= 0.54 and n >= 300 else ("maybe" if acc >= 0.52 else "bruit")
        if acc >= 0.51 or n >= 300:
            print(f"{name:28s} {n:8d} {acc:7.4f} {edge:+7.4f}  {verdict}")


if __name__ == "__main__":
    run()
