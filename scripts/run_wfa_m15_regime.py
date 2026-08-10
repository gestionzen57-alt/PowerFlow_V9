"""V10 Walk-Forward M15 + filtre régime HMM (R2 additif, R10).

DOCTRINE_PERFORMANCE (673865c) — P1/P2/P3/P5/P6.

Combine run_wfa_m15_10_08.py (5 fenêtres non-chevauchantes) + filtre régime
HMM (run_replay_m15_regime.py). H4 : valider hors-échantillon si le filtre
régime améliore la stabilité de l'edge.

Résultat attendu de H3 : le filtre régime a DÉGRADÉ le WR replay (55.13% vs
59.74%). Ce WFA confirme ou infirme la stabilité OOS du pipeline régime.

Verdict :
  - WFA_PASS si WR OOS moyen ≥ 0.52 sur ≥ 4/5 fenêtres
  - WFA_FAIL si WR OOS moyen < 0.50
R2 additif strict — zéro modification v10_replay_engine.py core.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone

REPLAY_DB = "C:/projet/V9/data/v9_forces.db"
OUT = "reports/wfa_m15_regime_2026_08_10.json"
PAIRS = ["EURUSD", "USDCAD", "USDCHF"]
TF = "M15"
N_WINDOWS = 5
WINDOW_BARS = 160
WORKERS = 2

ALLOWED_REGIMES = {"TRENDING_UP", "TRENDING_DOWN"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_window_bounds(db_path: str, pair: str, tf: str) -> list:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT DISTINCT bar_time FROM forces_snapshots "
        "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
        "ORDER BY bar_time DESC LIMIT ?",
        (pair.upper(), tf.upper(), N_WINDOWS * WINDOW_BARS),
    ).fetchall()
    conn.close()
    times = sorted(r["bar_time"] for r in rows)
    if len(times) < N_WINDOWS * WINDOW_BARS:
        return []
    bounds = []
    for w in range(N_WINDOWS):
        t0 = times[w * WINDOW_BARS]
        t1 = times[min((w + 1) * WINDOW_BARS, len(times)) - 1]
        bounds.append((t0, t1))
    return bounds


def _patch_window_regime(t0: int, t1: int) -> None:
    """Patche _load_bars (fenêtre [t0,t1] + forces natives) ET _decide_one
    (filtre régime HMM). Injection runtime — aucun fichier core modifié."""
    import core.v10.v10_replay_engine as eng

    def _load_bars_fixed(conn, symbol, tf, limit):
        rows = conn.execute(
            "SELECT bar_time AS timestamp, open, high, low, close, tick_volume, "
            "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd, "
            "direction, vitesse "
            "FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
            "AND bar_time BETWEEN ? AND ? ORDER BY bar_time ASC",
            (symbol.upper(), tf.upper(), t0, t1),
        ).fetchall()
        if not rows:
            return []
        bars = []
        for r in rows:
            b = dict(r)
            for k in ("open", "high", "low", "close"):
                b[k] = float(b.get(k) or 0.0)
            b["tick_volume"] = float(b.get("tick_volume") or 0.0)
            for c in ("force_usd", "force_gbp", "force_eur", "force_jpy",
                      "force_cad", "force_chf", "force_aud", "force_nzd"):
                b[c] = float(b.get(c) or 50.0)
            b["direction"] = b.get("direction", "neutre")
            b["vitesse"] = float(b.get("vitesse") or 0.0)
            bars.append(b)
        return bars

    eng._load_bars = _load_bars_fixed

    orig_decide_one = eng._decide_one

    def _decide_one_with_regime(pair, tf, tf_role, window, h4_bias,
                                fractal_conf, db_path, session, bayes_thresholds):
        try:
            from core.v10.v10_regime_hmm import detect_hmm_regime
            closes = [float(b.get("close", 0.0)) for b in window[-60:]]
            if len(closes) >= 30:
                rr = detect_hmm_regime(closes, symbol=pair, timestamp="")
                regime_name = rr.regime.name if hasattr(rr.regime, "name") else str(rr.regime)
                if regime_name not in ALLOWED_REGIMES:
                    return eng.DecisionRecord(
                        pair=pair, tf=tf, tf_role=tf_role, timestamp=str(window[-1].get("timestamp", "")),
                        action="HOLD", direction="", signal_level="NONE", pipeline="regime_filter",
                        held_reason=f"REGIME_{regime_name}",
                        vsa_ok=False, fractal_boost=0.0,
                        rl_boosted=False, pnl_pips=0.0, tp_pips=0.0, sl_pips=0.0, win=False,
                    )
        except Exception:
            pass
        return orig_decide_one(pair, tf, tf_role, window, h4_bias,
                               fractal_conf, db_path, session, bayes_thresholds)

    eng._decide_one = _decide_one_with_regime


def _compute_fold_metrics(by_pair_tf: list) -> dict:
    pnls = []
    gw = gl = 0.0
    wins = losses = 0
    n_filtered = 0
    for x in by_pair_tf:
        for d in x.get("decisions", []):
            if "REGIME_" in str(d.get("held_reason", "")):
                n_filtered += 1
                continue
            if d.get("action") not in ("BUY", "SELL"):
                continue
            pnl = float(d.get("pnl_pips", 0.0))
            pnls.append(pnl)
            if pnl > 0:
                gw += pnl
                wins += 1
            elif pnl < 0:
                gl += abs(pnl)
                losses += 1
    n = len(pnls)
    wr = wins / n if n else 0.0
    pf = gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0)
    avg = sum(pnls) / n if n else 0.0
    std = math.sqrt(sum((p - avg) ** 2 for p in pnls) / n) if n > 1 else 0.0
    sharpe = avg / std if std > 0 else 0.0
    return {
        "n_trades": n, "wins": wins, "losses": losses, "n_regime_filtered": n_filtered,
        "wr": round(wr, 4), "pf": round(pf, 4),
        "sharpe": round(sharpe, 4), "pnl_pips": round(sum(pnls), 2),
    }


def main() -> None:
    print(f"[{_now_iso()}] WFA M15 + régime — {PAIRS} × {TF}, {N_WINDOWS} fenêtres de {WINDOW_BARS} barres")

    if not os.path.exists(REPLAY_DB):
        print(f"[FATAL] DB introuvable : {REPLAY_DB}")
        return

    try:
        from core.v10.v10_replay_engine import ReplayEngine
    except ImportError as e:
        print(f"[FATAL] ReplayEngine import: {e}")
        return

    bounds = _get_window_bounds(REPLAY_DB, "EURUSD", TF)
    if not bounds:
        print(f"[FATAL] Moins de {N_WINDOWS * WINDOW_BARS} barres M15 EURUSD")
        return

    folds = []
    for w, (t0, t1) in enumerate(bounds, 1):
        _patch_window_regime(t0, t1)
        engine = ReplayEngine(db_path=REPLAY_DB, session="LONDON")
        t0m = time.time()
        try:
            report = engine.run_all(
                pairs=PAIRS, timeframes=[TF], limit=WINDOW_BARS,
                workers=WORKERS, run_c10_postprocess=True,
            )
        except Exception as e:
            folds.append({"window": w, "t0": t0, "t1": t1, "error": str(e),
                          "n_trades": 0, "wr": 0.0, "pf": 0.0, "sharpe": 0.0})
            continue
        metrics = _compute_fold_metrics(getattr(report, "by_pair_tf", []) or [])
        metrics["window"] = w
        metrics["t0"] = t0
        metrics["t1"] = t1
        metrics["elapsed_s"] = round(time.time() - t0m, 1)
        folds.append(metrics)
        print(f"[FOLD {w}] {metrics['n_trades']}t (filtrés {metrics['n_regime_filtered']}) | WR {metrics['wr']} | PF {metrics['pf']} | Sharpe {metrics['sharpe']}")

    valid_folds = [f for f in folds if f.get("n_trades", 0) >= 10]
    if not valid_folds:
        print("[FATAL] Aucune fenêtre valide (≥10 trades)")
        return
    wrs = [f["wr"] for f in valid_folds]
    wr_mean = sum(wrs) / len(wrs)
    wr_std = math.sqrt(sum((x - wr_mean) ** 2 for x in wrs) / len(wrs)) if len(wrs) > 1 else 0.0
    pf_mean = sum(f["pf"] for f in valid_folds) / len(valid_folds)
    sharpe_mean = sum(f["sharpe"] for f in valid_folds) / len(valid_folds)
    n_wr_ge_052 = sum(1 for f in valid_folds if f["wr"] >= 0.52)
    n_filtered_total = sum(f.get("n_regime_filtered", 0) for f in valid_folds)

    if wr_mean >= 0.52 and n_wr_ge_052 >= 4:
        verdict = "WFA_PASS"
    elif wr_mean < 0.50:
        verdict = "WFA_FAIL"
    else:
        verdict = "WFA_MARGINAL"

    summary = {
        "ts": _now_iso(), "pairs": PAIRS, "tf": TF, "session": "LONDON",
        "n_windows": N_WINDOWS, "window_bars": WINDOW_BARS,
        "regime_filter": {"allowed": sorted(ALLOWED_REGIMES)},
        "folds": folds,
        "verdict_global": {
            "wr_mean": round(wr_mean, 4), "wr_std": round(wr_std, 4),
            "pf_mean": round(pf_mean, 4), "sharpe_mean": round(sharpe_mean, 4),
            "n_valid_folds": len(valid_folds),
            "n_folds_wr_ge_052": n_wr_ge_052,
            "n_regime_filtered_total": n_filtered_total,
            "verdict": verdict,
        },
        "mode": "WALK_FORWARD_REGIME", "r10": "zero order real",
    }
    audit = {
        "wr_mean": round(wr_mean, 4), "wr_std": round(wr_std, 4),
        "n_folds": len(valid_folds), "n_trades_total": sum(f.get("n_trades", 0) for f in valid_folds),
        "n_regime_filtered_total": n_filtered_total, "verdict": verdict,
    }
    audit["all_ok"] = wr_mean >= 0.50
    summary["audit"] = audit

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n=== WFA RÉGIME RÉSULTAT GLOBAL ===")
    print(f"WR moyen: {wr_mean:.4f} ± {wr_std:.4f} | PF: {pf_mean:.4f} | Sharpe: {sharpe_mean:.4f}")
    print(f"Fenêtres WR≥0.52: {n_wr_ge_052}/{len(valid_folds)} | régime filtrés: {n_filtered_total}")
    print(f"Verdict: {verdict}")
    print("\n=== AUTO-AUDIT P5 ===")
    for k, v in audit.items():
        print(f"  {k}: {v}")
    print(f"\nRapport : {OUT}")


if __name__ == "__main__":
    main()
