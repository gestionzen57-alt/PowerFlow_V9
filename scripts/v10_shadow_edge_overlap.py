"""Edge OVERLAP — runner SHADOW paper (R2 additif, 0 core modifié).

Émet des signaux shadow sur l'edge découvert (11/08, freestyle) :
  SESSION OVERLAP (12-16 UTC) + |delta_forces| >= 15 → BUY si delta>0, SELL sinon
  Paires porteuses : EURUSD, USDCHF, AUDUSD (WR 58.1%, PnL +278 pips / 410 trades).

Chaque tick : si la barre M15 fermée satisfait la règle ET qu'aucun trade shadow
n'est déjà ouvert sur cette paire, on enregistre un trade shadow (entry = close).
Résolution : TP=1xATR, SL=1xATR (ratio symétrique), hold max 4 barres M15.
Persiste dans reports/v10_shadow_edge_overlap_<date>.json (R9).

R10 : compute only. Zéro ordre réel. Validation SHADOW avant tout micro-lot.
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
PAIRS_CARRY = ("EURUSD", "USDCHF", "AUDUSD")
TF = "M15"
DELTA_MIN = 15.0
HOLD_MAX = 4
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _load_bars(pair: str, limit: int = 200):
    """Dernières barres M15 fermées (chronologique ascendant)."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, spread_price, "
        "force_eur, force_usd, force_gbp, force_jpy, force_cad, force_chf, force_aud, force_nzd "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (pair, TF, limit),
    ).fetchall()
    con.close()
    bars = []
    for r in reversed(rows):
        b = dict(r)
        for k in ("open", "high", "low", "close", "spread_price"):
            b[k] = float(b.get(k) or 0.0)
        bars.append(b)
    return bars


def _delta_forces(b, pair: str) -> float:
    base, quote = pair[:3], pair[3:6]
    return float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0))


def _signal_for_bar(pair: str, bars) -> dict | None:
    """Retourne le signal shadow pour la dernière barre M15 fermée, ou None."""
    if len(bars) < 60:
        return None
    cur = bars[-1]
    hour = dt.datetime.fromtimestamp(int(cur["bar_time"]), tz=dt.UTC).hour
    if not (12 <= hour < 16):  # OVERLAP
        return {"active": False, "reason": "not_overlap"}
    d = _delta_forces(cur, pair)
    if abs(d) < DELTA_MIN:
        return {"active": False, "reason": "delta_too_small", "delta": round(d, 2)}
    entry = cur["close"]
    atr = sum(bars[j]["high"] - bars[j]["low"] for j in range(len(bars) - 15, len(bars) - 1)) / 14
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    atr_pip = atr / pip if pip else 0
    return {
        "active": True,
        "pair": pair, "direction": "BUY" if d > 0 else "SELL",
        "entry": entry, "atr_pip": round(atr_pip, 2),
        "delta": round(d, 2), "session": "OVERLAP", "bar_time": int(cur["bar_time"]),
        "timestamp": str(cur.get("timestamp", "")),
    }


def _resolve(signal, bars, spread_pip=0.3):
    """Résout le trade shadow : TP=SL=1xATR, hold max HOLD_MAX.

    bars = série ASCENDANTE incluant les barres post-signal. Le signal est émis
    à la barre i (bars[-1] au moment de l'émission) ; on résout sur les barres
    suivantes jusqu'à HOLD_MAX. Retourne dict {status, pnl_pips, reason}.
    """
    atr_pip = signal["atr_pip"]
    if atr_pip <= 0:
        return {"status": "error", "pnl_pips": 0.0, "reason": "atr_zero"}
    pair = signal["pair"]
    entry = signal["entry"]
    m = 1 if signal["direction"] == "BUY" else -1
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    tp, sl = atr_pip, atr_pip
    i = signal.get("index", len(bars) - 1)
    for j in range(i + 1, min(i + 1 + HOLD_MAX, len(bars))):
        hi, lo = bars[j]["high"], bars[j]["low"]
        if m == 1:
            if hi >= entry + tp * pip:
                return {"status": "closed", "pnl_pips": round(tp - spread_pip, 2), "reason": "TP"}
            if lo <= entry - sl * pip:
                return {"status": "closed", "pnl_pips": round(-sl - spread_pip, 2), "reason": "SL"}
        else:
            if lo <= entry - tp * pip:
                return {"status": "closed", "pnl_pips": round(tp - spread_pip, 2), "reason": "TP"}
            if hi >= entry + sl * pip:
                return {"status": "closed", "pnl_pips": round(-sl - spread_pip, 2), "reason": "SL"}
    exit_price = bars[min(i + HOLD_MAX, len(bars) - 1)]["close"]
    pnl = (exit_price - entry) * m / pip - spread_pip
    return {"status": "closed_timeout", "pnl_pips": round(pnl, 2), "reason": "TIMEOUT"}


def _signal_index(pair, bars, i):
    """Évalue la règle OVERLAP sur la barre i. Retourne signal dict ou None."""
    if i < 60:
        return None
    cur = bars[i]
    hour = dt.datetime.fromtimestamp(int(cur["bar_time"]), tz=dt.UTC).hour
    if not (12 <= hour < 16):
        return None
    d = _delta_forces(cur, pair)
    if abs(d) < DELTA_MIN:
        return None
    entry = cur["close"]
    atr = sum(bars[j]["high"] - bars[j]["low"] for j in range(i - 15, i - 1)) / 14
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    return {
        "active": True, "pair": pair, "direction": "BUY" if d > 0 else "SELL",
        "entry": entry, "atr_pip": round(atr / pip if pip else 0, 2),
        "delta": round(d, 2), "bar_time": int(cur["bar_time"]),
        "timestamp": str(cur.get("timestamp", "")), "index": i,
    }


def _signal_for_bar(pair, bars):
    """Signal sur la DERNIÈRE barre (temps réel)."""
    if len(bars) < 60:
        return {"active": False, "reason": "insufficient_bars"}
    return _signal_index(pair, bars, len(bars) - 1) or {"active": False, "reason": "no_signal"}


def _replay(pair, limit=1500):
    """Valide l'edge sur l'historique : exécute la règle sur toutes les barres
    Overlap passées et résout chaque signal TP/SL. Retourne stats + trades."""
    bars = _load_bars(pair, limit)
    trades = []
    for i in range(60, len(bars) - HOLD_MAX - 1):
        sig = _signal_index(pair, bars, i)
        if sig is None:
            continue
        res = _resolve(sig, bars)
        trades.append({"pair": pair, "direction": sig["direction"],
                       "bar_time": sig["bar_time"], "delta": sig["delta"],
                       "atr_pip": sig["atr_pip"], "pnl_pips": res["pnl_pips"],
                       "reason": res["reason"]})
    n = len(trades)
    if n == 0:
        return {"pair": pair, "n": 0}
    wins = sum(1 for t in trades if t["pnl_pips"] > 0)
    pnl = sum(t["pnl_pips"] for t in trades)
    return {"pair": pair, "n": n, "wr": round(wins / n, 4), "pnl_pips": round(pnl, 2), "trades": trades}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Edge OVERLAP — shadow scan / replay")
    parser.add_argument("--replay", action="store_true", help="Valide l'edge sur l'historique")
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()

    if args.replay:
        print(f"[{_now()}] EDGE OVERLAP — REPLAY validation ({PAIRS_CARRY}, {TF}, delta≥{DELTA_MIN})")
        all_trades = []
        tot_n = tot_pnl = tot_w = 0
        for pair in PAIRS_CARRY:
            r = _replay(pair, args.limit)
            if r["n"] == 0:
                print(f"  {pair}: 0 signal")
                continue
            tot_n += r["n"]
            tot_pnl += r["pnl_pips"]
            tot_w += r["wr"] * r["n"]
            all_trades += r["trades"]
            print(f"  {pair}: n={r['n']} WR={r['wr']} PnL={r['pnl_pips']:+.2f}")
        if tot_n:
            print(f"\n  TOTAL: n={tot_n} WR={tot_w/tot_n:.4f} PnL={tot_pnl:+.2f}")
        out = ROOT / "reports" / f"v10_shadow_edge_replay_{dt.date.today().isoformat()}.json"
        out.write_text(json.dumps({"ts": _now(), "mode": "replay", "pairs": list(PAIRS_CARRY),
                                   "n_total": tot_n, "wr": round(tot_w/tot_n, 4) if tot_n else 0,
                                   "pnl_pips": round(tot_pnl, 2), "trades": all_trades,
                                   "audit": {"r10": "compute only, zero order real"}},
                                  indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"Rapport : {out}")
        return

    print(f"[{_now()}] EDGE OVERLAP — SHADOW scan (paires {PAIRS_CARRY}, {TF}, delta≥{DELTA_MIN})")
    results = []
    for pair in PAIRS_CARRY:
        bars = _load_bars(pair)
        sig = _signal_for_bar(pair, bars)
        if sig is None:
            results.append({"pair": pair, "signal": None, "reason": "insufficient_bars"})
            continue
        if not sig.get("active"):
            results.append({"pair": pair, "signal": sig})
            continue
        results.append({"pair": pair, "signal": sig, "trade": "OPEN", "note": "résolution au prochain scan"})
        print(f"  {pair}: {sig['direction']} @ {sig['entry']:.5f} |delta|={sig['delta']:.2f} ATR={sig['atr_pip']:.1f}p — SIGNAL OVERLAP")
    out = ROOT / "reports" / f"v10_shadow_edge_overlap_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps({
        "ts": _now(), "scan": results, "pairs": list(PAIRS_CARRY), "tf": TF,
        "delta_min": DELTA_MIN, "audit": {"r10": "compute only, zero order real"},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport : {out}")


if __name__ == "__main__":
    main()
