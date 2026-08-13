"""Edge OVERLAP — runner SHADOW paper (R2 additif, 0 core modifié).

Émet des signaux shadow sur l'edge découvert (11/08, freestyle) :
  SESSION OVERLAP (12-16 UTC) + |delta_forces| >= 25 → BUY si delta>0, SELL sinon
  Paires porteuses : EURUSD, USDCHF, AUDUSD.

CONFIG OPTIMISÉE (benchmark 13/08, scripts/v10_edge_overlap_benchmark.py) :
  delta_min 15 → 25 (élimine le bucket 20-25 perdant : WR 46%, PnL négatif)
  TP=2xATR, SL=1xATR (payoff asymétrique — améliore Sharpe 4.4 → 5.2)
  hold max 4 barres M15
  Résultat : n=270 WR 59.3% PnL +540.8 pips DD 35.9 (vs 402 trades +349.5 DD 53)
  Robuste : 3/3 paires positives (EURUSD +132.7, USDCHF +258.3, AUDUSD +149.8)

FILTRE CINÉMATIQUE (benchmark 13/08, scripts/v10_edge_overlap_cinematics_benchmark.py) :
  Søn : "le cœur de la lecture du marché est dans l'interprétation de la
  cinématique". La courbe de force (pics, exhaustion, divergence) filtre les
  faux signaux des pics épuisés :
  - BLOCK si EXHAUSTION : pic de force récent puis retombée (épuisement)
  - BLOCK si DIVERGENCE : force décline pendant que le prix pousse (piège)
  Résultat : WR 60.4% → 62.8%, Sharpe 5.4 → 6.0, PnL/trade 2.05 → 2.48
  (45% des signaux bloqués = faux signaux éliminés, qualité prime)

Chaque tick : si la barre M15 fermée satisfait la règle, que la cinématique
ne bloque pas, ET qu'aucun trade shadow n'est déjà ouvert sur cette paire,
on enregistre un trade shadow (entry = close).
Résolution : TP=2xATR, SL=1xATR, hold max 4 barres M15.
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
DELTA_MIN = 25.0  # optimisé 13/08 (benchmark) : 15 → 25
TP_RATIO = 2.0    # optimisé 13/08 : TP=2xATR (payoff asymétrique)
SL_RATIO = 1.0    # optimisé 13/08 : SL=1xATR
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
    """Résout le trade shadow : TP=TP_RATIO×ATR, SL=SL_RATIO×ATR, hold max HOLD_MAX.

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
    tp, sl = atr_pip * TP_RATIO, atr_pip * SL_RATIO
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


def _cinematics_block(pair, bars, i):
    """Filtre cinématique (Søn) : BLOCK si exhaustion/divergence contre la direction.

    Analyse la courbe de force (delta_forces) sur les 60 dernières barres M15
    et bloque le signal si :
      - EXHAUSTION : pic de force récent puis retombée (épuisement)
      - DIVERGENCE : force décline pendant que le prix pousse (piège)
    Retourne (blocked: bool, reasons: list).
    """
    try:
        from core.v10.v10_cinematics import analyze_series, cinematics_verdict
        base, quote = pair[:3], pair[3:6]
        forces, prices = [], []
        for j in range(max(0, i - 60), i + 1):
            b = bars[j]
            forces.append(float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0)))
            prices.append(float(b["close"]))
        pip = 0.01 if pair.endswith("JPY") else 0.0001
        ana = analyze_series(forces, prices, label=f"{pair} M15", pip_size=pip)
        sig = _signal_index(pair, bars, i)
        direction = sig["direction"] if sig else "BUY"
        verdict = cinematics_verdict(ana, direction)
        return verdict["action"] == "BLOCK", verdict["reasons"]
    except Exception:
        return False, []  # R6 fail-open : cinématique indisponible → laisse passer


# ── Score de confluence multi-TF (Søn 13/08 — Pilier 2 imbrication) ─────────
# Cache des barres par (pair, tf) pour éviter de recharger la DB à chaque scan.
_TF_CACHE: dict = {}


def _load_tf_cached(pair: str, tf: str, limit: int = 2000):
    key = (pair, tf)
    if key not in _TF_CACHE:
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
        _TF_CACHE[key] = [dict(r) for r in reversed(rows)]
    return _TF_CACHE[key]


def _confluence_score(pair: str, bar_time: int, direction: str) -> dict:
    """Score de confluence [0-4] : M30 aligné + H1 aligné + M5 extension +
    cinématique M15 ALLOW. Sizing modulé 0.5→1.0. R6 fail-open → score 2/4.

    Søn : 'les confirmations de croisement sont retardées... imbrication.'
    Le H1 confirme APRÈS le mouvement — un conflit H1 réduit le sizing,
    il ne bloque pas (benchmark 13/08 : le sizing modulé protège les jours
    difficiles sans rater les trades à H1 en retard).
    """
    try:
        from core.v10.v10_confluence_tf import confluence_score as _cs
        return _cs(str(DB), pair, bar_time, direction,
                   bars_m15=_load_tf_cached(pair, "M15"),
                   bars_m5=_load_tf_cached(pair, "M5", 4000),
                   bars_m30=_load_tf_cached(pair, "M30"),
                   bars_h1=_load_tf_cached(pair, "H1"))
    except Exception:
        return {"score": 2, "max_score": 4, "sizing_multiplier": 0.75,
                "components": {"m30": None, "h1": None, "m5": None, "m15_cine": None},
                "detail": {}, "error": "fail_open"}


def _signal_for_bar(pair, bars):
    """Signal sur la DERNIÈRE barre (temps réel) + score de qualité.

    PARADIGME CHASSEUR (Søn 13/08) : le système ne bloque plus (BLOCK),
    il ÉVALUE (score 0-10) et agit selon la qualité.
      ≥ 7 → EXPLOITABLE (sizing renforcé)
      4-6 → SURVEILLER (sizing réduit)
      < 4 → BRUIT (ignorer)
    """
    if len(bars) < 60:
        return {"active": False, "reason": "insufficient_bars"}
    sig = _signal_index(pair, bars, len(bars) - 1)
    if sig is None:
        return {"active": False, "reason": "no_signal"}
    # Score de qualité institutionnel (remplace le BLOCK binaire)
    try:
        from core.v10.v10_quality_score import quality_score
        qs = quality_score(
            str(DB), pair, sig["bar_time"], sig["direction"],
            bars_m15=bars,
            bars_m5=_load_tf_cached(pair, "M5", 4000),
            bars_m30=_load_tf_cached(pair, "M30"),
            bars_h1=_load_tf_cached(pair, "H1"),
        )
        sig["quality_score"] = qs["score"]
        sig["quality_verdict"] = qs["verdict"]
        sig["sizing_multiplier"] = qs["sizing_multiplier"]
        sig["quality_detail"] = qs["components"]
        # BRUIT = pas actif (le système ignore)
        if qs["verdict"] == "BRUIT":
            return {"active": False, "reason": "quality_bruit",
                    "quality_score": qs["score"],
                    "quality_detail": qs["components"]}
    except Exception:
        sig["quality_score"] = 5  # R6 fail-open : neutre
        sig["quality_verdict"] = "SURVEILLER"
        sig["sizing_multiplier"] = 0.65
    return sig


def _replay(pair, limit=1500):
    """Valide l'edge sur l'historique : exécute la règle sur toutes les barres
    Overlap passées (filtre cinématique inclus) et résout chaque signal TP/SL.
    Retourne stats + trades."""
    bars = _load_bars(pair, limit)
    trades = []
    n_blocked = 0
    for i in range(60, len(bars) - HOLD_MAX - 1):
        sig = _signal_index(pair, bars, i)
        if sig is None:
            continue
        blocked, _ = _cinematics_block(pair, bars, i)
        if blocked:
            n_blocked += 1
            continue
        res = _resolve(sig, bars)
        # Score de confluence (sizing modulé — Søn 13/08)
        conf = _confluence_score(pair, sig["bar_time"], sig["direction"])
        trades.append({"pair": pair, "direction": sig["direction"],
                       "bar_time": sig["bar_time"], "delta": sig["delta"],
                       "atr_pip": sig["atr_pip"], "pnl_pips": res["pnl_pips"],
                       "pnl_module": round(res["pnl_pips"] * conf["sizing_multiplier"], 2),
                       "confluence_score": conf["score"],
                       "sizing_multiplier": conf["sizing_multiplier"],
                       "reason": res["reason"]})
    n = len(trades)
    if n == 0:
        return {"pair": pair, "n": 0, "n_blocked": n_blocked}
    wins = sum(1 for t in trades if t["pnl_pips"] > 0)
    pnl = sum(t["pnl_pips"] for t in trades)
    pnl_mod = sum(t["pnl_module"] for t in trades)
    return {"pair": pair, "n": n, "wr": round(wins / n, 4), "pnl_pips": round(pnl, 2),
            "pnl_module_pips": round(pnl_mod, 2), "n_blocked": n_blocked, "trades": trades}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Edge OVERLAP — shadow scan / replay")
    parser.add_argument("--replay", action="store_true", help="Valide l'edge sur l'historique")
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()

    if args.replay:
        print(f"[{_now()}] EDGE OVERLAP — REPLAY validation ({PAIRS_CARRY}, {TF}, delta≥{DELTA_MIN}, cinématique ON)")
        all_trades = []
        tot_n = tot_pnl = tot_pnl_mod = tot_w = tot_blocked = 0
        for pair in PAIRS_CARRY:
            r = _replay(pair, args.limit)
            if r["n"] == 0:
                print(f"  {pair}: 0 signal (bloqués={r.get('n_blocked', 0)})")
                continue
            tot_n += r["n"]
            tot_pnl += r["pnl_pips"]
            tot_pnl_mod += r.get("pnl_module_pips", 0.0)
            tot_w += r["wr"] * r["n"]
            tot_blocked += r.get("n_blocked", 0)
            all_trades += r["trades"]
            print(f"  {pair}: n={r['n']} WR={r['wr']} PnL={r['pnl_pips']:+.2f} "
                  f"PnL_module={r.get('pnl_module_pips', 0):+.2f} (bloqués={r.get('n_blocked', 0)})")
        if tot_n:
            print(f"\n  TOTAL: n={tot_n} WR={tot_w/tot_n:.4f} PnL={tot_pnl:+.2f} "
                  f"PnL_module={tot_pnl_mod:+.2f} (signaux bloqués par cinématique={tot_blocked})")
        out = ROOT / "reports" / f"v10_shadow_edge_replay_{dt.date.today().isoformat()}.json"
        out.write_text(json.dumps({"ts": _now(), "mode": "replay", "pairs": list(PAIRS_CARRY),
                                   "n_total": tot_n, "wr": round(tot_w/tot_n, 4) if tot_n else 0,
                                   "pnl_pips": round(tot_pnl, 2),
                                   "pnl_module_pips": round(tot_pnl_mod, 2),
                                   "n_blocked_cinematics": tot_blocked,
                                   "trades": all_trades,
                                   "audit": {"r10": "compute only, zero order real"}},
                                  indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"Rapport : {out}")
        return

    print(f"[{_now()}] EDGE OVERLAP — SHADOW scan (paires {PAIRS_CARRY}, {TF}, delta≥{DELTA_MIN}, cinématique ON)")
    state_path = ROOT / "reports" / "v10_shadow_trades_state.json"
    state = {"open": [], "history": []}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {"open": [], "history": []}

    # 1. Résoudre les trades ouverts (TP/SL/timeout) avec les barres actuelles
    resolved_now = []
    still_open = []
    for t in state.get("open", []):
        pair = t["pair"]
        bars = _load_bars(pair)
        # retrouver l'index du signal dans les barres (par bar_time)
        idx = None
        for j in range(len(bars) - 1, -1, -1):
            if int(bars[j]["bar_time"]) == t["bar_time"]:
                idx = j
                break
        if idx is None:
            still_open.append(t)  # barre pas encore dans l'historique chargé
            continue
        sig = {
            "pair": pair, "direction": t["direction"], "entry": t["entry"],
            "atr_pip": t["atr_pip"], "bar_time": t["bar_time"], "index": idx,
        }
        res = _resolve(sig, bars)
        if res["status"] == "error":
            still_open.append(t)
            continue
        closed = dict(t)
        closed.update({"pnl_pips": res["pnl_pips"], "reason": res["reason"],
                       "closed_at": _now()})
        resolved_now.append(closed)
        state["history"].append(closed)

    # 2. Scanner les nouvelles barres (signaux actifs)
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
        # pas de doublon : un seul trade ouvert par paire
        if any(o["pair"] == pair for o in still_open):
            results.append({"pair": pair, "signal": sig, "trade": "ALREADY_OPEN"})
            continue
        # Score de confluence (sizing modulé — Søn 13/08, Pilier 2)
        conf = _confluence_score(pair, sig["bar_time"], sig["direction"])
        trade = {
            "pair": pair, "direction": sig["direction"], "entry": sig["entry"],
            "atr_pip": sig["atr_pip"], "delta": sig["delta"],
            "bar_time": sig["bar_time"], "opened_at": _now(),
            "confluence_score": conf["score"],
            "sizing_multiplier": conf["sizing_multiplier"],
            "confluence_detail": conf.get("detail", {}),
        }
        still_open.append(trade)
        results.append({"pair": pair, "signal": sig, "trade": "OPEN",
                        "quality_score": sig.get("quality_score", 5),
                        "quality_verdict": sig.get("quality_verdict", "?"),
                        "sizing_multiplier": sig.get("sizing_multiplier", 0.65)})
        icon = {"EXPLOITABLE": "🟢", "SURVEILLER": "🟡", "BRUIT": "🔴"}.get(sig.get("quality_verdict", ""), "⚪")
        print(f"  {pair}: {sig['direction']} @ {sig['entry']:.5f} |delta|={sig['delta']:.2f} "
              f"ATR={sig['atr_pip']:.1f}p — {icon} {sig.get('quality_verdict','?')} "
              f"(qualité {sig.get('quality_score',5)}/10, sizing {sig.get('sizing_multiplier',0.65):.2f})")

    # 3. Persister l'état (open + history cumulée)
    state["open"] = still_open
    state["last_scan"] = _now()
    state_path.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")

    # 4. Track record cumulé (R9)
    hist = state["history"]
    n = len(hist)
    if n:
        wins = sum(1 for h in hist if h.get("pnl_pips", 0) > 0)
        pnl = sum(h.get("pnl_pips", 0) for h in hist)
        print(f"\n  TRACK RECORD SHADOW: {n} trades résolus, WR={wins/n:.4f}, PnL={pnl:+.2f} pips")
        print(f"  Résolus ce scan: {len(resolved_now)} (TP/SL/timeout)")
    else:
        print("\n  TRACK RECORD SHADOW: aucun trade résolu pour l'instant")

    out = ROOT / "reports" / f"v10_shadow_edge_overlap_{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps({
        "ts": _now(), "scan": results, "pairs": list(PAIRS_CARRY), "tf": TF,
        "delta_min": DELTA_MIN,
        "track_record": {"n_resolved": n, "n_open": len(still_open),
                         "wr": round(wins / n, 4) if n else 0.0,
                         "pnl_pips": round(pnl, 2) if n else 0.0},
        "audit": {"r10": "compute only, zero order real"},
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nRapport : {out}")


if __name__ == "__main__":
    main()
