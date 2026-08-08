"""v10_circuit_breaker.py — Circuit-breaker LIVE S25
Plateforme : Windows · MT5 natif
Auteur : PowerFlow Senior — 2026-08-08

Déclenche un arrêt immédiat de tous les ordres live si :
  - Drawdown journalier ≥ seuil_dd (défaut 3%)
  - Pertes consécutives ≥ seuil_streak (défaut 5)
  - Latence MT5 > seuil_latency_ms (défaut 800ms)
  - Écart WR live vs paper > seuil_drift (défaut 15%)

Usage :
  python scripts/v10_circuit_breaker.py --check      # vérification seule
  python scripts/v10_circuit_breaker.py --enforce    # applique les règles
  python scripts/v10_circuit_breaker.py --status     # état du breaker
  python scripts/v10_circuit_breaker.py --reset      # reset manuel (CEO only)
"""

import argparse
import sqlite3
import json
import os
import sys
from datetime import datetime, timezone, date
from pathlib import Path

DB_PATH = Path(os.getenv("POWERFLOW_DB", "data/powerflow_v10.db"))
BREAKER_STATE = Path("data/circuit_breaker_state.json")
LOG_PATH = Path("logs/circuit_breaker.log")

DEFAULT_CONFIG = {
    "seuil_dd_pct": 3.0,
    "seuil_streak": 5,
    "seuil_latency_ms": 800,
    "seuil_drift_pct": 15.0,
}


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if BREAKER_STATE.exists():
        return json.loads(BREAKER_STATE.read_text(encoding="utf-8"))
    return {"triggered": False, "reason": None, "triggered_at": None, "reset_at": None}


def save_state(state: dict):
    BREAKER_STATE.parent.mkdir(parents=True, exist_ok=True)
    BREAKER_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def get_daily_dd(conn: sqlite3.Connection) -> float:
    """Drawdown journalier en % du capital initial (approximé sur paper_trades)."""
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(profit_usd), 0) FROM paper_trades "
        "WHERE outcome='LOSS' AND date(resolved_at)=?",
        (today,)
    ).fetchone()
    losses = abs(row[0]) if row else 0.0
    capital = float(os.getenv("POWERFLOW_CAPITAL", "10000"))
    return round(losses / capital * 100, 2)


def get_loss_streak(conn: sqlite3.Connection) -> int:
    """Nombre de pertes consécutives les plus récentes."""
    rows = conn.execute(
        "SELECT outcome FROM paper_trades WHERE outcome IN ('WIN','LOSS') "
        "ORDER BY resolved_at DESC LIMIT 20"
    ).fetchall()
    streak = 0
    for r in rows:
        if r[0] == "LOSS":
            streak += 1
        else:
            break
    return streak


def get_live_vs_paper_drift(conn: sqlite3.Connection) -> float:
    """Écart WR live vs paper (approximé depuis paper_trades mode native vs paper)."""
    def wr(mode_filter):
        total = conn.execute(
            f"SELECT COUNT(*) FROM paper_trades WHERE outcome IN ('WIN','LOSS') {mode_filter}"
        ).fetchone()[0]
        if total == 0:
            return None
        wins = conn.execute(
            f"SELECT COUNT(*) FROM paper_trades WHERE outcome='WIN' {mode_filter}"
        ).fetchone()[0]
        return wins / total * 100
    wr_live = wr("AND resolve_mode='native'")
    wr_paper = wr("AND (resolve_mode IS NULL OR resolve_mode='paper')")
    if wr_live is None or wr_paper is None:
        return 0.0
    return round(abs(wr_live - wr_paper), 2)


def send_telegram_alert(msg: str):
    """Appel externe au notifier Telegram."""
    alert_script = Path("scripts/v10_telegram_alert.py")
    if alert_script.exists():
        os.system(f'python {alert_script} --msg "{msg}"')


def check_all(conn: sqlite3.Connection, config: dict) -> list[dict]:
    triggers = []
    dd = get_daily_dd(conn)
    if dd >= config["seuil_dd_pct"]:
        triggers.append({"rule": "DRAWDOWN", "value": dd, "seuil": config["seuil_dd_pct"]})
    streak = get_loss_streak(conn)
    if streak >= config["seuil_streak"]:
        triggers.append({"rule": "STREAK_LOSS", "value": streak, "seuil": config["seuil_streak"]})
    drift = get_live_vs_paper_drift(conn)
    if drift >= config["seuil_drift_pct"]:
        triggers.append({"rule": "WR_DRIFT", "value": drift, "seuil": config["seuil_drift_pct"]})
    return triggers


def main():
    parser = argparse.ArgumentParser(description="Circuit-breaker LIVE S25")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        log(f"=== CIRCUIT-BREAKER STATUS ===")
        log(f"Triggered : {state['triggered']}")
        log(f"Raison    : {state['reason']}")
        log(f"Depuis    : {state['triggered_at']}")
        return 0

    if args.reset:
        state = {"triggered": False, "reason": None, "triggered_at": None,
                 "reset_at": datetime.now(timezone.utc).isoformat()}
        save_state(state)
        log("[RESET] Circuit-breaker réinitialisé par CEO.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    try:
        triggers = check_all(conn, DEFAULT_CONFIG)
    finally:
        conn.close()

    if not triggers:
        log("[OK] Aucun déclencheur actif. Système nominal.")
        return 0

    reasons = " | ".join(f"{t['rule']}={t['value']}" for t in triggers)
    log(f"[ALERTE] Déclencheurs : {reasons}")

    if args.enforce:
        state["triggered"] = True
        state["reason"] = reasons
        state["triggered_at"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        msg = f"🚨 CIRCUIT-BREAKER ACTIF — {reasons} — Tous ordres suspendus"
        log(msg)
        send_telegram_alert(msg)
        return 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
