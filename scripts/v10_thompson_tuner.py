#!/usr/bin/env python3
"""
v10_thompson_tuner.py — Réglage Thompson Sampling par session ICT
Sprint 24 — Perplexity GitHub MCP — 2026-08-08 20:51 CEST

Objectif :
- Lire les résultats shadow par session (ASIAN/LONDON/NY/OUTSIDE)
- Recalculer alpha/beta Thompson par session et par paire
- Persister dans config/v10_thompson_priors.json
- Activer le filtre session OUTSIDE si WR < 0.40

Doctrine : R1-AGIR, R6 fail-open, R8-RECALIBRATION, R9-AUDIT, R10-CAPITAL
"""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB       = Path("data/v10_decisions.db")
OUT_CFG  = Path("config/v10_thompson_priors.json")
OUT_RPT  = Path("reports")
PAIRS    = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD"]
SESSIONS = {"ASIAN": (0, 8), "LONDON": (7, 13), "NY": (12, 17), "OUTSIDE": (17, 24)}
MIN_WR_SESSION = 0.40   # seuil filtre automatique OUTSIDE
OUT_RPT.mkdir(exist_ok=True)
Path("config").mkdir(exist_ok=True)


def _session(hour: int) -> str:
    for name, (s, e) in SESSIONS.items():
        if s <= hour < e:
            return name
    return "OUTSIDE"


def _load_shadow_by_session(pair: str, conn) -> dict:
    """Retourne {session: {wins, total}} depuis v10_rl_shadow_log."""
    result = {s: {"wins": 0, "total": 0} for s in SESSIONS}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT created_at, shadow_win FROM v10_rl_shadow_log WHERE pair=? AND shadow_win IS NOT NULL",
            (pair,)
        )
        for ts_str, sw in cur.fetchall():
            try:
                h = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).hour
            except Exception:
                h = 0
            s = _session(h)
            if s not in result:
                result[s] = {"wins": 0, "total": 0}
            result[s]["total"] += 1
            if sw == 1:
                result[s]["wins"] += 1
    except Exception:
        pass
    return result


def _compute_prior(wins: int, total: int, strength: float = 4.0) -> dict:
    """Beta distribution prior : alpha=wins*strength+1, beta=(total-wins)*strength+1."""
    alpha = max(1.0, wins * strength + 1)
    beta  = max(1.0, (total - wins) * strength + 1)
    wr    = round(wins / total, 4) if total else None
    return {"alpha": round(alpha, 2), "beta": round(beta, 2), "wr": wr, "n": total}


def tune() -> dict:
    ts  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    cfg = {"timestamp_utc": ts, "pairs": {}, "filters_applied": []}

    if not DB.exists():
        cfg["status"] = "DB_ABSENT"
        return cfg

    try:
        conn = sqlite3.connect(str(DB))
    except Exception as e:
        cfg["status"] = "DB_ERROR"; cfg["error"] = str(e)
        return cfg

    for pair in PAIRS:
        sessions = _load_shadow_by_session(pair, conn)
        pair_cfg = {}
        for sess, data in sessions.items():
            prior = _compute_prior(data["wins"], data["total"])
            filtered = bool(prior["wr"] is not None and prior["wr"] < MIN_WR_SESSION)
            pair_cfg[sess] = {**prior, "filtered": filtered}
            if filtered:
                cfg["filters_applied"].append(f"{pair}:{sess} WR={prior['wr']}")
        cfg["pairs"][pair] = pair_cfg
    conn.close()

    # Persistance config
    OUT_CFG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    # Rapport
    rpt = OUT_RPT / f"v10_thompson_tuner_{ts}.json"
    rpt.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    cfg["status"] = "OK"
    print(json.dumps({"filters": cfg["filters_applied"], "config": str(OUT_CFG)}, indent=2))
    return cfg


if __name__ == "__main__":
    tune()
