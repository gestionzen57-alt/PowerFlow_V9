"""Edge hunt V10 freestyle (11/08) — scan agressif SANS lookahead.

Cherche un signal prédictif de la direction future parmi les features
brutes de forces_snapshots. Honnête : features calculées à la barre t,
cible = direction à horizon H (barres futures).

Rien à perdre, on teste tout, on jette tout ce qui ne passe pas.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict

DB = "data/v9_forces.db"
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF")
TFS = ("M15", "M30", "H1")
HORIZONS = (1, 3)
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")
FC = {c: f"force_{c.lower()}" for c in CUR}
COL = ["bar_time", "open", "high", "low", "close", "tick_volume", "spread_price", "direction", "vitesse"] + list(FC.values())


def _load(pair, tf):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        f"SELECT {', '.join(COL)} FROM forces_snapshots "
        "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 ORDER BY bar_time ASC",
        (pair, tf),
    ).fetchall()
    con.close()
    return rows


def run():
    results = defaultdict(lambda: {"n": 0, "correct": 0})
    for pair in PAIRS:
        base = pair[:3]
        quote = pair[3:6]
        for tf in TFS:
            rows = _load(pair, tf)
            if len(rows) < 100:
                continue
            F = [float(r[9 + CUR.index(base)]) - float(r[9 + CUR.index(quote)]) for r in rows]
            closes = [float(r[4]) for r in rows]
            vols = [float(r[5]) for r in rows]
            spreads = [float(r[6]) for r in rows]
            dirc = [str(r[7]).lower() for r in rows]

            for h in HORIZONS:
                for i in range(50, len(rows) - h):
                    fut = closes[i + h] > closes[i]
                    dir_up = any(w in dirc[i] for w in ("long", "buy", "bull"))
                    mom = F[i] - F[i - 1]
                    v10 = sum(vols[max(0, i - 10):i]) / 10 or 1e-9
                    s10 = sum(spreads[max(0, i - 10):i]) / 10 or 1e-9
                    vol_up = vols[i] > v10
                    sp_hi = spreads[i] > s10
                    cmom = closes[i] > closes[i - 3]
                    feats = {
                        f"sign_forces_h{h}": (F[i] > 0, fut),
                        f"dir_col_h{h}": (dir_up, fut),
                        f"mom_forces_h{h}": (mom > 0, fut),
                        f"vol_up_h{h}": (vol_up, fut),
                        f"spread_hi_h{h}": (sp_hi, fut),
                        f"cmom_h{h}": (cmom, fut),
                        f"forces_and_cmom_h{h}": ((F[i] > 0 and cmom), fut),
                        f"forces_and_dircol_h{h}": ((F[i] > 0 and dir_up), fut),
                        f"mom_and_cmom_h{h}": ((mom > 0 and cmom), fut),
                    }
                    for name, (pred, actual) in feats.items():
                        results[name]["n"] += 1
                        results[name]["correct"] += 1 if pred == actual else 0
    print("=== SCAN EDGE FREESTYLE (features vs direction future) ===")
    print(f"{'feature':26s} {'n':>8s} {'acc':>7s} {'edge':>7s}  verdict")
    ranked = sorted(results.items(), key=lambda kv: -kv[1]["correct"] / max(1, kv[1]["n"]))
    for name, v in ranked:
        n = v["n"]
        acc = v["correct"] / n if n else 0
        edge = acc - 0.5
        verdict = "EDGE" if acc >= 0.54 and n >= 800 else ("maybe" if acc >= 0.52 else "bruit")
        print(f"{name:26s} {n:8d} {acc:7.4f} {edge:+7.4f}  {verdict}")


if __name__ == "__main__":
    run()
