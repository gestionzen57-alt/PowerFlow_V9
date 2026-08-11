"""v10_market_reader_gbp.py — Lecture multi-couche GBPUSD (Fatman + VSA + MTF).

Exploite le cœur Fatman + VSA + multi-timeframe pour lire GBPUSD. Focus :
lecture des pics (extrem highs) pour vendre, anomalies et failles.

R10 : lecture only. Zéro ordre réel. Rapport JSON.
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

from core.v10.v10_fatman_db_reader import get_fatman_live  # noqa: E402
from core.v10.v10_vsa import compute_vsa  # noqa: E402

DB = ROOT / "data" / "v9_forces.db"
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")
FC = {c: f"force_{c.lower()}" for c in CUR}


def _load_bars(pair, tf, limit=200):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, tick_volume, spread_price "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (pair, tf, limit),
    ).fetchall()
    con.close()
    bars = []
    for r in reversed(rows):
        b = dict(r)
        for k in ("open", "high", "low", "close", "tick_volume", "spread_price"):
            b[k] = float(b.get(k) or 0.0)
        b["timestamp"] = dt.datetime.fromtimestamp(int(b["bar_time"]), tz=dt.UTC).isoformat()
        bars.append(b)
    return bars


def _read_fatman(pair, tf):
    try:
        st = get_fatman_live(pair, tf, db_path=str(DB))
        return {
            "source": st.source.value,
            "base_score": round(st.base_score, 1),
            "quote_score": round(st.quote_score, 1),
            "base_rank": st.base_rank,
            "quote_rank": st.quote_rank,
            "delta_score": round(st.delta_score, 2),
            "momentum": st.momentum.value,
            "is_stale": st.is_stale,
        }
    except Exception as e:
        return {"error": str(e)}


def _read_vsa(pair, tf, bars):
    try:
        ts = bars[-1]["timestamp"]
        st = compute_vsa(symbol=pair, timestamp=ts, timeframe=tf, bars=bars)
        return {
            "state": st.state.value,
            "ok": getattr(st, "ok", None),
            "effort_vs_result": round(getattr(st, "effort_vs_result", 0), 4),
            "volume_relative": round(getattr(st, "volume_relative", 0), 4),
            "no_supply": getattr(st, "no_supply", False),
            "no_demand": getattr(st, "no_demand", False),
            "stopping": getattr(st, "stopping_volume", getattr(st, "stopping", False)),
            "climax": getattr(st, "climax", False),
        }
    except Exception as e:
        return {"error": str(e)}


def _read_breakdown(pair, tf, bars):
    """Lecture de retournement : pics, exhaustion, structure, distribution."""
    n = len(bars)
    if n < 50:
        return {"error": "insufficient_bars"}
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    # pic récent : high du jour vs moyenne
    recent_high = max(highs[-20:])
    all_high = max(highs)
    # position du prix dans le range
    rng = all_high - min(lows)
    pos = (closes[-1] - min(lows)) / rng if rng else 0.5
    # momentum : pente des closes sur 20 barres
    slope = (closes[-1] - closes[-10]) / (closes[-10] or 1e-9) * 100
    # distribution VSA proxy : volume élevé + corps étroit + haut de range
    spread = [h - low for h, low in zip(highs[-5:], lows[-5:], strict=True)]
    bodies = [abs(c - b["open"]) for c, b in zip(closes[-5:], bars[-5:], strict=True)]
    return {
        "recent_high": round(recent_high, 5),
        "all_time_high": round(all_high, 5),
        "at_extreme_high": bool(closes[-1] >= recent_high * 0.999),
        "range_position": round(pos, 3),
        "momentum_20": round(slope, 3),
        "avg_spread_last5": round(sum(spread) / len(spread), 5),
        "avg_body_last5": round(sum(bodies) / len(bodies), 5),
        "distribution_proxy": bool(pos > 0.8 and bodies and sum(bodies) < sum(spread) * 0.3),
        "exhaustion_proxy": bool(slope > 0.5 and recent_high >= all_high * 0.998),
    }


def main():
    pair = "GBPUSD"
    print("=== LECTURE MULTI-COUCHE GBPUSD — Fatman + VSA + MTF ===")
    out = {"pair": pair, "ts": dt.datetime.now(dt.UTC).isoformat(), "audit": {"r10": "read only"}}
    for tf in ("H4", "H1", "M30"):
        bars = _load_bars(pair, tf)
        fat = _read_fatman(pair, tf)
        vsa = _read_vsa(pair, tf, bars)
        brk = _read_breakdown(pair, tf, bars)
        out[tf] = {"fatman": fat, "vsa": vsa, "breakdown": brk}
        print(f"\n[{tf}]")
        print(f"  Fatman: {fat}")
        print(f"  VSA: {vsa}")
        print(f"  Breakdown: {brk}")

    # Verdict synthèse pour GBPUSD
    h4 = out["H4"]
    verdict = _verdict(h4)
    out["verdict"] = verdict
    print(f"\n=== VERDICT GBPUSD ===\n{json.dumps(verdict, indent=1, ensure_ascii=False)}")

    rep = ROOT / "reports" / f"v10_market_reader_gbp_{dt.date.today().isoformat()}.json"
    rep.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport : {rep}")


def _verdict(h4):
    fat = h4.get("fatman", {})
    vsa = h4.get("vsa", {})
    brk = h4.get("breakdown", {})
    reasons = []
    score_sell = 0
    # Fatman : GBP très fort = potential overbought
    if fat.get("base_score", 50) >= 65:
        score_sell += 1
        reasons.append(f"Fatman GBP force {fat.get('base_score')} (très fort — potentiel épuisement)")
    if fat.get("momentum") == "UP" and fat.get("base_score", 50) > 60:
        reasons.append("Momentum UP mais force déjà extrême (chasse de sommet)")
    # VSA
    if vsa.get("stopping") or vsa.get("climax"):
        score_sell += 1
        reasons.append(f"VSA signale {'climax' if vsa.get('climax') else 'stopping'} (épuisement acheteur)")
    if vsa.get("no_demand"):
        score_sell += 1
        reasons.append("VSA no_demand (manque de demande au sommet)")
    # Breakdown
    if brk.get("at_extreme_high"):
        score_sell += 1
        reasons.append(f"Prix à l'extrême haut {brk.get('recent_high')} (pic)")
    if brk.get("exhaustion_proxy"):
        score_sell += 1
        reasons.append("Exhaustion : momentum + dans un nouveau sommet")
    if brk.get("distribution_proxy"):
        score_sell += 1
        reasons.append("Distribution proxy : corps étroit + haut de range (vente en distribution)")

    action = "SELL_BIAS (pic/extrême haut)" if score_sell >= 3 else ("WATCH_SELL" if score_sell >= 2 else "NEUTRAL")
    return {
        "action": action,
        "score_sell": score_sell,
        "reasons": reasons,
        "note": "Lecture only R10 — vendre les pics nécessite confirmation d'un rejet (SL au-dessus du sommet).",
    }


if __name__ == "__main__":
    main()
