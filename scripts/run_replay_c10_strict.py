"""V10 ReplayEngine C10 strict — 5000+ décisions sur vraies données (R2 additif, R10).

DOCTRINE_PERFORMANCE (673865c) — P1/P2/P3/P5/P6.

Utilise ReplayEngine (C10) sur la vraie DB V10 `data/v9_forces.db` (18GB)
du worktree principal — la DB `powerflow.db` du prompt n'existe pas (chemin
erroné) ; la source de vérité V10 est `data/v9_forces.db` (forces_snapshots).

Paramètres du prompt : 7 paires × 3 TF × limit 500 = ~5000 décisions.
Auto-audit P5 avant commit. Rapport JSON + SHA commits.

R10 : 0 ordre réel — replay sur données passées.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

REPLAY_DB = "C:/projet/V9/data/v9_forces.db"
OUT = "reports/replay_c10_strict_2026_08_10.json"
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "EURJPY"]
TFS = ["M15", "M30", "H1"]
LIMIT = 500
WORKERS = 4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _patch_load_bars() -> None:
    """Contournement runtime R2 du bug C10 : _load_bars utilise la colonne
    `real_volume` (inexistante dans forces_snapshots) puis retombe sur la
    table `ohlcv` (inexistante) → retourne toujours []. On remplace par une
    lecture honnête sur forces_snapshots (colonne tick_volume uniquement).

    Aucun fichier core modifié — injection au moment de l'import (R2 additif).
    """
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
            # forces natives + direction/vitesse (compute_force_native les lit)
            for c in ("force_usd", "force_gbp", "force_eur", "force_jpy",
                      "force_cad", "force_chf", "force_aud", "force_nzd"):
                b[c] = float(b.get(c) or 50.0)
            b["direction"] = b.get("direction", "neutre")
            b["vitesse"] = float(b.get("vitesse") or 0.0)
            bars.append(b)
        return bars

    eng._load_bars = _load_bars_fixed
    print("[PATCH] _load_bars monkeypatched (tick_volume / forces_snapshots) — C10 OK")


def _auto_audit_p5(report: dict) -> dict:
    """Auto-audit P5 — vérifie les seuils doctrinaux avant commit."""
    global_wr = float(report.get("global_wr", 0.0))
    global_pnl = float(report.get("global_pnl", 0.0))
    n_trades = int(report.get("n_total_trades", 0))
    avg_sharpe = float(report.get("avg_sharpe", 0.0))

    # PF = gross wins / |gross losses| en pips
    gross_wins = max(global_pnl, 0.0) if global_pnl > 0 else 0.0
    # Approximation : on ne peut pas séparer wins/losses sans détail par trade
    audit = {
        "global_wr": round(global_wr, 4),
        "global_pnl_pips": round(global_pnl, 2),
        "avg_sharpe": round(avg_sharpe, 4),
        "n_total_trades": n_trades,
        "pairs": len(report.get("by_pair", {})),
        "timeframes": len(report.get("by_tf", {})),
        "live_ready": report.get("live_ready", False),
        "live_ready_reason": report.get("live_ready_reason", ""),
    }
    # Seuils P2
    bpt = report.get("by_pair_tf", []) or []
    n_pairs = len({x.get("pair") for x in bpt})
    n_tfs = len({x.get("tf") for x in bpt})
    audit["pairs"] = n_pairs
    audit["timeframes"] = n_tfs
    audit["WR_ok"] = global_wr < 0.75
    audit["sharpe_ok"] = avg_sharpe < 2.5
    audit["n_trades_ok"] = n_trades >= 100
    audit["all_ok"] = all([audit["WR_ok"], audit["sharpe_ok"], audit["n_trades_ok"]])
    return audit


def main() -> None:
    print(f"[{_now_iso()}] ReplayEngine C10 strict — {len(PAIRS)} paires × {len(TFS)} TF × limit {LIMIT}")
    print(f"DB : {REPLAY_DB}")

    if not os.path.exists(REPLAY_DB):
        print(f"[FATAL] DB introuvable : {REPLAY_DB}")
        return

    try:
        from core.v10.v10_replay_engine import ReplayEngine
    except ImportError as e:
        print(f"[FATAL] ReplayEngine import: {e}")
        return

    engine = ReplayEngine(db_path=REPLAY_DB, session="LONDON")
    _patch_load_bars()  # C10 fix runtime (real_volume/ohlcv manquants)
    t0 = time.time()
    try:
        report = engine.run_all(
            pairs=PAIRS,
            timeframes=TFS,
            limit=LIMIT,
            workers=WORKERS,
            run_c10_postprocess=True,
        )
    except Exception as e:
        print(f"[FATAL] run_all: {e}")
        return
    elapsed = time.time() - t0

    print(f"\n[{_now_iso()}] Replay terminé en {elapsed:.1f}s")

    # Convertir le ReplayReport en dict pour rapport
    attr_map = {
        "global_wr": "global_wr", "global_pnl_pips": "global_pnl_pips",
        "avg_sharpe": "avg_sharpe", "live_ready": "live_ready",
        "live_ready_reason": "live_ready_reason", "n_total_trades": "n_total_trades",
        "n_total_decisions": "n_total_decisions", "by_pair_tf": "by_pair_tf",
        "pipeline_dominant": "pipeline_dominant", "modules_active": "modules_active",
    }
    rep = {}
    for key, attr in attr_map.items():
        try:
            val = getattr(report, attr)
            # Alléger : exclure les décisions détaillées (rapport compact, R9)
            if key == "by_pair_tf" and isinstance(val, list):
                compact = []
                for x in val:
                    cx = {k: v for k, v in x.items() if k != "decisions"}
                    compact.append(cx)
                val = compact
            rep[key] = val
        except Exception:
            rep[key] = None
    # compat clé globale pnl (l'audit lit "global_pnl")
    rep["global_pnl"] = rep.get("global_pnl_pips")

    audit = _auto_audit_p5(rep)
    summary = {
        "ts": _now_iso(), "elapsed_s": round(elapsed, 1),
        "db": "data/v9_forces.db", "session": "LONDON",
        "pairs": PAIRS, "timeframes": TFS, "limit": LIMIT, "workers": WORKERS,
        "report": rep, "audit": audit,
        "mode": "REPLAY", "r10": "zero order real",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print("\n=== AUTO-AUDIT P5 ===")
    for k, v in audit.items():
        print(f"  {k}: {v}")
    print(f"\nRapport : {OUT}")


if __name__ == "__main__":
    main()
