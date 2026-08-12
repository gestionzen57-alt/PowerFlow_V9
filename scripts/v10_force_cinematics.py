"""v10_force_cinematics.py — Lecture CINÉMATIQUE de la courbe Fatman GBPUSD.

Søn : "Tu vois des valeurs mais pas toute la cinématique — les courbes,
pics et creux." Ce module extrait de la COURBE de la force GBP (et USD) :
- pics / creux locaux et leur timing
- pente / accélération de la courbe
- DIVERGENCE force vs prix (force décline pendant que le prix pousse)
- exhaustion : pic brutal puis retombée

C'est la lecture "en courbe" qui complète la lecture "en valeur".

R10 : lecture only, zéro ordre.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data" / "v9_forces.db").exists() else Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "v9_forces.db"
PAIR = "GBPUSD"


def _load_series(tf, n=60):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT bar_time, force_gbp, force_usd, close "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time ASC",
        (PAIR, tf),
    ).fetchall()
    con.close()
    return rows[-n:]


def _pivots(vals, window=3):
    """Pics/creux locaux (fenêtre window de chaque côté)."""
    n = len(vals)
    highs = []
    lows = []
    for i in range(window, n - window):
        v = vals[i]
        if v >= max(vals[i - window:i + window + 1]):
            highs.append((i, v))
        if v <= min(vals[i - window:i + window + 1]):
            lows.append((i, v))
    return highs, lows


def _analyze(series, label):
    """Analyse cinématique d'une série de (bar_time, gbp, usd, close)."""
    if len(series) < 10:
        return {"error": "insufficient"}
    gbp = [s[1] for s in series]
    prices = [s[3] for s in series]
    n = len(gbp)

    # pics/creux de la force GBP
    gbp_highs, gbp_lows = _pivots(gbp)
    gbp_pic = max(gbp_highs, key=lambda x: x[1]) if gbp_highs else None
    gbp_creux = min(gbp_lows, key=lambda x: x[1]) if gbp_lows else None

    # pente récente (5 dernières barres) de la force et du prix
    slope_gbp = (gbp[-1] - gbp[-5]) if n >= 5 else 0
    slope_price = (prices[-1] - prices[-5]) / (prices[-5] or 1e-9) * 100 if n >= 5 else 0

    # DIVERGENCE : pic de force GBP il y a >2 barres, la force décline ensuite,
    # MAIS le prix fait un nouveau sommet récent sans confirmation de la force.
    divergence = False
    divergence_detail = None
    # dernier pic de force (excluant les 2 dernières barres pour chercher le déclin)
    for (i, v) in gbp_highs:
        if i <= n - 3:
            # la force a-t-elle décliné depuis le pic ?
            force_declined = gbp[-1] < v - 3
            # le prix a-t-il atteint un nouveau haut APRÈS le pic de force ?
            price_made_new_high = prices[-1] > max(prices[i + 1:]) or \
                (len(prices) > i + 1 and max(prices[i + 1:]) > max(prices[max(0, i - 3):i + 1]))
            # prix actuel proche du sommet (dans les 20 pips)
            price_near_top = (max(prices) - prices[-1]) / 0.0001 < 20
            if force_declined and price_made_new_high and price_near_top:
                divergence = True
                divergence_detail = {
                    "force_pic": round(v, 1), "force_pic_bars_ago": n - 1 - i,
                    "force_now": round(gbp[-1], 1),
                    "price_top": round(max(prices), 5), "price_now": round(prices[-1], 5),
                }
            break

    # Exhaustion : pic récent (dans les 10 dernières barres) puis retombée
    recent_pic = None
    for (i, v) in gbp_highs:
        if i >= n - 10:
            recent_pic = (i, v)
    exhaustion = False
    if recent_pic and gbp[-1] < recent_pic[1] - 5:
        exhaustion = True

    # accélération : pente de la pente (2e dérivée sur 4 barres)
    accel = (gbp[-1] - gbp[-3]) - (gbp[-3] - gbp[-5]) if n >= 6 else 0

    return {
        "label": label,
        "last_price": round(prices[-1], 5),
        "last_gbp": round(gbp[-1], 1),
        "gbp_pic": round(gbp_pic[1], 1) if gbp_pic else None,
        "gbp_pic_bars_ago": n - 1 - gbp_pic[0] if gbp_pic else None,
        "gbp_creux": round(gbp_creux[1], 1) if gbp_creux else None,
        "slope_gbp_5": round(slope_gbp, 1),
        "slope_price_5": round(slope_price, 3),
        "divergence_force_price": divergence,
        "divergence_detail": divergence_detail,
        "exhaustion_pic": exhaustion,
        "acceleration_gbp": round(accel, 1),
    }


def main():
    print("=== CINÉMATIQUE DE LA COURBE FATMAN GBPUSD (force + prix) ===")
    out = {"pair": PAIR, "ts": dt.datetime.now(dt.UTC).isoformat(), "audit": {"r10": "read only"}}
    for tf in ("H4", "H1"):
        series = _load_series(tf)
        if len(series) < 10:
            print(f"[{tf}] données insuffisantes")
            continue
        a = _analyze(series, tf)
        out[tf] = a
        print(f"\n[{tf}]")
        for k, v in a.items():
            print(f"  {k}: {v}")

    # Verdict
    verdict = _verdict(out)
    out["verdict"] = verdict
    print(f"\n=== VERDICT CINÉMATIQUE ===\n{json.dumps(verdict, indent=1, ensure_ascii=False)}")

    rep = ROOT / "reports" / f"v10_force_cinematics_{dt.date.today().isoformat()}.json"
    rep.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport : {rep}")


def _verdict(out):
    reasons = []
    score = 0
    for tf in ("H4", "H1"):
        a = out.get(tf, {})
        if a.get("divergence_force_price"):
            score += 2
            reasons.append(f"[{tf}] DIVERGENCE : force GBP baisse mais prix monte (piège de sommet)")
        if a.get("exhaustion_pic"):
            score += 2
            reasons.append(f"[{tf}] EXHAUSTION : pic de force {a.get('gbp_pic')} puis retombée (épuisement acheteur)")
        if a.get("slope_gbp_5", 0) < 0 and a.get("slope_price_5", 0) > 0:
            score += 1
            reasons.append(f"[{tf}] Force décline ({a.get('slope_gbp_5')}) pendant que prix monte ({a.get('slope_price_5')}%)")
    action = "DIVERGENCE SOMMET — retournement vendeur probable" if score >= 3 else ("WATCH" if score >= 2 else "NEUTRAL")
    return {"action": action, "score": score, "reasons": reasons,
            "note": "Lecture cinématique R10. Divergence force/prix = le sommet du prix n'est pas confirmé par la force → piège à vendre."}


if __name__ == "__main__":
    main()
