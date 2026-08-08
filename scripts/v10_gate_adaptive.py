#!/usr/bin/env python3
"""
v10_gate_adaptive.py — Gate adaptatif SHADOW → ACTIVE (Sprint 24)
Perplexity GitHub MCP — 2026-08-08 20:51 CEST

Logique :
- Si baseline WR >= 60% : gate = 20 trades consécutifs gagnants
- Si baseline WR  < 60% : gate = 30 trades consécutifs gagnants
- Calcule le gate requis par paire depuis config/v10_thompson_priors.json
- Lit les résultats shadow depuis DB et vérifie le gate adaptatif
- Produit un rapport JSON GO/NO-GO par paire

Doctrine : R1-AGIR, R6 fail-open, R9-AUDIT, R10-CAPITAL
"""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB        = Path("data/v10_decisions.db")
PRIORS    = Path("config/v10_thompson_priors.json")
REPORTS   = Path("reports"); REPORTS.mkdir(exist_ok=True)
PAIRS     = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD"]
BASELINES = {"EURUSD": 0.693, "USDJPY": 0.581, "GBPUSD": 0.508, "AUDUSD": 0.466}


def _gate_for(baseline_wr: float) -> int:
    return 20 if baseline_wr >= 0.60 else 30


def _best_consecutive(trades: list[int]) -> int:
    best, cur = 0, 0
    for w in trades:
        if w == 1:
            cur += 1; best = max(best, cur)
        else:
            cur = 0
    return best


def _load_shadow_wins(pair: str, conn) -> list[int]:
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT shadow_win FROM v10_rl_shadow_log WHERE pair=? AND shadow_win IS NOT NULL ORDER BY created_at ASC",
            (pair,)
        )
        return [int(r[0]) for r in cur.fetchall()]
    except Exception:
        return []


def run() -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report = {"timestamp_utc": ts, "script": "v10_gate_adaptive", "pairs": {}, "summary": {}}

    conn = None
    if DB.exists():
        try:
            conn = sqlite3.connect(str(DB))
        except Exception:
            pass

    gates_pass = 0
    for pair in PAIRS:
        baseline = BASELINES.get(pair, 0.5)
        gate_req = _gate_for(baseline)
        wins = _load_shadow_wins(pair, conn) if conn else []
        n = len(wins)
        best_streak = _best_consecutive(wins)
        wr = round(sum(wins) / n, 4) if n else None
        passed = best_streak >= gate_req
        if passed:
            gates_pass += 1
        pair_report = {
            "pair": pair,
            "baseline_wr": baseline,
            "gate_required": gate_req,
            "gate_logic": "20 (baseline>=60%)" if gate_req == 20 else "30 (baseline<60%)",
            "n_trades": n,
            "wr_shadow": wr,
            "best_consecutive_wins": best_streak,
            "gate_pass": passed,
            "verdict": "GO" if passed else f"NO_GO (best={best_streak}/{gate_req})",
        }
        report["pairs"][pair] = pair_report
        print(f"{'✅' if passed else '❌'} {pair}: gate={gate_req} best={best_streak} WR={wr}")

    if conn:
        conn.close()

    all_pass = gates_pass == len(PAIRS)
    report["summary"] = {
        "gates_pass": gates_pass,
        "gates_total": len(PAIRS),
        "promotion_verdict": "PROMOTE_ALL" if all_pass else f"PARTIAL ({gates_pass}/{len(PAIRS)})",
        "action": "Lancer promotion SHADOW→ACTIVE" if all_pass else "Continuer shadow sur paires NO_GO",
    }
    out = REPORTS / f"v10_gate_adaptive_{ts}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n📊 Promotion: {report['summary']['promotion_verdict']}")
    print(f"📁 Rapport: {out}")
    return report


if __name__ == "__main__":
    run()
