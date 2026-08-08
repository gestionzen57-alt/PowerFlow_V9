"""v10_live_gate.py — Gate de passage paper → live réel S25
Plateforme : Windows · MT5 natif
Auteur : PowerFlow Senior — 2026-08-08

Vérifie tous les critères GO/NO-GO (G1-G4) par paire
et génère un rapport JSON + log CEO.

Usage :
  python scripts/v10_live_gate.py               # check toutes les paires
  python scripts/v10_live_gate.py --pair EURUSD # check une paire
  python scripts/v10_live_gate.py --promote     # marque GO les paires validées
"""

import argparse
import sqlite3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("POWERFLOW_DB", "data/powerflow_v10.db"))
GATE_REPORT = Path("data/live_gate_report.json")
LOG_PATH = Path("logs/live_gate.log")

PAIRS = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD"]

CRITERIA = {
    "G1_min_trades": 20,
    "G2_wr_delta_min": 0.0,
    "G3_wr_min": 55.0,
    "G3_trades_min": 60,
    "G3_sharpe_min": 0.3,
    "G4_outside_block": True,
}


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_g1(conn, pair) -> tuple[bool, dict]:
    """G1 : ≥20 trades consécutifs validés shadow."""
    n = conn.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE symbol=? AND outcome IN ('WIN','LOSS')",
        (pair,)
    ).fetchone()[0]
    ok = n >= CRITERIA["G1_min_trades"]
    return ok, {"trades": n, "min": CRITERIA["G1_min_trades"]}


def check_g2(conn, pair) -> tuple[bool, dict]:
    """G2 : WR shadow ≥ baseline (delta ≥ 0)."""
    total = conn.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE symbol=? AND outcome IN ('WIN','LOSS')",
        (pair,)
    ).fetchone()[0]
    if total == 0:
        return False, {"wr": 0, "delta": None}
    wins = conn.execute(
        "SELECT COUNT(*) FROM paper_trades WHERE symbol=? AND outcome='WIN'",
        (pair,)
    ).fetchone()[0]
    wr = round(wins / total * 100, 1)
    baseline = float(conn.execute(
        "SELECT COALESCE(AVG(baseline_wr), 55.0) FROM paire_baselines WHERE symbol=?",
        (pair,)
    ).fetchone()[0] or 55.0)
    delta = round(wr - baseline, 1)
    return delta >= CRITERIA["G2_wr_delta_min"], {"wr": wr, "baseline": baseline, "delta": delta}


def check_g3(conn, pair) -> tuple[bool, dict]:
    """G3 : Walkforward WR≥55%, n≥60, Sharpe≥0.3."""
    row = conn.execute(
        "SELECT wr_pct, n_trades, proxy_sharpe FROM walkforward_results WHERE symbol=? "
        "ORDER BY computed_at DESC LIMIT 1",
        (pair,)
    ).fetchone()
    if not row:
        return False, {"status": "pas de données walkforward"}
    wr, n, sharpe = row
    ok = (wr >= CRITERIA["G3_wr_min"] and
          n >= CRITERIA["G3_trades_min"] and
          sharpe >= CRITERIA["G3_sharpe_min"])
    return ok, {"wr": wr, "n": n, "sharpe": sharpe}


def check_g4(conn, pair) -> tuple[bool, dict]:
    """G4 : Pas de session OUTSIDE bloquante."""
    blocked = conn.execute(
        "SELECT COUNT(*) FROM thompson_sessions WHERE symbol=? AND session='OUTSIDE' AND wr_pct < 40",
        (pair,)
    ).fetchone()[0]
    ok = blocked == 0
    return ok, {"outside_blocked": blocked}


def evaluate_pair(conn, pair: str) -> dict:
    g1_ok, g1_data = check_g1(conn, pair)
    g2_ok, g2_data = check_g2(conn, pair)
    g3_ok, g3_data = check_g3(conn, pair)
    g4_ok, g4_data = check_g4(conn, pair)
    go = g1_ok and g2_ok and g3_ok and g4_ok
    return {
        "pair": pair,
        "GO": go,
        "G1": {"ok": g1_ok, **g1_data},
        "G2": {"ok": g2_ok, **g2_data},
        "G3": {"ok": g3_ok, **g3_data},
        "G4": {"ok": g4_ok, **g4_data},
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def promote_pair(conn, pair: str):
    """Marque la paire comme LIVE_READY dans la DB."""
    conn.execute(
        "INSERT OR REPLACE INTO pair_status (symbol, status, promoted_at) VALUES (?,?,?)",
        (pair, "LIVE_READY", datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    log(f"[PROMOTE] {pair} → LIVE_READY")


def main():
    parser = argparse.ArgumentParser(description="Live gate S25 — GO/NO-GO par paire")
    parser.add_argument("--pair", help="Paire spécifique (défaut: toutes)")
    parser.add_argument("--promote", action="store_true", help="Marquer GO en DB")
    args = parser.parse_args()

    pairs = [args.pair.upper()] if args.pair else PAIRS
    conn = sqlite3.connect(DB_PATH)
    results = []

    log("=== LIVE GATE S25 START ===")
    for pair in pairs:
        r = evaluate_pair(conn, pair)
        results.append(r)
        verdict = "✅ GO" if r["GO"] else "❌ NO-GO"
        log(f"[{pair}] {verdict} | G1={r['G1']['ok']} G2={r['G2']['ok']} G3={r['G3']['ok']} G4={r['G4']['ok']}")
        if r["GO"] and args.promote:
            promote_pair(conn, pair)

    conn.close()
    GATE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    GATE_REPORT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Rapport écrit : {GATE_REPORT}")
    log("=== LIVE GATE S25 END ===")
    go_count = sum(1 for r in results if r["GO"])
    log(f"Résumé : {go_count}/{len(results)} paires GO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
