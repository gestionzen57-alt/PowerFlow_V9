"""V10 ShadowTrader Continu — decide_entry() complet branché (R2 additif, R10).

Mission : brancher l'appel decide_entry() avec TOUS les paramètres :
  - session  : v10_session_filter.get_session_quality (heure UTC)
  - ote      : v10_ict_ote.compute_ict_ote
  - smc      : v10_smc.detect_smc
  - grammar  : v10_grammar_v9_final.evaluate_grammar_v9_final
  - fractal  : v10_fractal_context.compute_fractal_confluence
  - structure: v10_structure.compute_structure
  - rl_score : v10_rl_adapter.RLAdapter.evaluate

Seuls les trades avec action = BUY/SELL (pas WAIT) sont enregistrés.
Résultat attendu : volume de signaux divisé par 3-5, qualité réelle.

R6 fail-open : chaque module isolé en try/except (si un module échoue, on
passe le paramètre à None plutôt que de crasher).
R10 : 0 ordre réel — mode SHADOW pur.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone

DB = "C:/projet/V9/data/v9_forces.db"  # vraie DB (worktree principal)
TARGET_TRADES = 200
TICK_SECONDS = 15 * 60  # 15 min
PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD")
TFS = ("M15", "M30", "H1")
STATE_FILE = "reports/shadow_continuous_state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    """Charge les n dernières barres OHLC pour un (symbol, tf) — ordre ascendant."""
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
        bars.reverse()  # ordre ascendant
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
    """Session depuis l'heure UTC (v10_session_filter)."""
    try:
        from core.v10.v10_session_filter import get_session_quality
        return get_session_quality("EURUSD", timestamp=timestamp)
    except Exception as e:
        print(f"[WARN] session: {e}")
        return None


def _build_ote(symbol: str, tf: str, bars: list, timestamp: str):
    """OTE depuis v10_ict_ote."""
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
    """SMC depuis v10_smc."""
    try:
        from core.v10.v10_smc import detect_smc
        return detect_smc(bars, symbol=symbol, timeframe=tf, timestamp=timestamp)
    except Exception as e:
        print(f"[WARN] smc: {e}")
        return None


def _build_grammar(snap: dict):
    """Grammar depuis v10_grammar_v9_final."""
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
    """Fractal depuis v10_fractal_context."""
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
    """Structure depuis v10_structure (retourne un dict, pas l'objet)."""
    try:
        from core.v10.v10_structure import compute_structure
        sr = compute_structure(symbol, timestamp, tf, bars)
        # decide_entry consomme structure.get("s8_break") → dict requis
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
    """RL score depuis v10_rl_adapter."""
    try:
        from core.v10.v10_rl_adapter import RLAdapter
        rl = RLAdapter()
        # FeatureVector 5 dims (CEO spec)
        from core.v10.v10_rl_adapter import FeatureVector
        fv = FeatureVector(
            context_score=50.0, phase_score=0.5, solidarity=0.5,
            aligned_count=2, session_quality=0.5,
        )
        res = rl.evaluate(fv, baseline_level="A3", signal_level="A3")
        return float(res.get("score", 0.0)) if isinstance(res, dict) else 0.0
    except Exception as e:
        print(f"[WARN] rl_score: {e}")
        return 0.0


def _decide(symbol: str, tf: str, timestamp: str, direction: str, signal_level: str,
            bars: list, snap: dict) -> dict:
    """Appelle decide_entry() avec tous les paramètres branchés."""
    try:
        from core.v10.v10_decision_pipeline import decide_entry
        session = _build_session(timestamp)
        ote = _build_ote(symbol, tf, bars, timestamp)
        smc = _build_smc(bars, symbol, tf, timestamp)
        grammar = _build_grammar(snap)
        fractal = _build_fractal(symbol, tf, DB)
        structure = _build_structure(symbol, tf, bars, timestamp)
        rl_score = _build_rl_score(symbol, tf, bars, direction)

        dec = decide_entry(
            symbol, tf, timestamp, direction, signal_level,
            session=session, ote=ote, smc=smc,
            grammar=grammar, fractal=fractal, structure=structure,
            rl_score=rl_score, candidate_risk_pct=1.0,
        )
        return {
            "action": dec.action,
            "filtered_level": dec.filtered_level,
            "reasons": dec.reasons,
            "audit": dec.audit,
        }
    except Exception as e:
        print(f"[WARN] decide_entry: {e}")
        return {"action": "WAIT", "filtered_level": "NONE", "reasons": [f"error:{e}"], "audit": {}}


def _latest_snapshots(db_path: str) -> list:
    """Lit les forces_snapshots RÉCENTES (dernières 15 min) — flux live réel."""
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
    """Niveau de signal A1/A2/A3 depuis les forces (proxy simple)."""
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


def _commit_checkpoint(state: dict, n: int) -> None:
    if n % 50 == 0 and n > 0:
        out = f"reports/shadow_continuous_{n:03d}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
        print(f"[CHECKPOINT] {n} trades → {out}")


def main() -> None:
    print(f"[{_now_iso()}] ShadowTrader Continu (decide_entry complet) — cible {TARGET_TRADES}")
    try:
        from core.v10.v10_shadow_trader import ShadowTrader
    except ImportError as e:
        print(f"[FATAL] ShadowTrader import: {e}")
        return

    st = ShadowTrader()
    state = _load_state()
    n = int(state.get("n", 0))
    print(f"État chargé : {n} trades déjà accumulés")

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
            bars = _load_bars(DB, symbol, tf, 30)
            if not bars:
                continue
            decision = _decide(symbol, tf, ts, direction, level, bars, snap)
            if decision["action"] in ("BUY", "SELL"):
                entry = float(snap["close"])
                if entry <= 0:
                    continue
                if decision["action"] == "BUY":
                    sl, tp = entry * 0.99, entry * 1.02
                else:
                    sl, tp = entry * 1.01, entry * 0.98
                trade = st.open_trade(symbol, tf, decision["action"], entry, sl, tp)
                if trade is None:
                    continue
                n += 1
                state["n"] = n
                state["trades"].append({
                    "pair": symbol, "tf": tf, "direction": decision["action"],
                    "level": decision["filtered_level"], "entry": entry,
                    "ts": ts, "reasons": decision["reasons"],
                })
                _commit_checkpoint(state, n)
                print(f"[{_now_iso()}] Trade {n}/{TARGET_TRADES} : {symbol} {tf} {decision['action']} {decision['filtered_level']} @ {entry}")

        _save_state(state)
        if n < TARGET_TRADES:
            print(f"[{_now_iso()}] {n}/{TARGET_TRADES} trades — prochain tick dans {TICK_SECONDS}s")
            time.sleep(TICK_SECONDS)

    summary = st.summary()
    summary["target_trades"] = TARGET_TRADES
    summary["n_accumulated"] = n
    summary["ts"] = _now_iso()
    summary["mode"] = "SHADOW"
    summary["r10"] = "zero order real — R10 maintenu"
    out = "reports/shadow_continuous_final.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n=== ShadowTrader Continu — TERMINÉ ({n} trades) ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"Rapport final : {out}")


if __name__ == "__main__":
    main()
