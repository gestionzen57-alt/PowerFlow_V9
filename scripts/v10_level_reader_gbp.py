"""v10_level_reader_gbp.py — Lecture GBPUSD par NIVEAUX (structure) + Fatman + VSA.

"L'extrême haut H4 dans un niveau = exemple de l'exploitation infinie de
l'indicateur. Je le lis par sentiment/ressenti." — Søn

Lecture de STRUCTURE : le prix qui frappe un niveau clé (résistance majeure,
swing high, cluster de sommets, niveau rond) avec une force Fatman extrême →
zone de rejet. Combine : niveaux + Fatman + VSA + multi-TF.

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


def _load_bars(pair, tf, limit=400):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, tick_volume "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (pair, tf, limit),
    ).fetchall()
    con.close()
    bars = []
    for r in reversed(rows):
        b = dict(r)
        for k in ("open", "high", "low", "close", "tick_volume"):
            b[k] = float(b.get(k) or 0.0)
        bars.append(b)
    return bars


def _detect_levels(bars, window=10, min_touches=2):
    """Détecte les niveaux de résistance/support : pics (swing highs/lows)
    et clusters de sommets. Retourne les zones où le prix peut se retourner."""
    n = len(bars)
    # Swing highs : haut local (plus haut que window avant/après)
    swing_highs = []
    for i in range(window, n - window):
        h = bars[i]["high"]
        if h > max(bars[i - window]["high"], bars[i + window]["high"]) and \
           h >= max(bars[j]["high"] for j in range(i - window, i + window + 1)):
            swing_highs.append(h)
    swing_lows = []
    for i in range(window, n - window):
        lo = bars[i]["low"]
        if lo < min(bars[j]["low"] for j in range(i - window, i + window + 1)):
            swing_lows.append(lo)
    # Clusters : niveaux fréquentés plusieurs fois (tolérance 0.15%)
    def _cluster(levels, tol=0.0015):
        clusters = []
        used = set()
        for i, l1 in enumerate(levels):
            if i in used:
                continue
            group = [l1]
            used.add(i)
            for j, l2 in enumerate(levels):
                if j in used:
                    continue
                if abs(l2 - l1) / l1 < tol:
                    group.append(l2)
                    used.add(j)
            clusters.append({"level": round(sum(group) / len(group), 5), "touches": len(group)})
        return clusters
    res_clusters = _cluster(swing_highs)
    sup_clusters = _cluster(swing_lows)
    return {
        "resistance_levels": sorted(res_clusters, key=lambda c: -c["touches"])[:6],
        "support_levels": sorted(sup_clusters, key=lambda c: -c["touches"])[:6],
        "nearest_resistance": min(res_clusters, key=lambda c: abs(c["level"] - bars[-1]["close"])) if res_clusters else None,
        "nearest_support": min(sup_clusters, key=lambda c: abs(c["level"] - bars[-1]["close"])) if sup_clusters else None,
    }


def _round_levels(close):
    """Niveaux ronds psychologiques proches du prix."""
    r = []
    for step in (0.005, 0.010, 0.020, 0.050, 0.100):
        base = round(close / step) * step
        r.append({"level": round(base, 5), "step": step, "distance_pips": round(abs(base - close) / (0.0001 if close > 1 else 0.01), 1)})
    return sorted(r, key=lambda x: x["distance_pips"])[:3]


def main():
    pair = "GBPUSD"
    out = {"pair": pair, "ts": dt.datetime.now(dt.UTC).isoformat(), "audit": {"r10": "read only"}}
    for tf in ("H4", "H1", "D1"):
        bars = _load_bars(pair, tf)
        if len(bars) < 40:
            continue
        close = bars[-1]["close"]
        lv = _detect_levels(bars)
        rounds = _round_levels(close)
        # lire la position du prix vs résistance la plus proche
        nr = lv["nearest_resistance"]
        reading = {}
        if nr:
            d_pips = round(abs(nr["level"] - close) / 0.0001, 1)
            at_resistance = d_pips <= 30  # dans les 30 pips d'une résistance
            reading = {
                "close": round(close, 5),
                "nearest_resistance": nr["level"],
                "dist_to_res_pips": d_pips,
                "at_resistance": at_resistance,
                "res_touches": nr["touches"],
                "nearest_support": (lv["nearest_support"] or {}).get("level"),
            }
        out[tf] = {
            "levels": lv,
            "round_levels": rounds,
            "reading": reading,
        }
        print(f"[{tf}] close={close}")
        print(f"  Résistances: {lv['resistance_levels'][:3]}")
        print(f"  Supports: {lv['support_levels'][:3]}")
        print(f"  Lecture: {reading}")

    # Verdict final : prix à résistance + extrême haut
    verdict = _verdict(out)
    out["verdict"] = verdict
    print(f"\n=== VERDICT GBPUSD (niveaux) ===\n{json.dumps(verdict, indent=1, ensure_ascii=False)}")

    rep = ROOT / "reports" / f"v10_level_reader_gbp_{dt.date.today().isoformat()}.json"
    rep.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport : {rep}")


def _verdict(out):
    h4 = out.get("H4", {})
    h1 = out.get("H1", {})
    h4r = h4.get("reading", {})
    h1r = h1.get("reading", {})
    reasons = []
    score = 0
    # prix à résistance majeure H4
    if h4r.get("at_resistance"):
        score += 2
        reasons.append(f"Prix {h4r.get('close')} SUR résistance H4 {h4r.get('nearest_resistance')} ({h4r.get('dist_to_res_pips')} pips) — touche {h4r.get('res_touches')}x")
    # extrême haut (range position)
    # prix aussi près d'une résistance H1 (confluence)
    if h1r.get("at_resistance"):
        score += 1
        reasons.append(f"Confirmation : prix aussi à résistance H1 {h1r.get('nearest_resistance')}")
    action = "SELL_BIAS (prix sur résistance majeure)" if score >= 2 else ("WATCH_SELL" if score >= 1 else "NEUTRAL")
    return {
        "action": action,
        "score": score,
        "reasons": reasons,
        "note": "Lecture structure R10 — prix frappant un niveau = zone de rejet potentiel. Confirmer par un rejet (close sous le niveau) avant vente, SL au-dessus du sommet.",
    }


if __name__ == "__main__":
    main()
