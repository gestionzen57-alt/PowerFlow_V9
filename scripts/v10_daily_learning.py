"""v10_daily_learning.py — Apprentissage quotidien autonome (Hermes, 11/08).

"Chaque jour est unique. Il n'y a pas de loi, mais une façon d'exploiter et
comprendre la réalité du marché." — Søn

Ce module ré-évalue l'edge OVERLAP contre les données RÉELLES du jour courant
(ou des N derniers jours), sans loi figée :
- charge les barres M15 live du jour
- rejoue l'edge (OVERLAP 12-16 UTC + |delta_forces|>=15) sur ces barres
- compare le WR/PnL du jour à la baseline historique (58.1%)
- DÉCIDE (pas une loi) : edge toujours valide / drift / à re-calibrer
- persiste un journal d'apprentissage quotidien (R9) pour construire un track
  record qui capte l'évolution du marché.

R10 : compute only. Zéro ordre. C'est la boucle d'apprentissage qui devient
exécution réelle dès qu'un compte est connecté.
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
PAIRS = ("EURUSD", "USDCHF", "AUDUSD")
TF = "M15"
DELTA_MIN = 25.0  # optimisé 13/08 (benchmark) : 15 → 25
TP_RATIO = 2.0    # optimisé 13/08 : TP=2xATR (payoff asymétrique)
SL_RATIO = 1.0    # optimisé 13/08 : SL=1xATR
HOLD_MAX = 4
SPREAD_PIP = 0.3
BASELINE_WR = 0.5926  # config optimisée (270 trades, WR 59.3%)
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _load_bars(pair, since_ts, warmup_days=5):
    """Charge les barres M15 depuis warmup_days avant since_ts (warmup ATR)."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, high, low, close, force_eur, force_usd, force_gbp, force_jpy, "
        "force_cad, force_chf, force_aud, force_nzd "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "AND bar_time>=? ORDER BY bar_time ASC",
        (pair, TF, since_ts - warmup_days * 86400),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _run_edge(bars, pair, since_ts):
    """Rejoue l'edge. Ne compte que les signaux avec bar_time>=since_ts
    (les barres plus anciennes servent de warmup ATR). Retourne (n, wins, pnl, trades)."""
    base, quote = pair[:3], pair[3:6]
    trades = []
    for i in range(60, len(bars) - HOLD_MAX - 1):
        cur = bars[i]
        if int(cur["bar_time"]) < since_ts:
            continue  # hors période d'apprentissage (warmup)
        h = dt.datetime.fromtimestamp(int(cur["bar_time"]), tz=dt.UTC).hour
        if not (12 <= h < 16):
            continue
        d = float(cur.get(f"force_{base.lower()}", 0)) - float(cur.get(f"force_{quote.lower()}", 0))
        if abs(d) < DELTA_MIN:
            continue
        entry = float(cur["close"])
        atr = sum(float(bars[j]["high"]) - float(bars[j]["low"]) for j in range(i - 15, i - 1)) / 14
        pip = 0.01 if pair.endswith("JPY") else 0.0001
        atr_pip = atr / pip if pip else 0
        m = 1 if d > 0 else -1
        pnl = 0.0
        tp, sl = atr_pip * TP_RATIO, atr_pip * SL_RATIO
        for j in range(i + 1, min(i + 1 + HOLD_MAX, len(bars))):
            hi, lo = float(bars[j]["high"]), float(bars[j]["low"])
            if m == 1:
                if hi >= entry + tp * pip:
                    pnl = tp - SPREAD_PIP
                    break
                if lo <= entry - sl * pip:
                    pnl = -sl - SPREAD_PIP
                    break
            else:
                if lo <= entry - tp * pip:
                    pnl = tp - SPREAD_PIP
                    break
                if hi >= entry + sl * pip:
                    pnl = -sl - SPREAD_PIP
                    break
        else:
            exit_p = float(bars[min(i + HOLD_MAX, len(bars) - 1)]["close"])
            pnl = (exit_p - entry) * m / pip - SPREAD_PIP
        trades.append({"pair": pair, "direction": "BUY" if d > 0 else "SELL",
                       "delta": round(d, 2), "pnl_pips": round(pnl, 2),
                       "bar_time": int(cur["bar_time"])})
    n = len(trades)
    if n == 0:
        return n, 0, 0.0, []
    wins = sum(1 for t in trades if t["pnl_pips"] > 0)
    pnl = sum(t["pnl_pips"] for t in trades)
    return n, wins, pnl, trades


def _decision(n, wr, pnl, day_label):
    """DÉCISION adaptative (pas une loi fixe)."""
    if n < 5:
        return {"verdict": "insufficient_data", "note": f"trop peu de signaux ({n}) — pas de conclusion fiable"}
    if wr >= 0.54:
        return {"verdict": "edge_confirmed", "note": f"WR {wr:.3f} >= 0.54, edge OVERLAP valide sur {day_label}"}
    if 0.50 <= wr < 0.54 and pnl > 0:
        return {"verdict": "edge_marginal", "note": f"WR {wr:.3f} marginal mais PnL positif ({pnl:+.1f}p) — à surveiller"}
    return {"verdict": "edge_drift", "note": f"WR {wr:.3f} < 0.50 / PnL {pnl:+.1f}p — drift possible, re-calibrer les seuils"}


def main():
    days = 1
    today = dt.date.today()
    since = dt.datetime(today.year, today.month, today.day, 0, 0, tzinfo=dt.UTC)
    since_ts = int(since.timestamp())
    print(f"[{_now()}] APPRENTISSAGE QUOTIDIEN — edge OVERLAP sur {days} jour(s) ({today.isoformat()})")

    all_trades = []
    tot_n = tot_w = tot_pnl = 0
    per_pair = {}
    for pair in PAIRS:
        bars = _load_bars(pair, since_ts)
        n, wins, pnl, trades = _run_edge(bars, pair, since_ts)
        per_pair[pair] = {"n": n, "wins": wins, "pnl_pips": round(pnl, 2), "wr": round(wins / n, 4) if n else 0.0}
        tot_n += n
        tot_w += wins
        tot_pnl += pnl
        all_trades += trades
        print(f"  {pair}: n={n} WR={per_pair[pair]['wr']} PnL={pnl:+.2f}")

    wr = tot_w / tot_n if tot_n else 0.0
    dec = _decision(tot_n, wr, tot_pnl, today.isoformat())
    print(f"\n  TOTAL: n={tot_n} WR={wr:.4f} PnL={tot_pnl:+.2f}")
    print(f"  VERDICT: {dec['verdict']} — {dec['note']}")
    print(f"  Baseline historique: WR {BASELINE_WR} (382 trades)")

    journal = ROOT / "reports" / "v10_daily_learning.json"
    # journal cumulatif — une entrée par jour (dédup : écrase le même jour)
    hist = []
    if journal.exists():
        try:
            hist = json.load(open(journal, encoding="utf-8")).get("history", [])
        except Exception:
            hist = []
    entry = {
        "date": today.isoformat(),
        "generated_at": _now(),
        "n_trades": tot_n, "wr": round(wr, 4), "pnl_pips": round(tot_pnl, 2),
        "per_pair": per_pair, "decision": dec, "trades": all_trades,
        "baseline_wr": BASELINE_WR,
        "audit": {"r10": "compute only, zero order real", "method": "daily re-eval, no fixed law"},
    }
    # remplacer l'entrée du même jour s'il y en a une
    hist = [h for h in hist if h.get("date") != today.isoformat()]
    hist.append(entry)
    journal.write_text(json.dumps({"history": hist[-90:]}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nJournal d'apprentissage : {journal} ({len(hist)} jour(s) uniques cumulés)")


if __name__ == "__main__":
    main()
