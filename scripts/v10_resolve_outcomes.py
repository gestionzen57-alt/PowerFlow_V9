"""v10_resolve_outcomes.py — Résolution outcomes unifiée S24
Fusionne : v10_resolve_outcomes.py + v10_resolve_outcomes_native.py + v10_behavior_resolve_outcomes.py
Plateforme : Windows (MT5 natif)
Auteur : PowerFlow Senior Audit — 2026-08-08

Usage :
  python scripts/v10_resolve_outcomes.py              # mode auto (détecte MT5)
  python scripts/v10_resolve_outcomes.py --mode native    # MT5 natif Windows
  python scripts/v10_resolve_outcomes.py --mode behavior  # depuis behavior_log
  python scripts/v10_resolve_outcomes.py --mode paper     # paper trade DB
"""

import argparse
import sqlite3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("POWERFLOW_DB", "data/powerflow_v10.db"))
LOG_PATH = Path("logs/resolve_outcomes.log")


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def resolve_native() -> int:
    """Résout depuis MT5 natif Windows via fichier exchange JSON."""
    exchange_file = Path("data/mt5_trades_export.json")
    if not exchange_file.exists():
        log(f"[NATIVE] Fichier MT5 absent : {exchange_file} — skip")
        return 0
    with open(exchange_file, encoding="utf-8") as f:
        trades = json.load(f)
    resolved = 0
    conn = sqlite3.connect(DB_PATH)
    try:
        for t in trades:
            ticket = t.get("ticket")
            profit = t.get("profit", 0.0)
            state = "WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN"
            conn.execute(
                "UPDATE paper_trades SET outcome=?, profit_usd=?, resolved_at=? "
                "WHERE ticket=? AND outcome IS NULL",
                (state, profit, datetime.now(timezone.utc).isoformat(), ticket),
            )
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                resolved += 1
        conn.commit()
    finally:
        conn.close()
    log(f"[NATIVE] {resolved} trades résolus depuis MT5 export")
    return resolved


def resolve_behavior() -> int:
    """Résout depuis behavior_log (signaux ICT capturés)."""
    conn = sqlite3.connect(DB_PATH)
    resolved = 0
    try:
        rows = conn.execute(
            "SELECT id, symbol, entry_time, direction FROM behavior_log "
            "WHERE outcome IS NULL AND entry_time IS NOT NULL"
        ).fetchall()
        for row in rows:
            rid, symbol, entry_time, direction = row
            # Résolution simplifiée : lookup price_close dans market_data
            result = conn.execute(
                "SELECT close FROM market_data WHERE symbol=? AND ts > ? ORDER BY ts LIMIT 1",
                (symbol, entry_time),
            ).fetchone()
            if result:
                # placeholder : logique réelle à connecter au tick_data
                outcome = "RESOLVED"
                conn.execute(
                    "UPDATE behavior_log SET outcome=?, resolved_at=? WHERE id=?",
                    (outcome, datetime.now(timezone.utc).isoformat(), rid),
                )
                resolved += 1
        conn.commit()
    finally:
        conn.close()
    log(f"[BEHAVIOR] {resolved} behavior entries résolues")
    return resolved


def resolve_paper() -> int:
    """Résout les paper trades ouverts depuis la DB."""
    conn = sqlite3.connect(DB_PATH)
    resolved = 0
    try:
        rows = conn.execute(
            "SELECT id, symbol, sl_price, tp_price, direction, entry_price "
            "FROM paper_trades WHERE outcome IS NULL"
        ).fetchall()
        for row in rows:
            rid, symbol, sl, tp, direction, entry = row
            last_close = conn.execute(
                "SELECT close FROM market_data WHERE symbol=? ORDER BY ts DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if not last_close:
                continue
            price = last_close[0]
            if direction == "BUY":
                outcome = "WIN" if price >= tp else "LOSS" if price <= sl else None
            else:
                outcome = "WIN" if price <= tp else "LOSS" if price >= sl else None
            if outcome:
                profit = abs(tp - entry) if outcome == "WIN" else -abs(entry - sl)
                conn.execute(
                    "UPDATE paper_trades SET outcome=?, profit_usd=?, resolved_at=? WHERE id=?",
                    (outcome, round(profit, 5), datetime.now(timezone.utc).isoformat(), rid),
                )
                resolved += 1
        conn.commit()
    finally:
        conn.close()
    log(f"[PAPER] {resolved} paper trades résolus")
    return resolved


def detect_mode() -> str:
    """Détecte automatiquement le meilleur mode."""
    if Path("data/mt5_trades_export.json").exists():
        return "native"
    return "paper"


def main():
    parser = argparse.ArgumentParser(description="Resolve outcomes V10 — mode unifié")
    parser.add_argument(
        "--mode",
        choices=["native", "behavior", "paper", "auto"],
        default="auto",
        help="Mode de résolution (défaut: auto)",
    )
    args = parser.parse_args()
    mode = args.mode if args.mode != "auto" else detect_mode()
    log(f"=== resolve_outcomes START mode={mode} ===")
    if mode == "native":
        n = resolve_native()
    elif mode == "behavior":
        n = resolve_behavior()
    else:
        n = resolve_paper()
    log(f"=== resolve_outcomes END — {n} trades résolus ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
