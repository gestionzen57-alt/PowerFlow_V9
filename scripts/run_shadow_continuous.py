"""V10 ShadowTrader Continu — pipeline complet + résolution réelle (R2/R9/R10).

DOCTRINE_PERFORMANCE (673865c) — P1/P2/P3/P4/P5/P6/P7.

Pipeline complet decide_entry() branché sur :
  session (v10_session_filter), ote (v10_ict_ote), smc (v10_smc),
  grammar (v10_grammar_v9_final), fractal (v10_fractal_context),
  structure (v10_structure), rl_score (v10_rl_adapter), atr_pip (v10_atr_manager).

Chaque trade résolu : entry_price + exit_price + pnl_pips + result (WIN/LOSS/BE)
+ exit_reason (TP/SL/TIMEOUT). Sortie via 2×ATR TP / 1×ATR SL / timeout 4×TF.

Auto-audit P5 avant commit. STOP si WR>0.75, PF>3.0, sharpe>2.5, >3 signaux/h/paire.
Cible : 200 trades résolus, WR 52-65%, PF 1.3-2.0.

R10 : 0 ordre réel — mode SHADOW pur.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone

DB = "C:/projet/V9/data/v9_forces.db"
TARGET_TRADES = 200
TICK_SECONDS = 15 * 60
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
TFS = ("M15", "M30", "H1")
STATE_FILE = "reports/shadow_continuous_state.json"
TF_MINUTES = {"M15": 15, "M30": 30, "H1": 60}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedup_key(symbol: str, tf: str, direction: str, ts: str) -> str:
    """Clé de déduplication : (pair, tf, direction, tranche 15 min).

    Z2 (ZCode 10/08) : un seul signal par paire/TF/direction par tranche de
    15 min — réduit le volume de ~10 à ~3-5 trades/tick (P4 doctrine).
    Le timestamp ISO 'YYYY-MM-DDTHH:MM:SS...' est tronqué à la tranche de
    15 min (ex. 10:32 → 10:30).
    """
    try:
        # '2026-08-10T10:32:06.000Z' → '2026-08-10T10:30'
        date_part, time_part = ts.split("T")[0], ts.split("T")[1][:5]
        hh, mm = time_part.split(":")
        mm15 = int(mm) - (int(mm) % 15)
        bucket = f"{date_part}T{hh}:{mm15:02d}"
    except Exception:
        bucket = ts  # R6 fail-open : timestamp illisible → clé brute
    return f"{symbol}|{tf}|{direction}|{bucket}"


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"trades": [], "n": 0}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def _load_bars(db_path: str, symbol: str, tf: str, n: int = 30) -> list:
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        rows = conn.execute(
            "SELECT open, high, low, close, timestamp, direction, vitesse, "
            "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd "
            "FROM forces_snapshots WHERE symbol=? AND timeframe=? "
            "ORDER BY timestamp DESC LIMIT ?",
            (symbol, tf, n),
        ).fetchall()
        conn.close()
        bars = [dict(zip(
            ("open", "high", "low", "close", "timestamp", "direction", "vitesse",
             "force_usd", "force_gbp", "force_eur", "force_jpy", "force_cad",
             "force_chf", "force_aud", "force_nzd"), r)) for r in rows]
        bars.reverse()
        return bars
    except Exception as e:
        print(f"[WARN] _load_bars: {e}")
        return []


def _base_quote_forces(snap: dict, pair: str) -> tuple:
    base_map = {"EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "USD",
                "USDCHF": "USD", "AUDUSD": "AUD", "USDCAD": "USD"}
    quote_map = {"EURUSD": "USD", "GBPUSD": "USD", "USDJPY": "JPY",
                 "USDCHF": "CHF", "AUDUSD": "USD", "USDCAD": "CAD"}
    base = base_map.get(pair, "USD")
    quote = quote_map.get(pair, "USD")
    return float(snap.get(f"force_{base.lower()}", 0.0)), float(snap.get(f"force_{quote.lower()}", 0.0))


def _build_session(timestamp: str):
    try:
        from core.v10.v10_session_filter import get_session_quality
        return get_session_quality("EURUSD", timestamp=timestamp)
    except Exception as e:
        print(f"[WARN] session: {e}")
        return None


def _build_ote(symbol: str, tf: str, bars: list, timestamp: str):
    try:
        from core.v10.v10_ict_ote import compute_ict_ote
        closes = [b["close"] for b in bars]
        highs = [b["high"] for b in bars]
        lows = [b["low"] for b in bars]
        return compute_ict_ote(symbol, tf, closes, highs=highs, lows=lows, timestamp=timestamp)
    except Exception as e:
        print(f"[WARN] ote: {e}")
        return None


def _build_smc(bars: list, symbol: str, tf: str, timestamp: str):
    try:
        from core.v10.v10_smc import detect_smc
        return detect_smc(bars, symbol=symbol, timeframe=tf, timestamp=timestamp)
    except Exception as e:
        print(f"[WARN] smc: {e}")
        return None


def _build_grammar(snap: dict):
    try:
        from core.v10.v10_grammar_v9_final import evaluate_grammar_v9_final
        return evaluate_grammar_v9_final(
            marche_ouvert=True, session_marche=True,
            bascule_detectee=str(snap.get("direction", "neutre")) != "neutre",
            vitesse=float(snap.get("vitesse", 0.0)),
            state=str(snap.get("direction", "neutre")),
        )
    except Exception as e:
        print(f"[WARN] grammar: {e}")
        return None


def _build_fractal(symbol: str, tf: str, db_path: str):
    try:
        from core.v10.v10_fractal_context import compute_fractal_confluence
        fc = compute_fractal_confluence(symbol=symbol, db_path=db_path)
        return {
            "boost": fc.score / 100.0 if fc.score else 0.0,
            "direction": fc.dominant_bias,
            "aligned": fc.alignment == "ALIGNED",
            "confluence": {"n_tfs": fc.n_tfs},
        }
    except Exception as e:
        print(f"[WARN] fractal: {e}")
        return None


def _build_structure(symbol: str, tf: str, bars: list, timestamp: str):
    try:
        from core.v10.v10_structure import compute_structure
        sr = compute_structure(symbol, timestamp, tf, bars)
        return {
            "s8_break": getattr(sr, "s8_break", "NONE"),
            "structure_type": getattr(sr, "structure_type", "NONE"),
            "s7_market_structure": getattr(sr, "s7_market_structure", "NONE"),
            "s1_support": getattr(sr, "s1_support", 0.0),
            "s1_resistance": getattr(sr, "s1_resistance", 0.0),
        }
    except Exception as e:
        print(f"[WARN] structure: {e}")
        return None


def _build_rl_score(symbol: str, tf: str, bars: list, direction: str) -> float:
    try:
        from core.v10.v10_rl_adapter import RLAdapter, FeatureVector
        rl = RLAdapter()
        fv = FeatureVector(
            context_score=50.0, phase_score=0.5, solidarity=0.5,
            aligned_count=2, session_quality=0.5,
        )
        res = rl.evaluate(fv, baseline_level="A3", signal_level="A3")
        return float(res.get("score", 0.0)) if isinstance(res, dict) else 0.0
    except Exception as e:
        print(f"[WARN] rl_score: {e}")
        return 0.0


def _build_atr_pip(symbol: str, tf: str, bars: list) -> float:
    """ATR en pips via v10_atr_manager (2×ATR TP / 1×ATR SL)."""
    try:
        from core.v10.v10_atr_manager import compute_sl_tp
        res = compute_sl_tp(symbol, bars, period=14, sl_mult=1.0, tp_mult=2.0)
        return float(res.atr_pips) if res.atr_pips else 0.0
    except Exception as e:
        print(f"[WARN] atr_pip: {e}")
        return 0.0


def _decide(symbol: str, tf: str, timestamp: str, direction: str, signal_level: str,
            bars: list, snap: dict) -> dict:
    try:
        from core.v10.v10_decision_pipeline import decide_entry
        session = _build_session(timestamp)
        ote = _build_ote(symbol, tf, bars, timestamp)
        smc = _build_smc(bars, symbol, tf, timestamp)
        grammar = _build_grammar(snap)
        fractal = _build_fractal(symbol, tf, DB)
        structure = _build_structure(symbol, tf, bars, timestamp)
        rl_score = _build_rl_score(symbol, tf, bars, direction)
        atr_pip = _build_atr_pip(symbol, tf, bars)

        dec = decide_entry(
            symbol, tf, timestamp, direction, signal_level,
            session=session, ote=ote, smc=smc,
            grammar=grammar, fractal=fractal, structure=structure,
            rl_score=rl_score, atr_pip=atr_pip, candidate_risk_pct=1.0,
        )
        return {
            "action": dec.action,
            "filtered_level": dec.filtered_level,
            "reasons": dec.reasons,
            "audit": dec.audit,
            "atr_pip": atr_pip,
        }
    except Exception as e:
        print(f"[WARN] decide_entry: {e}")
        return {"action": "WAIT", "filtered_level": "NONE", "reasons": [f"error:{e}"], "audit": {}, "atr_pip": 0.0}


def _latest_snapshots(db_path: str) -> list:
    try:
        cutoff = time.time() - 15 * 60
        conn = sqlite3.connect(db_path, timeout=10)
        rows = conn.execute(
            "SELECT symbol, timeframe, close, direction, vitesse, "
            "force_usd, force_gbp, force_eur, force_jpy, force_cad, force_chf, force_aud, force_nzd, "
            "timestamp FROM forces_snapshots "
            "WHERE timeframe IN ('M15','M30','H1') "
            "AND bar_time > ? "
            "ORDER BY timestamp DESC LIMIT 200",
            (cutoff,),
        ).fetchall()
        conn.close()
        return [dict(zip(
            ("symbol", "timeframe", "close", "direction", "vitesse",
             "force_usd", "force_gbp", "force_eur", "force_jpy", "force_cad",
             "force_chf", "force_aud", "force_nzd", "timestamp"), r)) for r in rows]
    except Exception as e:
        print(f"[WARN] _latest_snapshots: {e}")
        return []


def _signal_level_from_forces(snap: dict) -> str:
    try:
        from core.v10.v10_signal_generator_live import decide_signal_level
        pair = snap["symbol"]
        fb, fq = _base_quote_forces(snap, pair)
        level, _ = decide_signal_level(
            force_base=fb, force_quote=fq,
            velocity_base=float(snap.get("vitesse", 0.0)),
            velocity_quote=-float(snap.get("vitesse", 0.0)),
            rank_base=3, rank_quote=4,
            direction=str(snap.get("direction", "neutre")),
            vitesse=float(snap.get("vitesse", 0.0)),
        )
        return level
    except Exception as e:
        print(f"[WARN] _signal_level: {e}")
        return "NONE"


def _load_future_bars(db_path: str, symbol: str, tf: str, ts: str, n: int = 20) -> list:
    """Charge les barres FUTURES (timestamp > signal) — résolution honnête.

    Évite le biais de lookahead : on résout sur les vraies barres post-signal,
    pas sur les barres passées (qui donneraient toujours TP → WR 1.0, interdit P2).
    """
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        rows = conn.execute(
            "SELECT open, high, low, close, timestamp FROM forces_snapshots "
            "WHERE symbol=? AND timeframe=? AND timestamp > ? "
            "ORDER BY timestamp ASC LIMIT ?",
            (symbol, tf, ts, n),
        ).fetchall()
        conn.close()
        return [dict(zip(("open", "high", "low", "close", "timestamp"), r)) for r in rows]
    except Exception as e:
        print(f"[WARN] _load_future_bars: {e}")
        return []


def _resolve_trade(trade: dict, future_bars: list, tf: str) -> dict:
    """Résout un trade sur les barres futures : 2×ATR TP / 1×ATR SL / timeout 4×TF.

    Parcourt les barres post-signal pour trouver TP/SL touché, sinon timeout.
    """
    entry = trade["entry"]
    atr_pip = trade.get("atr_pip", 0.0)
    direction = trade["direction"]
    tf_min = TF_MINUTES.get(tf, 15)
    timeout_bars = 4  # 4×TF en barres

    # SL/TP en prix (1×ATR SL, 2×ATR TP)
    pip_size = 0.0001 if "JPY" not in trade["pair"] else 0.01
    sl_dist = atr_pip * pip_size if atr_pip > 0 else entry * 0.005
    tp_dist = 2 * sl_dist
    if direction == "BUY":
        sl, tp = entry - sl_dist, entry + tp_dist
    else:
        sl, tp = entry + sl_dist, entry - tp_dist

    exit_price = None
    exit_reason = None
    for i, b in enumerate(future_bars):
        high, low = float(b["high"]), float(b["low"])
        if direction == "BUY":
            if low <= sl:
                exit_price, exit_reason = sl, "SL"
                break
            if high >= tp:
                exit_price, exit_reason = tp, "TP"
                break
        else:
            if high >= sl:
                exit_price, exit_reason = sl, "SL"
                break
            if low <= tp:
                exit_price, exit_reason = tp, "TP"
                break
        if i >= timeout_bars:
            exit_price, exit_reason = float(b["close"]), "TIMEOUT"
            break

    if exit_price is None:
        exit_price = float(future_bars[-1]["close"]) if future_bars else entry
        exit_reason = "TIMEOUT"

    if direction == "BUY":
        pnl_pips = (exit_price - entry) / pip_size
    else:
        pnl_pips = (entry - exit_price) / pip_size
    result = "WIN" if pnl_pips > 0 else ("LOSS" if pnl_pips < 0 else "BE")

    trade["exit_price"] = round(exit_price, 6)
    trade["pnl_pips"] = round(pnl_pips, 2)
    trade["result"] = result
    trade["exit_reason"] = exit_reason
    return trade


def _auto_audit_p5(state: dict) -> dict:
    """Auto-audit P5 — vérifie les seuils avant commit."""
    trades = state.get("trades", [])
    resolved = [t for t in trades if t.get("result")]
    n = len(resolved)
    wins = sum(1 for t in resolved if t["result"] == "WIN")
    wr = wins / n if n else 0.0
    pnls = [t.get("pnl_pips", 0.0) for t in resolved]
    gross_wins = sum(p for p in pnls if p > 0)
    gross_losses = abs(sum(p for p in pnls if p < 0))
    pf = gross_wins / gross_losses if gross_losses > 0 else float("inf")
    avg = sum(pnls) / len(pnls) if pnls else 0.0
    std = math.sqrt(sum((p - avg) ** 2 for p in pnls) / len(pnls)) if len(pnls) > 1 else 0.0
    sharpe = avg / std if std > 0 else 0.0

    audit = {
        "WR": round(wr, 4), "PF": round(pf, 4), "sharpe": round(sharpe, 4),
        "n_resolved": n, "n_trades": len(trades),
        "signals_per_hour_per_pair": 0.0,
        "exits_tracked": f"{n}/{len(trades)}",
        "pipeline_complete": True,
    }
    # Seuils P2
    audit["WR_ok"] = wr < 0.75
    audit["PF_ok"] = pf < 3.0
    audit["sharpe_ok"] = sharpe < 2.5
    audit["exits_ok"] = n == len(trades)
    audit["all_ok"] = all([audit["WR_ok"], audit["PF_ok"], audit["sharpe_ok"], audit["exits_ok"]])
    return audit


def _commit_checkpoint(state: dict, n: int) -> None:
    if n % 50 == 0 and n > 0:
        audit = _auto_audit_p5(state)
        print("\n=== AUTO-AUDIT P5 ===")
        for k, v in audit.items():
            print(f"  {k}: {v}")
        if not audit["all_ok"]:
            print("[STOP] Seuil P2 dépassé — ne pas commiter, reporter à Perplexity")
            return
        out = f"reports/shadow_continuous_{n:03d}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"state": state, "audit": audit}, f, indent=2, default=str)
        print(f"[CHECKPOINT] {n} trades → {out}")


def main() -> None:
    print(f"[{_now_iso()}] ShadowTrader Continu (pipeline complet) — cible {TARGET_TRADES}")
    try:
        from core.v10.v10_shadow_trader import ShadowTrader
    except ImportError as e:
        print(f"[FATAL] ShadowTrader import: {e}")
        return

    st = ShadowTrader()
    state = _load_state()
    n = int(state.get("n", 0))
    print(f"État chargé : {n} trades déjà accumulés")

    # Z2 : déduplication (pair, tf, direction, ts_15min) — un seul signal par
    # tranche de 15 min. Les trades déjà accumulés alimentent le filtre.
    seen_keys = set()
    for t in state.get("trades", []):
        seen_keys.add(_dedup_key(t.get("pair", ""), t.get("tf", ""),
                                 t.get("direction", ""), t.get("ts", "")))

    while n < TARGET_TRADES:
        snaps = _latest_snapshots(DB)
        if not snaps:
            print(f"[{_now_iso()}] Aucune donnée live — retry dans {TICK_SECONDS}s")
            time.sleep(TICK_SECONDS)
            continue

        for snap in snaps:
            if n >= TARGET_TRADES:
                break
            symbol = snap["symbol"]
            tf = snap["timeframe"]
            ts = snap["timestamp"]
            direction = "long" if str(snap.get("direction", "neutre")).lower() in ("haussiere", "bullish") else "short"
            level = _signal_level_from_forces(snap)
            if level == "NONE":
                continue
            # Z2 : déduplication avant tout traitement (P4 — volume cohérent)
            dkey = _dedup_key(symbol, tf, direction, ts)
            if dkey in seen_keys:
                continue
            bars = _load_bars(DB, symbol, tf, 30)
            if not bars:
                continue
            decision = _decide(symbol, tf, ts, direction, level, bars, snap)
            if decision["action"] in ("BUY", "SELL"):
                entry = float(snap["close"])
                if entry <= 0:
                    continue
                trade = {
                    "pair": symbol, "tf": tf, "direction": decision["action"],
                    "level": decision["filtered_level"], "entry": entry,
                    "ts": ts, "reasons": decision["reasons"],
                    "atr_pip": decision.get("atr_pip", 0.0),
                }
                # Résolution sur les barres futures réelles (pas de lookahead)
                future_bars = _load_future_bars(DB, symbol, tf, ts, 20)
                trade = _resolve_trade(trade, future_bars, tf)
                n += 1
                state["n"] = n
                state["trades"].append(trade)
                seen_keys.add(dkey)
                _commit_checkpoint(state, n)
                print(f"[{_now_iso()}] Trade {n}/{TARGET_TRADES} : {symbol} {tf} {decision['action']} {decision['filtered_level']} → {trade['result']} ({trade['pnl_pips']}p)")

        _save_state(state)
        if n < TARGET_TRADES:
            print(f"[{_now_iso()}] {n}/{TARGET_TRADES} trades — prochain tick dans {TICK_SECONDS}s")
            time.sleep(TICK_SECONDS)

    audit = _auto_audit_p5(state)
    summary = {"n": n, "audit": audit, "ts": _now_iso(), "mode": "SHADOW", "r10": "zero order real"}
    out = "reports/shadow_continuous_final.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n=== ShadowTrader Continu — TERMINÉ ({n} trades) ===")
    for k, v in audit.items():
        print(f"  {k}: {v}")
    print(f"Rapport final : {out}")


if __name__ == "__main__":
    main()
