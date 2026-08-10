"""V10 ReplayEngine M15 + filtre régime HMM (R2 additif, R10).

DOCTRINE_PERFORMANCE (673865c) — P1/P2/P3/P5/P6.

Base run_replay_m15_focused.py + filtre régime avant chaque décision :
- detect_hmm_regime(closes) → skip (HOLD) si regime ∉ {TRENDING_UP, TRENDING_DOWN}
- Uniquement les régimes de tendance permettent BUY/SELL
- Skip RANGING / VOLATILE / NEWS_LOCK / UNKNOWN (drainent le PnL, W3/W4 WFA)

Paires : EURUSD + USDCAD + USDCHF, M15, LONDON, limit=800.
Auto-audit P5 : cible WR ≥ 0.58, PF ≥ 1.5.

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
OUT = "reports/replay_m15_regime_2026_08_10.json"
PAIRS = ["EURUSD", "USDCAD", "USDCHF"]
TF = "M15"
LIMIT = 800
WORKERS = 4

# Régimes de tendance autorisés (intention H3 : TREND/MARKUP/MARKDOWN)
ALLOWED_REGIMES = {"TRENDING_UP", "TRENDING_DOWN"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _patch_load_bars_with_regime() -> None:
    """Patche _load_bars pour charger forces natives ET wrapper _replay_pair_tf
    avec filtre régime HMM. Injection runtime — aucun fichier core modifié."""
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

    # Sauvegarde de la décision originale
    orig_decide_one = eng._decide_one

    def _decide_one_with_regime(pair, tf, tf_role, window, h4_bias,
                                fractal_conf, db_path, session, bayes_thresholds):
        """Ajoute le filtre régime HMM AVANT la décision : si la fenêtre courante
        est en régime RANGING/VOLATILE/NEWS/UNKNOWN → HOLD (skip)."""
        try:
            from core.v10.v10_regime_hmm import detect_hmm_regime
            closes = [float(b.get("close", 0.0)) for b in window[-60:]]
            if len(closes) >= 30:
                rr = detect_hmm_regime(closes, symbol=pair, timestamp="")
                regime_name = rr.regime.name if hasattr(rr.regime, "name") else str(rr.regime)
                if regime_name not in ALLOWED_REGIMES:
                    # Régime non-trend → HOLD direct (skip le trade).
                    # Uniquement champs valides de DecisionRecord (reasons/n_bars
                    # n'existent pas → TypeError silencieuse sinon).
                    return eng.DecisionRecord(
                        pair=pair, tf=tf, tf_role=tf_role, timestamp=str(window[-1].get("timestamp", "")),
                        action="HOLD", direction="", signal_level="NONE", pipeline="regime_filter",
                        held_reason=f"REGIME_{regime_name}",
                        vsa_ok=False, fractal_boost=0.0,
                        rl_boosted=False, pnl_pips=0.0, tp_pips=0.0, sl_pips=0.0, win=False,
                    )
        except Exception as exc:
            # R6 fail-open : si régime KO, on laisse la décision originale passer
            pass
        return orig_decide_one(pair, tf, tf_role, window, h4_bias,
                               fractal_conf, db_path, session, bayes_thresholds)

    eng._decide_one = _decide_one_with_regime
    print("[PATCH] _load_bars + _decide_one filtre régime HMM — C10 OK")


def _compute_pf_pnl(by_pair_tf: list) -> dict:
    gw, gl, wins, losses, n = 0.0, 0.0, 0, 0, 0
    n_regime_filtered = 0
    per_pair = {}
    for x in by_pair_tf:
        pair = x.get("pair")
        p_gw = p_gl = 0.0
        p_w = p_l = 0
        for d in x.get("decisions", []):
            # Comptage des trades filtrés par régime (held_reason=REGIME_*)
            if "REGIME_" in str(d.get("held_reason", "")):
                n_regime_filtered += 1
                continue
            if d.get("action") not in ("BUY", "SELL"):
                continue
            pnl = float(d.get("pnl_pips", 0.0))
            n += 1
            if pnl > 0:
                gw += pnl
                p_gw += pnl
                wins += 1
                p_w += 1
            elif pnl < 0:
                gl += abs(pnl)
                p_gl += abs(pnl)
                losses += 1
                p_l += 1
        if pair and (p_gw or p_gl):
            per_pair[pair] = {
                "wins": p_w, "losses": p_l,
                "gross_wins": round(p_gw, 2), "gross_losses": round(p_gl, 2),
                "pnl_pips": round(p_gw - p_gl, 2),
            }
    pf = gw / gl if gl > 0 else (float("inf") if gw > 0 else 0.0)
    return {
        "n_trades": n, "wins": wins, "losses": losses,
        "wr": round(wins / n, 4) if n else 0.0,
        "pf": round(pf, 4), "pnl_total_pips": round(gw - gl, 2),
        "gross_wins": round(gw, 2), "gross_losses": round(gl, 2),
        "n_regime_filtered": n_regime_filtered,
        "per_pair": per_pair,
    }


def _auto_audit_p5(report: dict, pf_detail: dict) -> dict:
    global_wr = float(report.get("global_wr", 0.0))
    global_pnl = float(report.get("global_pnl", 0.0))
    n_trades = int(report.get("n_total_trades", 0))
    avg_sharpe = float(report.get("avg_sharpe", 0.0))
    pf = float(pf_detail.get("pf", 0.0))

    audit = {
        "global_wr": round(global_wr, 4),
        "global_pnl_pips": round(global_pnl, 2),
        "avg_sharpe": round(avg_sharpe, 4),
        "pf": round(pf, 4),
        "n_total_trades": n_trades,
        "n_regime_filtered": pf_detail.get("n_regime_filtered", 0),
        "pairs": 3, "timeframes": 1,
        "live_ready": report.get("live_ready", False),
        "live_ready_reason": report.get("live_ready_reason", ""),
    }
    audit["WR_ok"] = global_wr >= 0.58   # cible H3
    audit["PF_ok"] = pf >= 1.5           # cible H3
    audit["sharpe_ok"] = avg_sharpe < 2.5
    audit["n_trades_ok"] = n_trades >= 60
    audit["all_ok"] = all([audit["WR_ok"], audit["PF_ok"], audit["sharpe_ok"], audit["n_trades_ok"]])
    return audit


def main() -> None:
    print(f"[{_now_iso()}] Replay M15 + filtre régime HMM — {PAIRS} × M15 × limit {LIMIT}")
    print(f"DB : {REPLAY_DB}")

    if not os.path.exists(REPLAY_DB):
        print(f"[FATAL] DB introuvable : {REPLAY_DB}")
        return

    try:
        from core.v10.v10_replay_engine import ReplayEngine
    except ImportError as e:
        print(f"[FATAL] ReplayEngine import: {e}")
        return

    _patch_load_bars_with_regime()
    engine = ReplayEngine(db_path=REPLAY_DB, session="LONDON")
    t0 = time.time()
    try:
        report = engine.run_all(
            pairs=PAIRS, timeframes=[TF],
            limit=LIMIT, workers=WORKERS,
            run_c10_postprocess=True,
        )
    except Exception as e:
        print(f"[FATAL] run_all: {e}")
        return
    elapsed = time.time() - t0

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
            rep[key] = getattr(report, attr)
        except Exception:
            rep[key] = None
    rep["global_pnl"] = rep.get("global_pnl_pips")

    pf_detail = _compute_pf_pnl(rep.get("by_pair_tf", []) or [])
    rep["pf"] = pf_detail["pf"]

    audit = _auto_audit_p5(rep, pf_detail)
    summary = {
        "ts": _now_iso(), "elapsed_s": round(elapsed, 1),
        "db": "data/v9_forces.db", "session": "LONDON",
        "pairs": PAIRS, "timeframes": [TF], "limit": LIMIT, "workers": WORKERS,
        "regime_filter": {
            "allowed": sorted(ALLOWED_REGIMES),
            "skipped": ["RANGING", "VOLATILE", "NEWS_LOCK", "UNKNOWN"],
        },
        "report": {k: v for k, v in rep.items() if k != "by_pair_tf"},
        "pf_detail": pf_detail,
        "audit": audit,
        "mode": "REPLAY_REGIME", "r10": "zero order real",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n[{_now_iso()}] Replay terminé en {elapsed:.1f}s")
    print("\n=== AUTO-AUDIT P5 ===")
    for k, v in audit.items():
        print(f"  {k}: {v}")
    print(f"\nPF détaillé : {pf_detail['n_trades']} trades, WR {pf_detail['wr']}, PF {pf_detail['pf']}, PnL {pf_detail['pnl_total_pips']}p | régime filtrés: {pf_detail['n_regime_filtered']}")
    for pair, d in pf_detail["per_pair"].items():
        print(f"  {pair}: WR {d['wins']/(d['wins']+d['losses']) if (d['wins']+d['losses']) else 0:.1%}, PnL {d['pnl_pips']}p")
    print(f"\nRapport : {OUT}")


if __name__ == "__main__":
    main()
