#!/usr/bin/env python3
"""
v10_sprint_report.py — Rapport Telegram hebdo CEO (Sprint 24+)
Perplexity GitHub MCP — 2026-08-08 20:45 CEST

Résume en Markdown Telegram :
 - Gates RL promotion (G1-G4)
 - WR live paper_trades
 - Top 5 edges actifs
 - Alertes P0/P1
 - Prochain milestone Sprint

Doctrine : R1-AGIR, R6 fail-open, R9-AUDIT, R10-CAPITAL
"""
from __future__ import annotations
import json, sqlite3, os
from datetime import datetime, timezone
from pathlib import Path

DB_V9       = Path("data/v9_forces.db")
DB_DEC      = Path("data/v10_decisions.db")
REPORTS     = Path("reports"); REPORTS.mkdir(exist_ok=True)

TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID  = os.getenv("TELEGRAM_CHAT_ID", "")


def _q(db: Path, sql: str, params=()) -> list:
    if not db.exists(): return []
    try:
        with sqlite3.connect(str(db)) as c:
            return c.execute(sql, params).fetchall()
    except Exception:
        return []


def build_report() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Paper WR
    row = _q(DB_V9, "SELECT COUNT(*), SUM(CASE WHEN is_win=1 THEN 1 ELSE 0 END) FROM paper_trades WHERE is_win IS NOT NULL")
    n_p, w_p = (row[0][0] or 0, row[0][1] or 0) if row else (0, 0)
    wr_p = round(w_p/n_p*100, 1) if n_p else None
    # RL shadow par paire
    rl_rows = _q(DB_DEC,
        "SELECT pair, COUNT(*), SUM(CASE WHEN shadow_win=1 THEN 1 ELSE 0 END) "
        "FROM v10_rl_shadow_log WHERE shadow_win IS NOT NULL GROUP BY pair")
    rl_lines = []
    gates_pass = 0
    BASELINE = {"GBPUSD": 0.508, "AUDUSD": 0.466, "EURUSD": 0.693, "USDJPY": 0.581}
    for pair, n, w in rl_rows:
        wr = round((w or 0)/n, 3) if n else None
        base = BASELINE.get(pair, 0.5)
        ok = wr is not None and wr >= base
        if ok: gates_pass += 1
        rl_lines.append(f"  {'\u2705' if ok else '\u274c'} {pair}: shadow {wr*100:.1f}% (base {base*100:.1f}%)" if wr else f"  ❓ {pair}: N/A")
    # Top edges
    edges = _q(DB_DEC,
        "SELECT pair, timeframe, direction, wr FROM v10_edge_map WHERE wr>=0.50 AND n_trades>=30 ORDER BY wr DESC LIMIT 5")
    edge_lines = [f"  {r[0]} {r[1]} {r[2]} → {r[3]*100:.1f}%" for r in edges] or ["  Aucun edge disponible"]
    # Alertes
    alerts = []
    if wr_p is not None and wr_p < 45: alerts.append("🚨 P0 WR live critique")
    if gates_pass < 2: alerts.append("🚨 P1 Gates RL insuffisants")
    if not edges: alerts.append("🚨 P1 Pas d'edge en DB")
    # Construction message
    lines = [
        f"📊 *V10 Sprint Report* — {ts}",
        "",
        f"📈 *Paper Trades* : WR={wr_p}% n={n_p}",
        "",
        f"🤖 *RL Shadow* ({gates_pass}/4 gates passés) :",
        *rl_lines,
        "",
        f"⚡ *Top Edges actifs* :",
        *edge_lines,
    ]
    if alerts:
        lines += ["", "🚨 *Alertes* :", *[f"  {a}" for a in alerts]]
    else:
        lines += ["", "✅ Aucune alerte active"]
    lines += ["", "🎯 *Prochain milestone* : 4/4 gates RL → promotion SHADOW→ACTIVE"]
    return "\n".join(lines)


def send_telegram(msg: str) -> bool:
    if not TOKEN or not CHAT_ID: return False
    try:
        import urllib.request, urllib.parse
        payload = json.dumps({"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"[Telegram] WARN: {e}")
        return False


def main() -> None:
    msg = build_report()
    print(msg)
    sent = send_telegram(msg)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = REPORTS / f"v10_sprint_report_{ts}.txt"
    out.write_text(msg, encoding="utf-8")
    print(f"\n[Telegram] sent={sent}")
    print(f"[Rapport] {out}")


if __name__ == "__main__":
    main()
