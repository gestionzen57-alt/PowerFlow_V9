"""Walk-forward honnête des candidats EDGE freestyle (11/08).

Candidats détectés au scan :
- OVERLAP_mag_forte_h5 : delta forces >= 15, session OVERLAP, horizon 5 → 56.2%
- LONDON_mag_moyenne_h3 : delta forces [7,15), LONDON, horizon 3 → 56.1%

Validation rigoureuse : chaque candidat testé sur 2 moitiés temporelles
(train = ancienne, test = récente). Un edge réel DOIT rester > 54% sur la
moitié de test (hors-échantillon), sinon = surapprentissage du data-mining.
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
    if 16 <= h < 20:
        return "NY"
    if 0 <= h < 7:
        return "ASIA"
    return "OTHER"


def collect():
    """Collecte toutes les observations (features + cible) pour les 2 règles."""
    obs = []
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
            for i in range(50, len(rows) - 5):
                d = F[i]
                ad = abs(d)
                sess = session_of(bts[i])
                fut5 = closes[i + 5] > closes[i]
                fut3 = closes[i + 3] > closes[i]
                # Règle A : OVERLAP + delta forte + horizon 5
                if sess == "OVERLAP" and ad >= 15:
                    obs.append(("OVERLAP_mag_forte_h5", bts[i], d > 0, fut5))
                # Règle B : LONDON + delta moyenne + horizon 3
                if sess == "LONDON" and 7 <= ad < 15:
                    obs.append(("LONDON_mag_moyenne_h3", bts[i], d > 0, fut3))
    return obs


def walk(rule_obs, label):
    obs = sorted(rule_obs, key=lambda x: x[1])  # chronologique
    n = len(obs)
    if n < 100:
        print(f"{label}: n={n} — insuffisant")
        return
    half = n // 2
    train = obs[:half]
    test = obs[half:]
    for name, sub in (("TRAIN(ancien)", train), ("TEST(récent)", test)):
        correct = sum(1 for _, _, pred, fut in sub if pred == fut)
        acc = correct / len(sub) if sub else 0
        print(f"  {name:14s} n={len(sub):5d} acc={acc:.4f} ({'✅ EDGE' if acc>=0.54 else ('🔶' if acc>=0.52 else '❌ bruit')})")
    t_correct = sum(1 for _, _, pred, fut in test if pred == fut)
    t_acc = t_correct / len(test) if test else 0
    print(f"  VERDICT: {'EDGE CONFIRMÉ' if t_acc>=0.54 else 'SUREXPLOITÉ (data-mining)'}")


def main():
    obs = collect()
    for rule in ("OVERLAP_mag_forte_h5", "LONDON_mag_moyenne_h3"):
        rule_obs = [o for o in obs if o[0] == rule]
        print(f"=== Walk-forward {rule} (n={len(rule_obs)}) ===")
        walk(rule_obs, rule)


if __name__ == "__main__":
    main()
