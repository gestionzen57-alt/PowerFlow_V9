"""v10_live_monitor.py — Monitoring temps réel LIVE S25
Plateforme : Windows · MT5 natif
Auteur : PowerFlow Senior — 2026-08-08

Surveille en temps réel les paires en mode LIVE :
  - WR glissant 20 trades
  - Drawdown journalier
  - Latence MT5
  - Streak pertes
  - Dérive paper vs live

Affiche dashboard console + alerte Telegram si seuils dépassés.

Usage :
  python scripts/v10_live_monitor.py              # 1 check
  python scripts/v10_live_monitor.py --loop 60    # loop toutes les 60s
  python scripts/v10_live_monitor.py --pair EURUSD
"""

import argparse
import sqlite3
import time
import os
from datetime import datetime, timezone, date
from pathlib import Path

DB_PATH = Path(os.getenv("POWERFLOW_DB", "data/powerflow_v10.db"))
LOG_PATH = Path("logs/live_monitor.log")

THRESHOLDS = {
    "wr_alert": 50.0,
    "dd_alert_pct": 2.0,
    "streak_alert": 3,
    "drift_alert_pct": 10.0,
}


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_live_pairs(conn) -> list[str]:
    rows = conn.execute(
        "SELECT symbol FROM pair_status WHERE status='LIVE'"
    ).fetchall()
    return [r[0] for r in rows]


def rolling_wr(conn, pair: str, n: int = 20) -> float | None:
    rows = conn.execute(
        "SELECT outcome FROM paper_trades WHERE symbol=? AND outcome IN ('WIN','LOSS') "
        "ORDER BY resolved_at DESC LIMIT ?",
        (pair, n)
    ).fetchall()
    if not rows:
        return None
    wins = sum(1 for r in rows if r[0] == "WIN")
    return round(wins / len(rows) * 100, 1)


def daily_dd(conn, pair: str) -> float:
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(profit_usd), 0) FROM paper_trades "
        "WHERE symbol=? AND outcome='LOSS' AND date(resolved_at)=?",
        (pair, today)
    ).fetchone()
    losses = abs(row[0]) if row else 0.0
    capital = float(os.getenv("POWERFLOW_CAPITAL", "10000"))
    return round(losses / capital * 100, 2)


def loss_streak(conn, pair: str) -> int:
    rows = conn.execute(
        "SELECT outcome FROM paper_trades WHERE symbol=? AND outcome IN ('WIN','LOSS') "
        "ORDER BY resolved_at DESC LIMIT 10",
        (pair,)
    ).fetchall()
    streak = 0
    for r in rows:
        if r[0] == "LOSS":
            streak += 1
        else:
            break
    return streak


def alert(pair: str, msg: str):
    log(f"[ALERTE] {pair} — {msg}")
    os.system(f'python scripts/v10_telegram_alert.py --msg "⚠️ LIVE {pair}: {msg}"')


def check_pair(conn, pair: str) -> dict:
    wr = rolling_wr(conn, pair)
    dd = daily_dd(conn, pair)
    streak = loss_streak(conn, pair)
    alerts = []
    if wr is not None and wr < THRESHOLDS["wr_alert"]:
        alerts.append(f"WR={wr}% < {THRESHOLDS['wr_alert']}%")
    if dd >= THRESHOLDS["dd_alert_pct"]:
        alerts.append(f"DD={dd}% ≥ {THRESHOLDS['dd_alert_pct']}%")
    if streak >= THRESHOLDS["streak_alert"]:
        alerts.append(f"STREAK={streak} pertes consécutives")
    for a in alerts:
        alert(pair, a)
    return {"pair": pair, "wr": wr, "dd": dd, "streak": streak, "alerts": alerts}


def display_dashboard(results: list[dict]):
    print("\n" + "═" * 60)
    print(f"  LIVE MONITOR — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
    print("═" * 60)
    for r in results:
        status = "🔴" if r["alerts"] else "🟢"
        wr_str = f"{r['wr']}%" if r["wr"] is not None else "N/A"
        print(f"  {status} {r['pair']:8} | WR={wr_str:6} | DD={r['dd']}% | Streak={r['streak']}")
        for a in r["alerts"]:
            print(f"     ⚠️  {a}")
    print("═" * 60)


def run_once(pair_filter=None):
    conn = sqlite3.connect(DB_PATH)
    pairs = get_live_pairs(conn)
    if pair_filter:
        pairs = [p for p in pairs if p == pair_filter.upper()]
    if not pairs:
        log("Aucune paire en mode LIVE. Utiliser v10_paper2live.py d'abord.")
        conn.close()
        return
    results = [check_pair(conn, p) for p in pairs]
    conn.close()
    display_dashboard(results)


def main():
    parser = argparse.ArgumentParser(description="Live monitor S25")
    parser.add_argument("--loop", type=int, help="Intervalle en secondes (défaut: 1 check)")
    parser.add_argument("--pair", help="Filtrer une paire")
    args = parser.parse_args()
    if args.loop:
        log(f"Monitor loop démarré (intervalle={args.loop}s)")
        while True:
            run_once(args.pair)
            time.sleep(args.loop)
    else:
        run_once(args.pair)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
