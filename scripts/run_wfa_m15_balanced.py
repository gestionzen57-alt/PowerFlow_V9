"""V10 Walk-Forward M15 équilibré par nombre de trades (R2 additif, R10).

DOCTRINE_PERFORMANCE (673865c) — P1/P2/P3/P5/P6.

Contexte : WFA_MARGINAL (H3/H4) car fenêtres de tailles inégales (W3=10 trades,
W4=47 trades). H5 : fenêtres temporelles ÉQUILIBRÉES par nombre de trades
(cible 30-40 trades/fenêtre), pas par nombre de barres.

Algorithme (2 passes) :
1. Calibration : run complet sur 800 barres → collecte des timestamps des trades
   (BUY/SELL) triés chronologiquement.
2. Découpage : 5 fenêtres de ~35 trades chacune (bornes = timestamps des trades
   35, 70, 105, 140).
3. Validation : re-run par fenêtre (patch _load_bars bornes temporelles).

Verdict : WFA_PASS si 4/5 fenêtres WR ≥ 0.52.
Paires : EURUSD + USDCAD + USDCHF, M15, LONDON, limit=800.

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
OUT = "reports/wfa_m15_balanced_2026_08_10.json"
PAIRS = ["EURUSD", "USDCAD", "USDCHF"]
TF = "M15"
LIMIT = 800
N_WINDOWS = 5
TARGET_TRADES_PER_WINDOW = 35
WORKERS = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _patch_load_bars_full() -> None:
    """Patche _load_bars (forces natives) — run complet sans filtre temporel."""
    import core.v10.v10_replay_engine as eng

    def _load_bars_fixed(conn, symbol, tf, limit):
        rows = conn.execute(
            "SELECT bar_time AS timestamp, open, high, low, close, tick_volume, "
            "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd, "
            "direction, vitesse "
            "FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (symbol.upper(), tf.upper(), limit),
        ).fetchall()
        if not rows:
            return []
        bars = []
        for r in reversed(rows):
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


def _patch_load_bars_window(t0: int, t1: int) -> None:
    """Patche _load_bars pour ne retourner que les barres de la fenêtre [t0, t1]."""
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


def _collect_trade_timestamps() -> list:
    """Passe 1 : run complet, collecte les timestamps des trades triés."""
    from core.v10.v10_replay_engine import ReplayEngine
    _patch_load_bars_full()
    engine = ReplayEngine(db_path=REPLAY_DB, session="LONDON")
    report = engine.run_all(
        pairs=PAIRS, timeframes=[TF], limit=LIMIT,
        workers=WORKERS, run_c10_postprocess=True,
    )
    trades = []
    for x in getattr(report, "by_pair_tf", []) or []:
        for d in x.get("decisions", []):
            if d.get("action") in ("BUY", "SELL"):
                trades.append(int(d.get("timestamp", 0)))
    trades.sort()
    return trades


def _compute_fold_metrics(by_pair_tf: list) -> dict:
    pnls = []
    gw = gl = 0.0
    wins = losses = 0
    for x in by_pair_tf:
        for d in x.get("decisions", []):
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
        "n_trades": n, "wins": wins, "losses": losses,
        "wr": round(wr, 4), "pf": round(pf, 4),
        "sharpe": round(sharpe, 4), "pnl_pips": round(sum(pnls), 2),
    }


def main() -> None:
    print(f"[{_now_iso()}] WFA M15 équilibré — {PAIRS} × {TF}, {N_WINDOWS} fenêtres × ~{TARGET_TRADES_PER_WINDOW} trades")

    if not os.path.exists(REPLAY_DB):
        print(f"[FATAL] DB introuvable : {REPLAY_DB}")
        return

    try:
        from core.v10.v10_replay_engine import ReplayEngine
    except ImportError as e:
        print(f"[FATAL] ReplayEngine import: {e}")
        return

    # Passe 1 : calibration — collecte des timestamps des trades
    print("[CALIBRATION] run complet pour localiser les trades...")
    t0c = time.time()
    trade_ts = _collect_trade_timestamps()
    print(f"[CALIBRATION] {len(trade_ts)} trades localisés en {time.time()-t0c:.1f}s")

    if len(trade_ts) < N_WINDOWS * 20:
        print(f"[FATAL] Trop peu de trades ({len(trade_ts)}) pour {N_WINDOWS} fenêtres de ~35")
        return

    # Découpage en 5 fenêtres de ~35 trades
    bounds = []
    for w in range(N_WINDOWS):
        lo = w * TARGET_TRADES_PER_WINDOW
        hi = min((w + 1) * TARGET_TRADES_PER_WINDOW, len(trade_ts)) - 1
        t0 = trade_ts[lo]
        t1 = trade_ts[hi]
        bounds.append((t0, t1))
    print(f"Bornes fenêtres (par trades) : {bounds}")

    # Passe 2 : validation par fenêtre
    folds = []
    for w, (t0, t1) in enumerate(bounds, 1):
        _patch_load_bars_window(t0, t1)
        engine = ReplayEngine(db_path=REPLAY_DB, session="LONDON")
        t0m = time.time()
        try:
            report = engine.run_all(
                pairs=PAIRS, timeframes=[TF], limit=LIMIT,
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
        print(f"[FOLD {w}] {metrics['n_trades']}t | WR {metrics['wr']} | PF {metrics['pf']} | Sharpe {metrics['sharpe']}")

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

    # Verdict H5 : WFA_PASS si 4/5 fenêtres WR ≥ 0.52
    if n_wr_ge_052 >= 4:
        verdict = "WFA_PASS"
    elif wr_mean < 0.50:
        verdict = "WFA_FAIL"
    else:
        verdict = "WFA_MARGINAL"

    summary = {
        "ts": _now_iso(), "pairs": PAIRS, "tf": TF, "session": "LONDON",
        "n_windows": N_WINDOWS, "target_trades_per_window": TARGET_TRADES_PER_WINDOW,
        "calibration": {"n_trades_total": len(trade_ts), "bounds": bounds},
        "folds": folds,
        "verdict_global": {
            "wr_mean": round(wr_mean, 4), "wr_std": round(wr_std, 4),
            "pf_mean": round(pf_mean, 4), "sharpe_mean": round(sharpe_mean, 4),
            "n_valid_folds": len(valid_folds),
            "n_folds_wr_ge_052": n_wr_ge_052,
            "verdict": verdict,
        },
        "mode": "WALK_FORWARD_BALANCED", "r10": "zero order real",
    }
    audit = {
        "wr_mean": round(wr_mean, 4), "wr_std": round(wr_std, 4),
        "n_folds": len(valid_folds), "n_trades_total": sum(f.get("n_trades", 0) for f in valid_folds),
        "n_folds_wr_ge_052": n_wr_ge_052, "verdict": verdict,
    }
    audit["all_ok"] = n_wr_ge_052 >= 4
    summary["audit"] = audit

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n=== WFA ÉQUILIBRÉ RÉSULTAT GLOBAL ===")
    print(f"WR moyen: {wr_mean:.4f} ± {wr_std:.4f} | PF: {pf_mean:.4f} | Sharpe: {sharpe_mean:.4f}")
    print(f"Fenêtres WR≥0.52: {n_wr_ge_052}/{len(valid_folds)}")
    print(f"Verdict: {verdict}")
    print("\n=== AUTO-AUDIT P5 ===")
    for k, v in audit.items():
        print(f"  {k}: {v}")
    print(f"\nRapport : {OUT}")


if __name__ == "__main__":
    main()
