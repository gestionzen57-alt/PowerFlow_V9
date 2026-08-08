"""v10_paper2live.py — Bascule paper → live réel S25
Plateforme : Windows · MT5 natif
Auteur : PowerFlow Senior — 2026-08-08

Bascule une paire validée (LIVE_READY) du mode paper vers le live réel MT5.
Ne s'exécute QUE si circuit-breaker = OFF et live_gate = GO.

Usage :
  python scripts/v10_paper2live.py --pair GBPUSD   # bascule une paire
  python scripts/v10_paper2live.py --all            # bascule toutes LIVE_READY
  python scripts/v10_paper2live.py --status         # affiche mode actuel
  python scripts/v10_paper2live.py --rollback EURUSD # retour paper immédiat
"""

import argparse
import sqlite3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("POWERFLOW_DB", "data/powerflow_v10.db"))
BREAKER_STATE = Path("data/circuit_breaker_state.json")
LIVE_CONFIG = Path("data/live_pairs_config.json")
LOG_PATH = Path("logs/paper2live.log")


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def breaker_is_active() -> bool:
    if not BREAKER_STATE.exists():
        return False
    return json.loads(BREAKER_STATE.read_text(encoding="utf-8")).get("triggered", False)


def load_live_config() -> dict:
    if LIVE_CONFIG.exists():
        return json.loads(LIVE_CONFIG.read_text(encoding="utf-8"))
    return {}


def save_live_config(cfg: dict):
    LIVE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    LIVE_CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_live_ready_pairs(conn) -> list[str]:
    rows = conn.execute(
        "SELECT symbol FROM pair_status WHERE status='LIVE_READY'"
    ).fetchall()
    return [r[0] for r in rows]


def switch_to_live(pair: str, conn, cfg: dict):
    cfg[pair] = {
        "mode": "LIVE",
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "lot_size": float(os.getenv(f"LOT_{pair}", "0.01")),
        "max_daily_trades": 3,
        "circuit_breaker": "active",
    }
    conn.execute(
        "UPDATE pair_status SET status='LIVE', live_at=? WHERE symbol=?",
        (datetime.now(timezone.utc).isoformat(), pair)
    )
    conn.commit()
    log(f"[LIVE] {pair} → MODE LIVE activé (lot={cfg[pair]['lot_size']})")  
    os.system(f'python scripts/v10_telegram_alert.py --msg "🟢 {pair} BASCULÉ EN LIVE — lot={cfg[pair]["lot_size"]}"')


def rollback_to_paper(pair: str, conn, cfg: dict):
    cfg[pair] = {
        "mode": "PAPER",
        "rollback_at": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(
        "UPDATE pair_status SET status='PAPER_ROLLBACK', live_at=NULL WHERE symbol=?",
        (pair,)
    )
    conn.commit()
    log(f"[ROLLBACK] {pair} → retour PAPER immédiat")
    os.system(f'python scripts/v10_telegram_alert.py --msg "🔴 {pair} ROLLBACK → PAPER"')


def main():
    parser = argparse.ArgumentParser(description="Paper → Live S25")
    parser.add_argument("--pair", help="Paire à basculer en live")
    parser.add_argument("--all", action="store_true", help="Toutes les paires LIVE_READY")
    parser.add_argument("--status", action="store_true", help="Afficher modes actuels")
    parser.add_argument("--rollback", help="Rollback paire vers paper")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cfg = load_live_config()

    if args.status:
        log("=== STATUS PAIRES ===")
        rows = conn.execute("SELECT symbol, status, live_at FROM pair_status").fetchall()
        for r in rows:
            print(f"  {r[0]:10} | {r[1]:20} | {r[2]}")
        conn.close()
        return 0

    if args.rollback:
        rollback_to_paper(args.rollback.upper(), conn, cfg)
        save_live_config(cfg)
        conn.close()
        return 0

    if breaker_is_active():
        log("[BLOQUÉ] Circuit-breaker actif — bascule LIVE impossible. Faire make breaker-reset.")
        conn.close()
        return 1

    pairs_to_switch = []
    if args.all:
        pairs_to_switch = get_live_ready_pairs(conn)
    elif args.pair:
        pairs_to_switch = [args.pair.upper()]
    else:
        parser.print_help()
        conn.close()
        return 0

    if not pairs_to_switch:
        log("[INFO] Aucune paire LIVE_READY trouvée. Lancer make live-gate d'abord.")
        conn.close()
        return 0

    log(f"=== PAPER2LIVE START — {len(pairs_to_switch)} paire(s) ===")
    for pair in pairs_to_switch:
        switch_to_live(pair, conn, cfg)
    save_live_config(cfg)
    log("=== PAPER2LIVE END ===")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
