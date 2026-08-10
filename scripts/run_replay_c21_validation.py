"""scripts/run_replay_c21_validation.py — H-REPLAY-C21 (R2 additif, R10).

Validation replay C21 sur vraie DB `data/v9_forces.db` :
  Paires : EURUSD, USDCAD, USDCHF | TF : M15 | Session : LONDON | 800 barres

Métriques : WR, PF, Sharpe + breakdown pre_wave_phase
  (COMPRESSION / DIVERGENCE / NEUTRAL) — WR/PF/PnL par phase.

Auto-audit P5 (DOCTRINE_PERFORMANCE 673865c) | R9 honnête | R10 compute only.

Sortie : reports/replay_c21_validation_2026_08_10.json

NOTE : réutilise le monkeypatch `_load_bars` (bug C10 : colonne real_volume
inexistante) — R2 additif, aucun fichier core modifié.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from datetime import UTC, datetime, timezone
from typing import Any, Dict, List

REPLAY_DB = "C:/projet/V9/data/v9_forces.db"
OUT = "reports/replay_c21_validation_2026_08_10.json"
PAIRS = ["EURUSD", "USDCAD", "USDCHF"]
TFS = ["M15"]
LIMIT = 800
WORKERS = 4
SESSION = "LONDON"

# Seuil divergence sigma (H7 spec)
SIGMA_DIVERGENCE_THRESHOLD = 28.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _patch_load_bars() -> None:
    """Contournement runtime R2 du bug C10 : _load_bars lit real_volume
    (inexistante) puis retombe sur ohlcv (inexistante) → toujours [].

    Remplace par une lecture honnête sur forces_snapshots + forces natives.
    Aucun fichier core modifié (R2 additif).
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
            for c in ("force_usd", "force_gbp", "force_eur", "force_jpy",
                      "force_cad", "force_chf", "force_aud", "force_nzd"):
                b[c] = float(b.get(c) or 50.0)
            b["direction"] = b.get("direction", "neutre")
            b["vitesse"] = float(b.get("vitesse") or 0.0)
            bars.append(b)
        return bars

    eng._load_bars = _load_bars_fixed
    print("[PATCH] _load_bars monkeypatched (tick_volume + forces_native) — C21 OK")


# ─────────────────────────────────────────────────────────────────────
# PRE-WAVE PHASE BREAKDOWN
# ─────────────────────────────────────────────────────────────────────

def _sigma_of_bar(b: Dict[str, Any]) -> float:
    """Sigma des 8 forces d'une barre (0-100)."""
    forces = [float(b.get(f"force_{c.lower()}") or 50.0)
              for c in ("USD", "GBP", "EUR", "JPY", "CAD", "CHF", "AUD", "NZD")]
    return statistics.pstdev(forces)


def _pre_wave_phase(sigma_history: List[float]) -> str:
    """Phase pre-wave depuis une série sigma (API ZCode detect_pre_wave).

    COMPRESSION : pre_wave=True (compression sigma détectée)
    DIVERGENCE  : sigma_recent > seuil divergence
    NEUTRAL     : sinon
    """
    if not sigma_history or len(sigma_history) < 6:
        return "NEUTRAL"
    try:
        from core.v10.v10_fatman_wave_predictor import detect_pre_wave
        alert = detect_pre_wave(sigma_history, min_history=6, window=4)
        if alert.pre_wave:
            return "COMPRESSION"
        if alert.sigma_recent > SIGMA_DIVERGENCE_THRESHOLD:
            return "DIVERGENCE"
    except Exception:
        pass
    return "NEUTRAL"


def _pre_wave_phases_for_bars(bars: List[Dict[str, Any]]) -> Dict[str, str]:
    """Map timestamp → phase pre-wave pour chaque barre (rolling sigma).

    Pour chaque barre i, on calcule la phase sur la fenêtre sigma
    [i-9, i] (10 dernières barres), cohérent avec get_sigma_history(n=10).
    """
    phases: Dict[str, str] = {}
    sigmas = [_sigma_of_bar(b) for b in bars]
    for i, b in enumerate(bars):
        hist = sigmas[max(0, i - 9): i + 1]
        phases[str(b.get("timestamp"))] = _pre_wave_phase(hist)
    return phases


def _compute_pf_pnl(by_pair_tf: list) -> dict:
    """PF (gross wins / |gross losses|) + WR depuis les décisions résolues."""
    gw, gl, wins, losses, n = 0.0, 0.0, 0, 0, 0
    per_pair = {}
    for x in by_pair_tf:
        pair = x.get("pair")
        p_gw = p_gl = 0.0
        p_w = p_l = 0
        for d in x.get("decisions", []):
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
        "per_pair": per_pair,
    }


def _compute_pre_wave_breakdown(by_pair_tf: list) -> dict:
    """WR/PF/PnL par pre_wave_phase (COMPRESSION/DIVERGENCE/NEUTRAL).

    Pour chaque trade (décision BUY/SELL), on détermine la phase pre-wave
    à la barre d'entrée via le timestamp de la décision.
    """
    breakdown: Dict[str, Dict[str, Any]] = {
        "COMPRESSION": {"n": 0, "wins": 0, "gw": 0.0, "gl": 0.0, "pnl": 0.0},
        "DIVERGENCE": {"n": 0, "wins": 0, "gw": 0.0, "gl": 0.0, "pnl": 0.0},
        "NEUTRAL": {"n": 0, "wins": 0, "gw": 0.0, "gl": 0.0, "pnl": 0.0},
    }
    for x in by_pair_tf:
        phases = _pre_wave_phases_for_bars(x.get("bars", []))
        for d in x.get("decisions", []):
            if d.get("action") not in ("BUY", "SELL"):
                continue
            phase = phases.get(str(d.get("timestamp")), "NEUTRAL")
            if phase not in breakdown:
                phase = "NEUTRAL"
            pnl = float(d.get("pnl_pips", 0.0))
            b = breakdown[phase]
            b["n"] += 1
            if pnl > 0:
                b["wins"] += 1
                b["gw"] += pnl
            elif pnl < 0:
                b["gl"] += abs(pnl)
            b["pnl"] += pnl
    out = {}
    for phase, b in breakdown.items():
        n = b["n"]
        out[phase] = {
            "n_trades": n,
            "wr": round(b["wins"] / n, 4) if n else 0.0,
            "pf": round(b["gw"] / b["gl"], 4) if b["gl"] > 0 else
                  (float("inf") if b["gw"] > 0 else 0.0),
            "pnl_pips": round(b["pnl"], 2),
        }
    return out


def _auto_audit_p5(report: dict) -> dict:
    """Auto-audit P5 — seuils doctrinaux (WR<0.75, sharpe<2.5, n>=100)."""
    global_wr = float(report.get("global_wr", 0.0))
    avg_sharpe = float(report.get("avg_sharpe", 0.0))
    n_trades = int(report.get("n_total_trades", 0))
    pf = float(report.get("pf", 0.0))
    audit = {
        "global_wr": round(global_wr, 4),
        "global_pnl_pips": round(float(report.get("global_pnl", 0.0)), 2),
        "avg_sharpe": round(avg_sharpe, 4),
        "pf": round(pf, 4),
        "n_total_trades": n_trades,
        "pairs": 3, "timeframes": 1,
        "live_ready": report.get("live_ready", False),
        "live_ready_reason": report.get("live_ready_reason", ""),
    }
    audit["WR_ok"] = global_wr < 0.75
    audit["sharpe_ok"] = avg_sharpe < 2.5
    audit["n_trades_ok"] = n_trades >= 100
    audit["all_ok"] = all([audit["WR_ok"], audit["sharpe_ok"], audit["n_trades_ok"]])
    return audit


def main() -> None:
    print(f"[{_now_iso()}] Replay C21 validation — {PAIRS} × M15 × LONDON × {LIMIT}")
    print(f"DB : {REPLAY_DB}")

    if not os.path.exists(REPLAY_DB):
        print(f"[FATAL] DB introuvable : {REPLAY_DB}")
        return

    try:
        from core.v10.v10_replay_engine import ReplayEngine
    except ImportError as e:
        print(f"[FATAL] ReplayEngine import: {e}")
        return

    _patch_load_bars()
    engine = ReplayEngine(db_path=REPLAY_DB, session=SESSION)
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

    # Injecter les barres dans by_pair_tf pour le breakdown pre-wave
    by_pair_tf = rep.get("by_pair_tf", []) or []
    for x in by_pair_tf:
        x["bars"] = _load_bars_for_pair(x.get("pair"))

    pf_detail = _compute_pf_pnl(by_pair_tf)
    rep["pf"] = pf_detail["pf"]
    rep["pf_detail"] = pf_detail

    pre_wave_breakdown = _compute_pre_wave_breakdown(by_pair_tf)

    audit = _auto_audit_p5(rep)
    summary = {
        "ts": _now_iso(), "elapsed_s": round(elapsed, 1),
        "db": "data/v9_forces.db", "session": SESSION,
        "pairs": PAIRS, "timeframes": TFS, "limit": LIMIT, "workers": WORKERS,
        "report": {k: v for k, v in rep.items() if k not in ("by_pair_tf",)},
        "pf_detail": pf_detail,
        "pre_wave_phase_breakdown": pre_wave_breakdown,
        "audit": audit,
        "mode": "REPLAY", "r10": "zero order real",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n[{_now_iso()}] Replay terminé en {elapsed:.1f}s")
    print("\n=== AUTO-AUDIT P5 ===")
    for k, v in audit.items():
        print(f"  {k}: {v}")
    print(f"\nPF détaillé : {pf_detail['n_trades']} trades, WR {pf_detail['wr']}, "
          f"PF {pf_detail['pf']}, PnL {pf_detail['pnl_total_pips']}p")
    print("\n=== PRE-WAVE PHASE BREAKDOWN ===")
    for phase, d in pre_wave_breakdown.items():
        print(f"  {phase}: {d['n_trades']} trades, WR {d['wr']}, PF {d['pf']}, PnL {d['pnl_pips']}p")
    print(f"\nRapport : {OUT}")


def _load_bars_for_pair(pair: str) -> List[Dict[str, Any]]:
    """Charge les barres M15 d'une paire (réutilise le monkeypatch)."""
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{REPLAY_DB}?mode=ro", uri=True, timeout=15)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT bar_time AS timestamp, open, high, low, close, tick_volume, "
            "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd "
            "FROM forces_snapshots "
            "WHERE symbol=? AND timeframe='M15' AND is_closed_bar=1 "
            "ORDER BY bar_time DESC LIMIT ?",
            (pair.upper(), LIMIT),
        ).fetchall()
        con.close()
        bars = []
        for r in reversed(rows):
            b = dict(r)
            for k in ("open", "high", "low", "close"):
                b[k] = float(b.get(k) or 0.0)
            for c in ("force_usd", "force_gbp", "force_eur", "force_jpy",
                      "force_cad", "force_chf", "force_aud", "force_nzd"):
                b[c] = float(b.get(c) or 50.0)
            bars.append(b)
        return bars
    except Exception:
        return []


if __name__ == "__main__":
    main()
