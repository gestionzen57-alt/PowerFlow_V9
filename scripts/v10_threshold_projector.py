"""v10_threshold_projector.py — Projecteur de seuils GBPUSD (anticipation).

"Trouver les seuils AVANT les faits, anticiper et projeter." — Søn

Apprend de l'historique QUAND GBPUSD retourne, en combinant les facteurs
(force GBP, position dans le range, momentum, distance à résistance), puis
projette les seuils de retournement sur le futur.

Méthode (honnête, R9) :
1. Sur l'historique H4, pour chaque barre, calculer les facteurs.
2. Mesurer le retournement 5 barres plus tard (baisse > X pips).
3. Trouver les combinaisons de facteurs qui précèdent le plus souvent un
   retournement (taux > 55% avec n suffisant).
4. Projeter : si le marché actuel matche une combinaison gagnante → alerte
   "seuil de retournement probable".

R10 : lecture only, zéro ordre.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data" / "v9_forces.db").exists() else Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "v9_forces.db"
PAIR = "GBPUSD"
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")


def _load_h4():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, force_eur, force_usd, force_gbp, force_jpy, "
        "force_cad, force_chf, force_aud, force_nzd "
        "FROM forces_snapshots WHERE symbol=? AND timeframe='H4' AND is_closed_bar=1 "
        "ORDER BY bar_time ASC",
        (PAIR,),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _factors(bars, i):
    """Facteurs à la barre i (tout calculé sur données <= i, pas de lookahead)."""
    gbp = float(bars[i]["force_gbp"])
    usd = float(bars[i]["force_usd"])
    close = float(bars[i]["close"])
    # position dans le range des 30 dernières barres
    win = bars[max(0, i - 30):i + 1]
    hi = max(float(b["high"]) for b in win)
    lo = min(float(b["low"]) for b in win)
    pos = (close - lo) / (hi - lo) if hi > lo else 0.5
    # momentum GBP (force i vs i-3)
    mom_gbp = gbp - float(bars[i - 3]["force_gbp"]) if i >= 3 else 0.0
    # momentum prix (close i vs i-3)
    mom_price = (close - float(bars[i - 3]["close"])) / (float(bars[i - 3]["close"]) or 1e-9) * 100 if i >= 3 else 0.0
    # DISTANCE À LA RÉSISTANCE : swing high le plus proche au-dessus du prix
    res = None
    dist_res = None
    for j in range(max(0, i - 40), i):
        h = float(bars[j]["high"])
        if h > close and (res is None or h < res):
            res = h
    if res is not None:
        dist_res = (res - close) / 0.0001  # en pips
    return {
        "gbp": gbp, "usd": usd, "pos": pos, "mom_gbp": mom_gbp, "mom_price": mom_price,
        "close": close, "bar_time": int(bars[i]["bar_time"]),
        "resistance": round(res, 5) if res else None,
        "dist_res_pips": round(dist_res, 1) if dist_res is not None else None,
    }


def _reversal(bars, i, horizon=5, pips=20):
    """Retournement baissier : prix baisse de >pips pips sur horizon barres."""
    if i + horizon >= len(bars):
        return None
    c0 = float(bars[i]["close"])
    cH = float(bars[i + horizon]["close"])
    drop = (c0 - cH) / 0.0001
    return drop > pips


def _learn():
    bars = _load_h4()
    if len(bars) < 100:
        return None, []
    # Combinaisons de facteurs → taux de retournement
    combos = defaultdict(lambda: {"n": 0, "rev": 0})
    for i in range(40, len(bars) - 6):
        f = _factors(bars, i)
        rev = _reversal(bars, i)
        if rev is None:
            continue
        # buckets
        gbp_b = "GBP>=70" if f["gbp"] >= 70 else ("GBP60-70" if f["gbp"] >= 60 else "GBP<60")
        pos_b = "haut_range" if f["pos"] >= 0.7 else ("milieu" if f["pos"] >= 0.4 else "bas_range")
        mom_b = "mom_neg" if f["mom_price"] < 0 else "mom_pos"
        res_b = "proche_res" if f["dist_res_pips"] is not None and f["dist_res_pips"] <= 30 else "loin_res"
        # combos
        keys = [
            f"{gbp_b}|{pos_b}",
            f"{gbp_b}|{mom_b}",
            f"{pos_b}|{mom_b}",
            f"{gbp_b}|{pos_b}|{mom_b}",
            f"{gbp_b}|{res_b}",
            f"{res_b}|{mom_b}",
            f"{gbp_b}|{res_b}|{mom_b}",
            f"{gbp_b}|{pos_b}|{res_b}|{mom_b}",
        ]
        for k in keys:
            combos[k]["n"] += 1
            combos[k]["rev"] += 1 if rev else 0
    # garder les combos avec n>=15 et taux>=55%
    rules = []
    for k, v in combos.items():
        if v["n"] >= 15 and v["rev"] / v["n"] >= 0.55:
            rules.append({"combo": k, "n": v["n"], "rev_rate": round(v["rev"] / v["n"], 3)})
    rules.sort(key=lambda r: -r["rev_rate"])
    return rules, bars


def _project(rules, bars):
    """Projette sur la barre courante : matche-t-elle une règle de retournement ?"""
    if not bars:
        return None
    f = _factors(bars, len(bars) - 1)
    gbp_b = "GBP>=70" if f["gbp"] >= 70 else ("GBP60-70" if f["gbp"] >= 60 else "GBP<60")
    pos_b = "haut_range" if f["pos"] >= 0.7 else ("milieu" if f["pos"] >= 0.4 else "bas_range")
    mom_b = "mom_neg" if f["mom_price"] < 0 else "mom_pos"
    res_b = "proche_res" if f["dist_res_pips"] is not None and f["dist_res_pips"] <= 30 else "loin_res"
    current = f"{gbp_b}|{pos_b}|{res_b}|{mom_b}"
    matched = [r for r in rules if r["combo"] == current]
    return {
        "current": current, "factors": {k: round(v, 3) if isinstance(v, float) else v for k, v in f.items()},
        "matched_rule": matched[0] if matched else None,
        "all_rules": rules[:8],
    }


def main():
    rules, bars = _learn()
    print("=== PROJECTEUR DE SEUILS GBPUSD (apprentissage historique) ===")
    print(f"{len(bars)} barres H4 analysées")
    print("\nRègles de retournement apprises (n>=15, taux>=55%):")
    if not rules:
        print("  (aucune règle fiable — la force seule ne prédit pas)")
    for r in rules[:8]:
        print(f"  {r['combo']:30s} n={r['n']:4d} rev_rate={r['rev_rate']:.3f}")
    proj = _project(rules, bars)
    print("\n=== PROJECTION SUR LE MARCHÉ ACTUEL ===")
    if proj:
        print(f"  Facteurs actuels: {proj['factors']}")
        print(f"  Combo actuel: {proj['current']}")
        if proj["matched_rule"]:
            m = proj["matched_rule"]
            print(f"  ⚠️ MATCH RÈGLE DE RETOURNEMENT: {m['combo']} (rev_rate={m['rev_rate']})")
            print("  → Seuil de retournement baissier PROBABLE")
        else:
            print("  Aucune règle de retournement ne matche — pas de seuil anticipé")
    out = ROOT / "reports" / f"v10_threshold_projection_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps({"ts": dt.datetime.now(dt.UTC).isoformat(), "rules": rules, "projection": proj,
                               "audit": {"r10": "read only", "method": "historique H4, no lookahead"}},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport : {out}")


if __name__ == "__main__":
    main()
