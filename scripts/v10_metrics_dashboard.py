#!/usr/bin/env python3
"""
v10_metrics_dashboard.py — Dashboard métriques CEO V10
Sprint 24 — Perplexity GitHub MCP — 2026-08-08

Résume en CLI/JSON l'état complet du système V10 :
- WR live (paper_trades)
- WR shadow RL (v10_rl_shadow_log)
- Gates de promotion (4 critères R10)
- Edges actifs (replay batch)
- Watchdog status
- Alertes P0/P1

Doctrine : R1-AGIR, R6 fail-open, R9-AUDIT, R10-CAPITAL (0 order)
"""

import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)

DB_V9 = DATA_DIR / "v9_forces.db"
DB_DECISIONS = DATA_DIR / "v10_decisions.db"
DB_LEARNING = DATA_DIR / "v10_learning_state.db"


def _connect(path: Path):
    """R6 fail-open : retourne None si DB absente."""
    if not path.exists():
        return None
    try:
        return sqlite3.connect(str(path))
    except Exception:
        return None


def get_paper_trades_stats() -> dict:
    """WR live depuis paper_trades (v9_forces.db)."""
    conn = _connect(DB_V9)
    if not conn:
        return {"source": "paper_trades", "status": "DB_ABSENT", "wr": None, "n": 0}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) "
            "FROM paper_trades WHERE is_win IS NOT NULL"
        )
        row = cur.fetchone()
        n, wins = (row[0] or 0), (row[1] or 0)
        wr = round(wins / n, 4) if n > 0 else None
        return {"source": "paper_trades", "status": "OK", "wr": wr, "n": n, "wins": wins}
    except Exception as e:
        return {"source": "paper_trades", "status": f"ERROR:{e}", "wr": None, "n": 0}
    finally:
        conn.close()


def get_rl_shadow_stats() -> dict:
    """WR shadow RL depuis v10_rl_shadow_log (v10_decisions.db)."""
    conn = _connect(DB_DECISIONS)
    if not conn:
        return {"source": "rl_shadow", "status": "DB_ABSENT", "wr_by_pair": {}}
    try:
        cur = conn.cursor()
        # Vérifie que la table existe
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='v10_rl_shadow_log'"
        )
        if not cur.fetchone():
            return {"source": "rl_shadow", "status": "TABLE_ABSENT", "wr_by_pair": {}}
        cur.execute(
            "SELECT pair, COUNT(*), "
            "SUM(CASE WHEN shadow_win=1 THEN 1 ELSE 0 END) "
            "FROM v10_rl_shadow_log "
            "WHERE shadow_win IS NOT NULL "
            "GROUP BY pair"
        )
        rows = cur.fetchall()
        wr_by_pair = {}
        for pair, n, wins in rows:
            wr_by_pair[pair] = {
                "n": n,
                "wins": wins or 0,
                "wr": round((wins or 0) / n, 4) if n > 0 else None
            }
        return {"source": "rl_shadow", "status": "OK", "wr_by_pair": wr_by_pair}
    except Exception as e:
        return {"source": "rl_shadow", "status": f"ERROR:{e}", "wr_by_pair": {}}
    finally:
        conn.close()


def get_active_edges() -> dict:
    """Edges actifs depuis replay batch (dernière table edge_map si disponible)."""
    conn = _connect(DB_DECISIONS)
    if not conn:
        return {"source": "edge_map", "status": "DB_ABSENT", "edges": []}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='v10_edge_map'"
        )
        if not cur.fetchone():
            return {"source": "edge_map", "status": "TABLE_ABSENT", "edges": []}
        cur.execute(
            "SELECT pair, timeframe, direction, wr, n_trades "
            "FROM v10_edge_map WHERE wr >= 0.50 AND n_trades >= 30 "
            "ORDER BY wr DESC LIMIT 20"
        )
        rows = cur.fetchall()
        edges = [
            {"pair": r[0], "tf": r[1], "dir": r[2], "wr": r[3], "n": r[4]}
            for r in rows
        ]
        return {"source": "edge_map", "status": "OK", "edges": edges, "count": len(edges)}
    except Exception as e:
        return {"source": "edge_map", "status": f"ERROR:{e}", "edges": []}
    finally:
        conn.close()


def get_promotion_gates(paper: dict, rl: dict) -> dict:
    """
    4 gates de promotion SHADOW→ACTIVE (R10) :
    1. WR global ≥ 50%
    2. Sharpe ≥ 0.3  (proxy : WR ≥ 55% si Sharpe non dispo)
    3. DD ≤ 50 pips   (non calculé ici → flag N/A)
    4. Consistency ≥ 75% (non calculé ici → flag N/A)
    """
    wr = paper.get("wr")
    gate1 = (wr is not None and wr >= 0.50)
    gate2 = (wr is not None and wr >= 0.55)  # proxy Sharpe
    gates = {
        "G1_WR_50": {"pass": gate1, "value": wr},
        "G2_SHARPE_proxy": {"pass": gate2, "value": wr},
        "G3_DD": {"pass": None, "value": "N/A — calculer depuis paper_trades"},
        "G4_CONSISTENCY": {"pass": None, "value": "N/A — calculer depuis paper_trades"},
    }
    passed = sum(1 for g in gates.values() if g["pass"] is True)
    return {"gates": gates, "passed": passed, "total": 4,
            "verdict": "CANDIDAT_ACTIVE" if passed >= 4 else f"HOLD ({passed}/4)"}


def run_dashboard() -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    paper = get_paper_trades_stats()
    rl = get_rl_shadow_stats()
    edges = get_active_edges()
    promo = get_promotion_gates(paper, rl)

    # Alertes P0/P1
    alerts = []
    if paper.get("wr") is not None and paper["wr"] < 0.45:
        alerts.append({"level": "P0", "msg": f"WR live critique : {paper['wr']*100:.1f}%"})
    if promo["passed"] < 2:
        alerts.append({"level": "P1", "msg": "Promotion SHADOW bloquée (<2 gates)"})
    if edges.get("count", 0) < 5:
        alerts.append({"level": "P1", "msg": "Edges actifs insuffisants (<5)"})

    report = {
        "timestamp": ts,
        "sprint": "S24",
        "paper_trades": paper,
        "rl_shadow": rl,
        "active_edges": edges,
        "promotion": promo,
        "alerts": alerts,
        "doctrine": "R1-AGIR R6-fail-open R9-AUDIT R10-CAPITAL",
    }

    # Sauvegarde rapport
    out = REPORTS_DIR / f"v10_metrics_dashboard_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Affichage CLI CEO
    print("\n" + "="*60)
    print(f"📊 V10 METRICS DASHBOARD — {ts}")
    print("="*60)
    print(f"\n📈 Paper Trades : WR={paper.get('wr','N/A')} n={paper.get('n',0)}")
    rl_pairs = rl.get("wr_by_pair", {})
    if rl_pairs:
        print("\n🤖 RL Shadow WR par paire :")
        for pair, d in rl_pairs.items():
            print(f"   {pair}: WR={d['wr']} n={d['n']}")
    print(f"\n⚡ Edges actifs ≥50% : {edges.get('count','N/A')}")
    for e in edges.get("edges", [])[:5]:
        print(f"   {e['pair']} {e['tf']} {e['dir']} WR={e['wr']} n={e['n']}")
    print(f"\n🎯 Promotion : {promo['verdict']} ({promo['passed']}/4 gates)")
    for gname, g in promo["gates"].items():
        status = "✅" if g["pass"] else ("❌" if g["pass"] is False else "⬜")
        print(f"   {status} {gname}: {g['value']}")
    if alerts:
        print("\n🚨 Alertes :")
        for a in alerts:
            print(f"   [{a['level']}] {a['msg']}")
    else:
        print("\n✅ Aucune alerte active")
    print(f"\n💾 Rapport : {out}")
    print("="*60 + "\n")

    return report


if __name__ == "__main__":
    run_dashboard()
