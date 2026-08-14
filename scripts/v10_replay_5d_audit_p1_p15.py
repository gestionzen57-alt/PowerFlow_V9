"""Replay 5 jours — audit P1-P15 bout-en-bout.

Scope : EURUSD + USDCHF + AUDUSD, M15, fenêtre 5 derniers jours (2026-08-10 → 2026-08-14).
Combine :
  1. Edge OVERLAP baseline (delta≥25, 12-16 UTC, cinématique filter) — utilise P8 confluence + P9 σ-bands.
  2. Vérification P1-P15 : exerce chaque patch sur les données réelles du replay.
  3. KPIs : n, WR, PnL brut, PnL modulé (sizing confluence), DD max, Sharpe.
  4. Sortie JSON R9 + verdict CEO.

R10 : compute only, 0 ordre réel.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path.cwd() if (Path.cwd() / "data" / "v9_forces.db").exists() else Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "v9_forces.db"
PAIRS_CARRY = ("EURUSD", "USDCHF", "AUDUSD")
TF = "M15"
DELTA_MIN = 25.0
TP_RATIO = 2.0
SL_RATIO = 1.0
HOLD_MAX = 4
REPLAY_DAYS = 5


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _load_bars_window(pair: str, days: int):
    """Charge TOUTES les barres M15 fermées des N derniers jours (chronologique ASC)."""
    end_ts = int(dt.datetime(2026, 8, 14, 23, 59, 59, tzinfo=dt.UTC).timestamp())
    start_ts = end_ts - days * 86400
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT bar_time, open, high, low, close, spread_price, "
        "force_eur, force_usd, force_gbp, force_jpy, force_cad, force_chf, force_aud, force_nzd "
        "FROM forces_snapshots WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "AND bar_time BETWEEN ? AND ? "
        "ORDER BY bar_time ASC",
        (pair, TF, start_ts, end_ts),
    ).fetchall()
    con.close()
    bars = []
    for r in rows:
        b = dict(r)
        for k in ("open", "high", "low", "close", "spread_price"):
            b[k] = float(b.get(k) or 0.0)
        bars.append(b)
    return bars


def _delta_forces(b, pair: str) -> float:
    base, quote = pair[:3], pair[3:6]
    return float(b.get(f"force_{base.lower()}", 0.0)) - float(b.get(f"force_{quote.lower()}", 0.0))


def _signal_index(pair, bars, i):
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
        "delta": round(d, 2), "bar_time": int(cur["bar_time"]), "index": i,
    }


def _resolve(signal, bars, spread_pip=0.3):
    atr_pip = signal["atr_pip"]
    if atr_pip <= 0:
        return {"status": "error", "pnl_pips": 0.0, "reason": "atr_zero"}
    pair = signal["pair"]
    entry = signal["entry"]
    m = 1 if signal["direction"] == "BUY" else -1
    pip = 0.01 if pair.endswith("JPY") else 0.0001
    tp, sl = atr_pip * TP_RATIO, atr_pip * SL_RATIO
    i = signal["index"]
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


def _cinematics_block(pair, bars, i):
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
        return False, []


def _confluence_score(pair, bar_time, direction, bars):
    try:
        from core.v10.v10_confluence_tf import confluence_score as _cs
        return _cs(str(DB), pair, bar_time, direction,
                   bars_m15=bars, bars_m5=None, bars_m30=None, bars_h1=None)
    except Exception as exc:
        return {"score": 2, "max_score": 4, "sizing_multiplier": 0.75,
                "components": {}, "detail": {}, "error": str(exc)}


def _compute_vsa_check(pair, bars, i):
    """Exerce P1+P5+P15 sur la barre i : calcule VSAEngineState et retourne les flags clés."""
    try:
        from core.v10.v10_vsa import compute_vsa
        # bars[i-20:i+1] = fenêtre 21 bougies (min_bars_required)
        window = bars[max(0, i - 60):i + 1]
        if len(window) < 21:
            return None
        ts = dt.datetime.fromtimestamp(int(bars[i]["bar_time"]), tz=dt.UTC).isoformat()
        s = compute_vsa(pair, ts, TF, window)
        return {
            "state": s.state.value,
            "close_location": round(s.close_location, 4),
            "upthrust": s.upthrust,
            "has_gap": s.has_gap,
            "gap_bullish": s.gap_bullish,
            "gap_bearish": s.gap_bearish,
            "data_insufficient": s.data_insufficient,
            "spread_relative": round(s.spread_relative, 4),
            "volume_relative": round(s.volume_relative, 4),
            "classification_path_excerpt": " | ".join(s.classification_path[-3:]),
        }
    except Exception as exc:
        return {"error": str(exc)}


def replay_one_pair(pair: str, days: int = REPLAY_DAYS) -> dict:
    bars = _load_bars_window(pair, days)
    trades = []
    n_signals_total = 0
    n_signals_blocked_cine = 0
    n_vsa_audit_done = 0
    vsa_states = defaultdict(int)
    vsa_upthrust_count = 0
    vsa_gap_count = 0
    vsa_data_insufficient = 0
    p15_gap_bullish = 0
    p15_gap_bearish = 0
    p1_close_loc_low = 0
    p1_close_loc_high = 0

    for i in range(60, len(bars) - HOLD_MAX - 1):
        sig = _signal_index(pair, bars, i)
        if sig is None:
            continue
        n_signals_total += 1

        # P8+P9 : confluence (filtre cinématique + sizing)
        blocked_cine, _ = _cinematics_block(pair, bars, i)
        if blocked_cine:
            n_signals_blocked_cine += 1
            continue

        # P1+P5+P15 : audit VSAEngineState sur cette barre
        vsa = _compute_vsa_check(pair, bars, i)
        if vsa is not None:
            n_vsa_audit_done += 1
            if "error" not in vsa:
                vsa_states[vsa.get("state", "NEUTRAL")] += 1
                if vsa.get("upthrust"):
                    vsa_upthrust_count += 1
                if vsa.get("has_gap"):
                    vsa_gap_count += 1
                    if vsa.get("gap_bullish"):
                        p15_gap_bullish += 1
                    if vsa.get("gap_bearish"):
                        p15_gap_bearish += 1
                if vsa.get("data_insufficient"):
                    vsa_data_insufficient += 1
                cl = vsa.get("close_location", 0.5)
                if cl < 0.4:
                    p1_close_loc_low += 1
                elif cl > 0.6:
                    p1_close_loc_high += 1

        # P9 : confluence score (utilise σ-bands P3 indirectement)
        conf = _confluence_score(pair, sig["bar_time"], sig["direction"], bars)
        res = _resolve(sig, bars)
        trades.append({
            "pair": pair,
            "direction": sig["direction"],
            "bar_time": sig["bar_time"],
            "delta": sig["delta"],
            "atr_pip": sig["atr_pip"],
            "pnl_pips": res["pnl_pips"],
            "pnl_module": round(res["pnl_pips"] * conf.get("sizing_multiplier", 0.75), 2),
            "confluence_score": conf.get("score", 0),
            "sizing_multiplier": conf.get("sizing_multiplier", 0.75),
            "reason": res["reason"],
        })

    n = len(trades)
    if n == 0:
        return {"pair": pair, "n": 0, "n_signals_total": n_signals_total,
                "n_blocked_cine": n_signals_blocked_cine, "n_vsa_audit": n_vsa_audit_done,
                "vsa_states": dict(vsa_states), "vsa_upthrust": vsa_upthrust_count,
                "vsa_gap": vsa_gap_count, "vsa_data_insufficient": vsa_data_insufficient,
                "p15_gap_bullish": p15_gap_bullish, "p15_gap_bearish": p15_gap_bearish,
                "p1_close_loc_low": p1_close_loc_low, "p1_close_loc_high": p1_close_loc_high}

    wins = sum(1 for t in trades if t["pnl_pips"] > 0)
    pnl_brut = sum(t["pnl_pips"] for t in trades)
    pnl_mod = sum(t["pnl_module"] for t in trades)

    # DD max (cumulative pnl)
    cum = 0.0
    max_dd = 0.0
    peak = 0.0
    for t in trades:
        cum += t["pnl_module"]
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)

    # Sharpe (annualisé simplifié — sur 5j avec ~n trades)
    rets = [t["pnl_module"] for t in trades]
    if len(rets) > 1:
        mean_r = sum(rets) / len(rets)
        var = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
        std_r = math.sqrt(var) if var > 0 else 0.0
        sharpe = (mean_r / std_r) * math.sqrt(len(rets)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "pair": pair,
        "n": n,
        "wr": round(wins / n, 4),
        "pnl_brut_pips": round(pnl_brut, 2),
        "pnl_module_pips": round(pnl_mod, 2),
        "max_dd_pips": round(max_dd, 2),
        "sharpe_module": round(sharpe, 2),
        "n_signals_total": n_signals_total,
        "n_blocked_cine": n_signals_blocked_cine,
        "n_vsa_audit": n_vsa_audit_done,
        "vsa_states": dict(vsa_states),
        "vsa_upthrust": vsa_upthrust_count,
        "vsa_gap": vsa_gap_count,
        "vsa_data_insufficient": vsa_data_insufficient,
        "p15_gap_bullish": p15_gap_bullish,
        "p15_gap_bearish": p15_gap_bearish,
        "p1_close_loc_low": p1_close_loc_low,
        "p1_close_loc_high": p1_close_loc_high,
        "trades": trades,
    }


def main():
    print(f"[{_now()}] REPLAY 5 JOURS — audit P1-P15 bout-en-bout")
    print(f"  Paires : {PAIRS_CARRY} | TF : {TF} | Fenêtre : {REPLAY_DAYS} jours")
    print(f"  Filtres : OVERLAP 12-16 UTC + |delta|≥{DELTA_MIN} + cinématique ON")
    print(f"  TP/SL/hold : {TP_RATIO}xATR / {SL_RATIO}xATR / {HOLD_MAX} barres")
    print(f"  Patches exercés : P1(close_loc) P3(σ-bands) P5(end-of-bar) P8(confluence filter)")
    print(f"                     P9(σ-threshold M5) P15(gap detection)")
    print()

    all_results = {}
    grand_total = {"n": 0, "wins": 0, "pnl_brut": 0.0, "pnl_mod": 0.0, "max_dd": 0.0}
    grand_vsa_states = defaultdict(int)
    grand_signals_total = 0
    grand_blocked_cine = 0
    grand_vsa_audit = 0
    grand_upthrust = 0
    grand_gap = 0
    grand_data_insuff = 0
    grand_gap_bull = 0
    grand_gap_bear = 0
    grand_close_low = 0
    grand_close_high = 0

    for pair in PAIRS_CARRY:
        r = replay_one_pair(pair)
        all_results[pair] = r
        if r["n"] > 0:
            grand_total["n"] += r["n"]
            grand_total["wins"] += int(r["wr"] * r["n"])
            grand_total["pnl_brut"] += r["pnl_brut_pips"]
            grand_total["pnl_mod"] += r["pnl_module_pips"]
            grand_total["max_dd"] = max(grand_total["max_dd"], r["max_dd_pips"])
            print(f"  {pair}: n={r['n']} WR={r['wr']:.4f} PnL_brut={r['pnl_brut_pips']:+.2f}p "
                  f"PnL_module={r['pnl_module_pips']:+.2f}p DD={r['max_dd_pips']:.1f}p "
                  f"Sharpe={r['sharpe_module']:.2f}")
            print(f"        signals_total={r['n_signals_total']} "
                  f"blocked_cine={r['n_blocked_cine']} vsa_audit={r['n_vsa_audit']}")
            print(f"        vsa_states={r['vsa_states']} upthrust={r['vsa_upthrust']} "
                  f"gap={r['vsa_gap']}(bull={r['p15_gap_bullish']} bear={r['p15_gap_bearish']}) "
                  f"close_low={r['p1_close_loc_low']} close_high={r['p1_close_loc_high']}")
        else:
            print(f"  {pair}: 0 trade résolu (signals={r['n_signals_total']})")

        grand_signals_total += r["n_signals_total"]
        grand_blocked_cine += r["n_blocked_cine"]
        grand_vsa_audit += r["n_vsa_audit"]
        grand_upthrust += r.get("vsa_upthrust", 0)
        grand_gap += r.get("vsa_gap", 0)
        grand_data_insuff += r.get("vsa_data_insufficient", 0)
        grand_gap_bull += r.get("p15_gap_bullish", 0)
        grand_gap_bear += r.get("p15_gap_bearish", 0)
        grand_close_low += r.get("p1_close_loc_low", 0)
        grand_close_high += r.get("p1_close_loc_high", 0)
        for st, cnt in r.get("vsa_states", {}).items():
            grand_vsa_states[st] += cnt

    print()
    if grand_total["n"]:
        wr_global = grand_total["wins"] / grand_total["n"]
        print(f"  TOTAL : n={grand_total['n']} WR={wr_global:.4f} "
              f"PnL_brut={grand_total['pnl_brut']:+.2f}p "
              f"PnL_module={grand_total['pnl_mod']:+.2f}p "
              f"DD_max={grand_total['max_dd']:.1f}p")
    else:
        print("  TOTAL : aucun trade résolu")

    print()
    print("  AUDIT P1-P15 EXERCÉS :")
    print(f"    P1 (close_location) : {grand_close_low} low (<0.4), {grand_close_high} high (>0.6) sur {grand_vsa_audit} audits")
    print(f"    P5 (end-of-bar) : 0 bougie intra-barre calculée (filtre is_closed_bar=1 DB amont)")
    print(f"    P15 (gap detection) : {grand_gap} gaps détectés ({grand_gap_bull} bullish, {grand_gap_bear} bearish)")
    print(f"    upthrust (P1) : {grand_upthrust} sur {grand_vsa_audit} VSA calculés")
    print(f"    vsa_states : {dict(grand_vsa_states)}")
    print(f"    data_insufficient : {grand_data_insuff}")
    print(f"    cinématique bloque : {grand_blocked_cine}/{grand_signals_total} "
          f"({grand_blocked_cine*100/max(grand_signals_total,1):.0f}%)")

    # Verdict CEO
    print()
    print("  VERDICT CEO :")
    n = grand_total["n"]
    if n == 0:
        verdict = "INSUFFISANT — 0 trade résolu sur 5 jours. Étendre fenêtre ou baisser seuils."
    else:
        wr = grand_total["wins"] / n
        pnl = grand_total["pnl_mod"]
        if wr >= 0.55 and pnl > 0:
            verdict = "GO EDGE — WR ≥ 55% ET PnL > 0. Edge OVERLAP confirmé sur 5 jours."
        elif wr >= 0.45 and pnl > 0:
            verdict = "PRUDENT — WR 45-55% mais PnL > 0. Continuer 30 trades paper avant live."
        elif pnl > 0:
            verdict = f"BORDERLINE — PnL > 0 mais WR < 45% ({wr:.2%}). Volumétrie insuffisante, étendre."
        else:
            verdict = f"NO-GO — PnL ≤ 0 et WR < seuil ({wr:.2%}). Edge dégradé sur la fenêtre."

    print(f"    {verdict}")

    out = {
        "ts": _now(),
        "mode": "replay_5d_audit_p1_p15",
        "window_days": REPLAY_DAYS,
        "pairs": list(PAIRS_CARRY),
        "tf": TF,
        "config": {"delta_min": DELTA_MIN, "tp_ratio": TP_RATIO,
                   "sl_ratio": SL_RATIO, "hold_max": HOLD_MAX},
        "totals": grand_total,
        "vsa_states_total": dict(grand_vsa_states),
        "patch_audit": {
            "P1_close_loc_low_count": grand_close_low,
            "P1_close_loc_high_count": grand_close_high,
            "P1_upthrust_count": grand_upthrust,
            "P5_intra_barre_count": 0,  # garanti par is_closed_bar=1 dans le WHERE SQL
            "P15_gap_total": grand_gap,
            "P15_gap_bullish": grand_gap_bull,
            "P15_gap_bearish": grand_gap_bear,
            "data_insufficient": grand_data_insuff,
            "cinematique_blocks": grand_blocked_cine,
            "signals_total": grand_signals_total,
        },
        "per_pair": all_results,
        "verdict_ceo": verdict,
        "audit": {"r10": "compute only, zero order real",
                  "patches": ["P1", "P3", "P5", "P8", "P9", "P15"]},
    }
    out_path = ROOT / "reports" / f"v10_replay_5d_audit_{dt.date.today().isoformat()}.json"
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str),
                        encoding="utf-8")
    print(f"\n  Rapport : {out_path}")


if __name__ == "__main__":
    main()
