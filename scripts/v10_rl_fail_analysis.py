#!/usr/bin/env python3
"""
v10_rl_fail_analysis.py — Analyse des trades shadow perdants EURUSD + USDJPY
Sprint 24 — Perplexity GitHub MCP — 2026-08-08 20:45 CEST

Lit v10_rl_shadow_log depuis v10_decisions.db.
Détecte les patterns d'échec : session, heure UTC, action, série perdante.
Produit un rapport JSON + CLI pour décision CEO.

Doctrine : R1-AGIR, R6 fail-open, R9-AUDIT, R10-CAPITAL
"""
from __future__ import annotations
import json, sqlite3, math, collections
from datetime import datetime, timezone
from pathlib import Path

DB = Path("data/v10_decisions.db")
REPORTS = Path("reports"); REPORTS.mkdir(exist_ok=True)
PAIRS = ["EURUSD", "USDJPY"]
ICT_SESSIONS = {
    "ASIAN":  (0,  8),
    "LONDON": (7, 13),
    "NY":     (12, 17),
    "OUTSIDE":(17, 24),
}


def _session(hour: int) -> str:
    for name, (s, e) in ICT_SESSIONS.items():
        if s <= hour < e:
            return name
    return "OUTSIDE"


def _conn():
    if not DB.exists(): return None
    try: return sqlite3.connect(str(DB))
    except: return None


def analyse_pair(pair: str, conn) -> dict:
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='v10_rl_shadow_log'")
        if not cur.fetchone():
            return {"pair": pair, "status": "TABLE_ABSENT"}
        cur.execute(
            "SELECT created_at, action, shadow_win, baseline_win FROM v10_rl_shadow_log "
            "WHERE pair=? ORDER BY created_at ASC",
            (pair,)
        )
        rows = cur.fetchall()
        if not rows:
            return {"pair": pair, "status": "NO_DATA", "n": 0}

        n_total = len(rows)
        losses = [r for r in rows if r[2] == 0]
        n_loss = len(losses)
        wr = round(1 - n_loss/n_total, 4) if n_total else None

        # Distribution par session
        session_dist: dict[str, dict] = {s: {"total":0, "wins":0} for s in ICT_SESSIONS}
        for ts_str, action, sw, bw in rows:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z","+00:00"))
                h = dt.hour
            except Exception:
                h = 0
            s = _session(h)
            if s not in session_dist:
                session_dist[s] = {"total":0, "wins":0}
            session_dist[s]["total"] += 1
            if sw == 1:
                session_dist[s]["wins"] += 1
        session_wr = {}
        for s, d in session_dist.items():
            if d["total"] > 0:
                session_wr[s] = {"wr": round(d["wins"]/d["total"],3), "n": d["total"]}

        # Pire série perdante
        worst_streak, cur_streak = 0, 0
        for _, _, sw, _ in rows:
            if sw == 0:
                cur_streak += 1
                worst_streak = max(worst_streak, cur_streak)
            else:
                cur_streak = 0

        # Distribution par action
        action_wr = collections.defaultdict(lambda: {"n":0,"wins":0})
        for _, act, sw, _ in rows:
            action_wr[act]["n"] += 1
            if sw == 1: action_wr[act]["wins"] += 1
        action_summary = {a: {"wr": round(d["wins"]/d["n"],3), "n": d["n"]} for a, d in action_wr.items()}

        # Gate 30 consécutifs
        best_streak, cur_s = 0, 0
        for _, _, sw, _ in rows:
            if sw == 1: cur_s+=1; best_streak=max(best_streak,cur_s)
            else: cur_s=0

        # Recommandation
        worst_session = min(session_wr, key=lambda s: session_wr[s]["wr"]) if session_wr else None
        reco = []
        if worst_session and session_wr[worst_session]["wr"] < 0.40:
            reco.append(f"Filtrer session {worst_session} (WR={session_wr[worst_session]['wr']})") 
        if worst_streak >= 8:
            reco.append(f"Série perdante max {worst_streak} — envisager circuit-breaker")
        if wr is not None and wr < 0.50:
            reco.append("WR global shadow < 50% — revoir hyperparam Thompson")
        if not reco:
            reco.append("Aucun pattern critique — gate 30-consécutifs suffit")

        return {
            "pair": pair, "status": "OK",
            "n_total": n_total, "n_loss": n_loss, "wr_shadow": wr,
            "gate_30_best_streak": best_streak, "gate_30_pass": best_streak >= 30,
            "worst_loss_streak": worst_streak,
            "session_wr": session_wr,
            "action_wr": action_summary,
            "recommendations": reco,
        }
    except Exception as e:
        return {"pair": pair, "status": "ERROR", "error": str(e)}


def main() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    conn = _conn()
    report = {"timestamp_utc": ts, "script": "v10_rl_fail_analysis", "pairs": {}}
    if not conn:
        report["status"] = "DB_ABSENT"
    else:
        for pair in PAIRS:
            result = analyse_pair(pair, conn)
            report["pairs"][pair] = result
            print(f"\n--- {pair} ---")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        conn.close()
        passed = sum(1 for p in report["pairs"].values() if p.get("gate_30_pass"))
        report["summary"] = {"pairs_gate_passed": passed, "pairs_total": len(PAIRS),
                             "verdict": "GATES_OK" if passed==len(PAIRS) else f"NEED_WORK ({passed}/{len(PAIRS)})"}
    out = Path("reports") / f"v10_rl_fail_analysis_{ts}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n[Rapport] {out}")


if __name__ == "__main__":
    main()
