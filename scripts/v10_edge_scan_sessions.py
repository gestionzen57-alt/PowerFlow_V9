"""V10 Edge Scan Multi-Fenêtres — couche EXPLORATION (Option C).

Implémente la couche exploration de DECISION_OVERLAP_VS_SCAN_LARGE.md :
le scan large continue en SHADOW permanent pour détecter de NOUVEAUX edges,
mais ne produit JAMAIS de signal exécutable (exploration_only).

Méthode : pour chaque (session, paire, TF), rejoue la règle
"|delta_forces|≥seuil → BUY/SELL" avec TP=2xATR, SL=1xATR, hold=4
(config optimisée edge OVERLAP) et mesure WR/PnL/Sharpe.

Sessions :
  ASIE    21-02 UTC
  LONDON  07-12 UTC
  OVERLAP 12-16 UTC  (edge prouvé — baseline de référence)
  NY      13-20 UTC

Un nouveau edge est candidat si : n≥30, WR≥54%, PnL>0, Sharpe≥0.5 (annualisé).
Il passe ensuite la gate R10 complète (v10_edge_overlap_gate.py) avant toute
exécution. R10 : compute only, zéro ordre réel.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "v9_forces.db"
PAIRS = ("EURUSD", "USDCHF", "AUDUSD", "GBPUSD", "USDJPY", "USDCAD")
TFS = ("M15", "M30", "H1")
CUR = ("EUR", "USD", "GBP", "JPY", "CAD", "CHF", "AUD", "NZD")
SPREAD_PIP = 0.3
TP_RATIO, SL_RATIO, HOLD_MAX = 2.0, 1.0, 4

SESSIONS = {
    "ASIE":    (21, 2),    # 21:00-02:00 (chevauche minuit)
    "LONDON":  (7, 12),
    "OVERLAP": (12, 16),
    "NY":      (13, 20),
}

# Seuils candidat edge (alignés gate R10)
CAND_WR = 0.54
CAND_SHARPE = 0.5
CAND_MIN_N = 30


def _sharpe(pnls: list) -> float:
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return 0.0
    return mean / sd * math.sqrt(252)


def _in_session(hour: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end  # chevauchement minuit (ASIE)


def _load_bars(pair: str, tf: str, limit: int = 1500):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, force_eur, force_usd, force_gbp, "
        "force_jpy, force_cad, force_chf, force_aud, force_nzd "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (pair, tf, limit),
    ).fetchall()
    con.close()
    return [dict(r) for r in reversed(rows)]


def _delta(b: dict, pair: str) -> float:
    base, quote = pair[:3], pair[3:6]
    return float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0))


def _replay_session(bars, pair, session, delta_min):
    """Rejoue la règle delta sur une session. Retourne trades."""
    start, end = SESSIONS[session]
    trades = []
    for i in range(60, len(bars) - HOLD_MAX - 1):
        cur = bars[i]
        h = dt.datetime.fromtimestamp(int(cur["bar_time"]), tz=dt.UTC).hour
        if not _in_session(h, start, end):
            continue
        d = _delta(cur, pair)
        if abs(d) < delta_min:
            continue
        entry = float(cur["close"])
        atr = sum(float(bars[j]["high"]) - float(bars[j]["low"]) for j in range(i - 15, i - 1)) / 14
        pip = 0.01 if pair.endswith("JPY") else 0.0001
        atr_pip = atr / pip if pip else 0
        if atr_pip <= 0:
            continue
        m = 1 if d > 0 else -1
        tp, sl = atr_pip * TP_RATIO, atr_pip * SL_RATIO
        pnl = 0.0
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
    return trades


def main():
    print(f"[{dt.datetime.now(dt.UTC).isoformat()}] EDGE SCAN MULTI-FENÊTRES (exploration)")
    print(f"Config: TP={TP_RATIO}xATR SL={SL_RATIO}xATR hold={HOLD_MAX} spread={SPREAD_PIP}p")
    print("=" * 110)

    bars_cache = {}
    results = []
    for session in SESSIONS:
        for pair in PAIRS:
            for tf in TFS:
                key = (pair, tf)
                if key not in bars_cache:
                    bars_cache[key] = _load_bars(pair, tf)
                bars = bars_cache[key]
                if len(bars) < 100:
                    continue
                trades = _replay_session(bars, pair, session, delta_min=25.0)
                n = len(trades)
                if n < 20:
                    continue
                pnls = [t["pnl_pips"] for t in trades]
                wins = sum(1 for p in pnls if p > 0)
                wr = wins / n
                pnl = sum(pnls)
                sharpe = _sharpe(pnls)
                results.append({
                    "session": session, "pair": pair, "tf": tf, "n": n,
                    "wr": round(wr, 4), "pnl_pips": round(pnl, 2),
                    "sharpe": round(sharpe, 3),
                })

    # Tri : OVERLAP d'abord (référence), puis par Sharpe
    results.sort(key=lambda r: (r["session"] != "OVERLAP", -r["sharpe"]))

    print(f"\n{'session':>8} {'pair':>7} {'tf':>4} {'n':>5} {'WR':>7} {'PnL':>9} {'Sharpe':>8}")
    print("-" * 110)
    for r in results:
        mark = " ⭐" if (r["wr"] >= CAND_WR and r["sharpe"] >= CAND_SHARPE
                         and r["n"] >= CAND_MIN_N and r["session"] != "OVERLAP") else ""
        print(f"{r['session']:>8} {r['pair']:>7} {r['tf']:>4} {r['n']:>5} "
              f"{r['wr']:>7.4f} {r['pnl_pips']:>9.2f} {r['sharpe']:>8.3f}{mark}")

    # Candidats nouveaux edges (hors OVERLAP)
    print("\n=== CANDIDATS NOUVEAUX EDGES (hors OVERLAP, WR≥54% + Sharpe≥0.5 + n≥30) ===")
    candidates = [r for r in results if r["session"] != "OVERLAP"
                  and r["wr"] >= CAND_WR and r["sharpe"] >= CAND_SHARPE
                  and r["n"] >= CAND_MIN_N]
    if candidates:
        for r in candidates:
            print(f"  ⭐ {r['session']} {r['pair']} {r['tf']} → n={r['n']} "
                  f"WR={r['wr']:.4f} PnL={r['pnl_pips']:.2f} Sharpe={r['sharpe']:.3f}")
        print("\n  → Passer ces candidats par la gate R10 complète avant toute exécution.")
    else:
        print("  Aucun candidat — l'edge OVERLAP reste le seul edge prouvé.")

    # OVERLAP référence
    overlap = [r for r in results if r["session"] == "OVERLAP"]
    if overlap:
        best = max(overlap, key=lambda r: r["sharpe"])
        print(f"\n  OVERLAP référence : {best['pair']} {best['tf']} → n={best['n']} "
              f"WR={best['wr']:.4f} PnL={best['pnl_pips']:.2f} Sharpe={best['sharpe']:.3f}")

    out = ROOT / "reports" / f"v10_edge_scan_sessions_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps({
        "ts": dt.datetime.now(dt.UTC).isoformat(),
        "config": {"tp_ratio": TP_RATIO, "sl_ratio": SL_RATIO, "hold": HOLD_MAX,
                   "spread_pip": SPREAD_PIP, "delta_min": 25.0},
        "sessions": SESSIONS,
        "results": results,
        "candidates": candidates,
        "audit": {"r9": "point_in_time strict, TP/SL réels",
                  "r10": "compute only, zero order real — exploration_only"},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport: {out}")


if __name__ == "__main__":
    main()