"""v10_liquidity_sweep.py — Détection de sweep de liquidité (stop hunt) GBPUSD.

Comble la lacune : reconnaître quand le prix a BALAYÉ un niveau de liquidité
(equal highs/lows, swing highs/lows) pour prendre les stops, puis anticiper
le retournement. Combine SMC + ICT + liquidité + Fatman.

Concepts (SMC/ICT) :
- Buy-side liquidity : pool de stops au-dessus d'un high (shorts piégés).
- Sell-side liquidity : pool de stops en dessous d'un low (longs piégés).
- SWEEP : le prix dépasse un niveau de liquidité (wick) puis se retourne.
- MSS/CHoCH : cassure contre la tendance = confirmation du retournement.

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

from core.v10.v10_fatman_db_reader import get_fatman_live  # noqa: E402
from core.v10.v10_liquidity_map import get_liquidity_map  # noqa: E402
from core.v10.v10_smc import detect_smc  # noqa: E402

DB = ROOT / "data" / "v9_forces.db"
PAIR = "GBPUSD"


def _load_bars(tf, limit=300):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, tick_volume "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (PAIR, tf, limit),
    ).fetchall()
    con.close()
    bars = []
    for r in reversed(rows):
        b = dict(r)
        for k in ("open", "high", "low", "close", "tick_volume"):
            b[k] = float(b.get(k) or 0.0)
        b["timestamp"] = dt.datetime.fromtimestamp(int(b["bar_time"]), tz=dt.UTC).isoformat()
        bars.append(b)
    return bars


def _detect_sweep(bars, lookback=40, wick_pips=5):
    """Détecte un sweep de liquidité : le prix dépasse un swing high/low récent
    (wick) puis se referme en dessous/au-dessus (rejet)."""
    if len(bars) < lookback + 2:
        return None
    cur = bars[-1]
    close = cur["close"]
    high = cur["high"]
    low = cur["low"]
    # swing highs/lows récents (hors dernière bougie)
    swing_highs = []
    swing_lows = []
    for i in range(3, len(bars) - 1):
        h = bars[i]["high"]
        lo = bars[i]["low"]
        if h >= max(bars[j]["high"] for j in range(max(0, i - 3), min(len(bars), i + 4))):
            swing_highs.append(h)
        if lo <= min(bars[j]["low"] for j in range(max(0, i - 3), min(len(bars), i + 4))):
            swing_lows.append(lo)
    if not swing_highs and not swing_lows:
        return None
    pip = 0.0001
    # Sweep de buy-side liquidity : high dépasse un swing high, close revient sous
    for sh in swing_highs:
        if high > sh + wick_pips * pip and close < sh:
            return {
                "type": "BUY_SIDE_SWEEP",
                "level": round(sh, 5),
                "wick_pips": round((high - sh) / pip, 1),
                "close_below": close < sh,
                "direction": "SELL_BIAS",
                "reason": f"Prix a balayé le high {sh:.5f} (wick {round((high - sh) / pip, 1)}p) puis close sous — stops longs pris, retournement probable",
            }
    # Sweep de sell-side liquidity : low dépasse un swing low, close revient au-dessus
    for sl in swing_lows:
        if low < sl - wick_pips * pip and close > sl:
            return {
                "type": "SELL_SIDE_SWEEP",
                "level": round(sl, 5),
                "wick_pips": round((sl - low) / pip, 1),
                "close_above": close > sl,
                "direction": "BUY_BIAS",
                "reason": f"Prix a balayé le low {sl:.5f} (wick {wick_pips}p) puis close au-dessus — stops shorts pris, rebond probable",
            }
    return None


def _read_smc(bars):
    try:
        res = detect_smc(bars, symbol=PAIR, timeframe="H4")
        return {
            "structure": res.structure.value,
            "order_block_side": res.order_block_side.value,
            "fvg_side": res.fvg_side.value,
            "in_fvg": res.in_fvg,
            "in_order_block": res.in_order_block,
        }
    except Exception as e:
        return {"error": str(e)}


def _read_liquidity(bars):
    try:
        lm = get_liquidity_map(PAIR, "H4", bars, current_price=bars[-1]["close"])
        zones = lm.as_dict() if hasattr(lm, "as_dict") else {}
        return zones
    except Exception as e:
        return {"error": str(e)}


def _read_fatman():
    try:
        st = get_fatman_live(PAIR, "H4", db_path=str(DB))
        return {"gbp": round(st.base_score, 1), "usd": round(st.quote_score, 1),
                "momentum": st.momentum.value, "gbp_rank": st.base_rank}
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=== LECTURE LIQUIDITÉ / SWEEP GBPUSD (SMC + ICT + Fatman) ===")
    out = {"pair": PAIR, "ts": dt.datetime.now(dt.UTC).isoformat(), "audit": {"r10": "read only"}}
    for tf in ("H4", "H1", "M30"):
        bars = _load_bars(tf)
        sweep = _detect_sweep(bars)
        smc = _read_smc(bars)
        liq = _read_liquidity(bars)
        fat = _read_fatman() if tf == "H4" else None
        out[tf] = {"sweep": sweep, "smc": smc, "liquidity": liq, "fatman": fat}
        print(f"\n[{tf}]")
        print(f"  SWEEP: {sweep}")
        print(f"  SMC: {smc}")
        # liquidité résumée
        if isinstance(liq, dict) and "zones" in liq:
            n = len(liq["zones"])
            print(f"  Liquidité: {n} zones")
        elif isinstance(liq, dict) and "error" not in liq:
            print(f"  Liquidité: {list(liq.keys())[:5]}")

    # Verdict combiné
    verdict = _verdict(out)
    out["verdict"] = verdict
    print(f"\n=== VERDICT GBPUSD (sweep) ===\n{json.dumps(verdict, indent=1, ensure_ascii=False)}")

    rep = ROOT / "reports" / f"v10_liquidity_sweep_{dt.date.today().isoformat()}.json"
    rep.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport : {rep}")


def _verdict(out):
    reasons = []
    score = 0
    for tf in ("H4", "H1", "M30"):
        sweep = out.get(tf, {}).get("sweep")
        if sweep:
            score += 2
            reasons.append(f"[{tf}] {sweep['reason']}")
        smc = out.get(tf, {}).get("smc", {})
        if smc.get("structure") in ("MSS_BEAR", "MSS_BULL"):
            score += 1
            reasons.append(f"[{tf}] MSS ({smc['structure']}) — shift de structure")
    fat = out.get("H4", {}).get("fatman", {})
    if fat.get("gbp", 0) >= 65:
        score += 1
        reasons.append(f"Fatman GBP {fat.get('gbp')} (très fort)")
    action = "SWEEP DÉTECTÉ — retournement probable" if score >= 2 else ("WATCH" if score >= 1 else "NEUTRAL")
    return {"action": action, "score": score, "reasons": reasons,
            "note": "Lecture R10. Un sweep = stops pris, retournement probable. Confirmer par MSS/CHoCH avant action."}


if __name__ == "__main__":
    main()
