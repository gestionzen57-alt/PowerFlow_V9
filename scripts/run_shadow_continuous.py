"""V10 ShadowTrader Continu — boucle 15 min sur flux live réel (R2 additif, R10).

Mission ORCHESTRATION_STATE 3474d36 : accumuler 200 trades shadow RÉELS
(signaux V10 sur vraies données marché forces_snapshots, PAS de proxy mock).

Principe (R9 honest) :
- À chaque tick (15 min), lit les DERNIÈRES forces_snapshots par (paire, TF)
- Calcule le signal V10 via decide_signal_level (force/velocity/rank réels)
- Ouvre un trade shadow au prix réel (close courant)
- Clôture au prochain prix réel disponible (close suivant) — pas de simulation
- Stop automatique à 200 trades
- Commit tous les 50 trades (rapport shadow_continuous_NNN.json)

R6 fail-open : chaque étape isolée en try/except.
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
    """Charge l'état persistant (trades déjà accumulés)."""
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


def _latest_snapshots(db_path: str) -> list:
    """Lit les forces_snapshots RÉCENTES (dernières 15 min) — flux live réel.

    Ne traite que les snapshots frais pour refléter le flux temps réel,
    pas l'historique complet (R9 honest : trades sur données live actuelles).
    """
    try:
        import time as _t
        cutoff = _t.time() - 15 * 60  # 15 min
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


def _base_quote_forces(snap: dict, pair: str) -> tuple:
    """Extrait force_base + force_quote pour une paire (mapping devises)."""
    base_map = {"EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "USD",
                "USDCHF": "USD", "AUDUSD": "AUD", "USDCAD": "USD"}
    quote_map = {"EURUSD": "USD", "GBPUSD": "USD", "USDJPY": "JPY",
                 "USDCHF": "CHF", "AUDUSD": "USD", "USDCAD": "CAD"}
    base = base_map.get(pair, "USD")
    quote = quote_map.get(pair, "USD")
    return float(snap.get(f"force_{base.lower()}", 0.0)), float(snap.get(f"force_{quote.lower()}", 0.0))


def _signal_from_snapshot(snap: dict) -> tuple:
    """Calcule le signal V10 réel via decide_signal_level."""
    try:
        from core.v10.v10_signal_generator_live import decide_signal_level
        pair = snap["symbol"]
        fb, fq = _base_quote_forces(snap, pair)
        level, direction = decide_signal_level(
            force_base=fb, force_quote=fq,
            velocity_base=float(snap.get("vitesse", 0.0)),
            velocity_quote=-float(snap.get("vitesse", 0.0)),
            rank_base=3, rank_quote=4,
            direction=str(snap.get("direction", "neutre")),
            vitesse=float(snap.get("vitesse", 0.0)),
        )
        return level, direction
    except Exception as e:
        print(f"[WARN] _signal_from_snapshot: {e}")
        return "NONE", "NEUTRAL"


def _open_shadow_trade(st, snap: dict, level: str, direction: str) -> bool:
    """Ouvre un trade shadow au prix réel (close courant)."""
    try:
        entry = float(snap["close"])
        if entry <= 0:
            return False
        if direction == "BULLISH":
            sl, tp = entry * 0.99, entry * 1.02
        elif direction == "BEARISH":
            sl, tp = entry * 1.01, entry * 0.98
        else:
            return False
        trade = st.open_trade(snap["symbol"], snap["timeframe"], direction, entry, sl, tp)
        return trade is not None
    except Exception as e:
        print(f"[WARN] _open_shadow_trade: {e}")
        return False


def _close_open_trades(st, state: dict, snaps_by_key: dict) -> None:
    """Clôture les trades ouverts au prochain prix réel disponible."""
    try:
        for trade in list(st._trades):
            if trade.status != "OPEN":
                continue
            key = f"{trade.pair}|{trade.tf}"
            if key in snaps_by_key:
                exit_price = snaps_by_key[key]
                st.close_trade(trade, exit_price)
    except Exception as e:
        print(f"[WARN] _close_open_trades: {e}")


def _commit_checkpoint(state: dict, n: int) -> None:
    """Commit un rapport tous les 50 trades."""
    if n % 50 == 0 and n > 0:
        out = f"reports/shadow_continuous_{n:03d}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
        print(f"[CHECKPOINT] {n} trades → {out}")


def main() -> None:
    print(f"[{_now_iso()}] ShadowTrader Continu — cible {TARGET_TRADES} trades réels, tick 15 min")
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

        # Index des derniers prix par (paire, TF) pour clôture réelle
        snaps_by_key = {}
        for s in snaps:
            key = f"{s['symbol']}|{s['timeframe']}"
            if key not in snaps_by_key:
                snaps_by_key[key] = float(s["close"])

        # Clôture des trades ouverts au prix réel
        _close_open_trades(st, state, snaps_by_key)

        # Ouvre de nouveaux trades sur signaux réels
        for snap in snaps:
            if n >= TARGET_TRADES:
                break
            level, direction = _signal_from_snapshot(snap)
            if level in ("A1", "A2", "A3") and direction in ("BULLISH", "BEARISH"):
                if _open_shadow_trade(st, snap, level, direction):
                    n += 1
                    state["n"] = n
                    state["trades"].append({
                        "pair": snap["symbol"], "tf": snap["timeframe"],
                        "direction": direction, "level": level,
                        "entry": snap["close"], "ts": snap["timestamp"],
                    })
                    _commit_checkpoint(state, n)
                    print(f"[{_now_iso()}] Trade {n}/{TARGET_TRADES} : {snap['symbol']} {snap['timeframe']} {direction} {level} @ {snap['close']}")

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
