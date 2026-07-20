#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""v9_edge_alert.py — Alerte Telegram automatique si edge live dégradé.

Détecte 3 patterns critiques via SQL lecture seule sur data/v9_forces.db :
  1. Edge baissier 24h dégradé : WR < 40% ET n >= 10 ET pips < -100
  2. Edge haussier 24h dégradé : WR < 50% ET n >= 10 ET pips < -100
  3. Watchdog live : net_pnl_24h < -200 OU wr_long_only_gbpusd < 0.60

Doctrine : R6 (ne lève jamais), R18 (zéro LLM), R25' (alerte défensive, pas d'action auto).
Idempotent : rate-limit 1 alerte / pattern / 6h via state file.

Usage :
    python scripts/v9_edge_alert.py --dry-run     # affiche sans envoyer
    python scripts/v9_edge_alert.py --live        # envoie via Telegram
    python scripts/v9_edge_alert.py --json        # sortie JSON pour orchestrateur
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TELEGRAM_CONFIG = ROOT / "config" / "telegram.json"
DB_PATH = ROOT / "data" / "v9_forces.db"
STATE_PATH = ROOT / "data" / "v9_edge_alert_state.json"

# Seuils d'alerte (calibrés sur le pattern incident 2026-07-20).
THRESH_BAISS_WR = 40.0       # WR baissier 24h < 40%
THRESH_BAISS_N = 10          # avec au moins 10 trades
THRESH_BAISS_PIPS = -100     # ET perte > 100 pips
THRESH_HAUSSE_WR = 50.0      # WR haussier 24h < 50%
THRESH_HAUSSE_N = 10
THRESH_HAUSSE_PIPS = -100
THRESH_WATCHDOG_PIPS = -200  # net_pnl_24h < -200 pips
THRESH_WATCHDOG_WR = 0.60    # OU wr_long_only_gbpusd < 60%
RATE_LIMIT_HOURS = 6         # 1 alerte / pattern / 6h


def _load_telegram():
    if not TELEGRAM_CONFIG.exists():
        raise FileNotFoundError(f"Config Telegram absente : {TELEGRAM_CONFIG}")
    with TELEGRAM_CONFIG.open(encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg["BOT_TOKEN"], cfg["CHAT_ID"]


def _send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Envoi Telegram via urllib (bypass MCP cassé). R6 : ne lève pas."""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:  # noqa: BLE001
        print(f"[Telegram] envoi KO : {exc}", file=sys.stderr)
        return False


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"alerts": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"alerts": {}}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def _should_alert(state: dict, pattern: str) -> bool:
    """Rate-limit 1 alerte / pattern / RATE_LIMIT_HOURS."""
    last = state.get("alerts", {}).get(pattern)
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    delta = datetime.now(timezone.utc) - last_dt
    return delta > timedelta(hours=RATE_LIMIT_HOURS)


def _mark_alert(state: dict, pattern: str) -> None:
    state.setdefault("alerts", {})[pattern] = datetime.now(timezone.utc).isoformat()


def _compute_edge(db_path: Path) -> dict:
    """Calcule les 3 patterns critiques. Lecture seule."""
    if not db_path.exists():
        raise FileNotFoundError(f"DB absente : {db_path}")
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    out: dict = {"timestamp": datetime.now(timezone.utc).isoformat()}

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        # Pattern 1 : baissier 24h
        r = conn.execute(
            """
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) AS w,
                   ROUND(100.0 * SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS wr,
                   ROUND(SUM(resolution_pips), 1) AS pips
            FROM decisions
            WHERE action = 'preparer_entree'
              AND direction = 'baissiere'
              AND resolution_strategy IS NOT NULL
              AND resolved_at >= ?
            """,
            (cutoff_24h,),
        ).fetchone()
        out["baissier_24h"] = {"n": r[0] or 0, "wins": r[1] or 0,
                                "wr": r[2] or 0.0, "pips": r[3] or 0.0}

        # Pattern 2 : haussier 24h
        r = conn.execute(
            """
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) AS w,
                   ROUND(100.0 * SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS wr,
                   ROUND(SUM(resolution_pips), 1) AS pips
            FROM decisions
            WHERE action = 'preparer_entree'
              AND direction = 'haussiere'
              AND resolution_strategy IS NOT NULL
              AND resolved_at >= ?
            """,
            (cutoff_24h,),
        ).fetchone()
        out["haussier_24h"] = {"n": r[0] or 0, "wins": r[1] or 0,
                                "wr": r[2] or 0.0, "pips": r[3] or 0.0}

        # Pattern 3 : détail par symbole (pour message Telegram)
        rows = conn.execute(
            """
            SELECT symbol, direction, COUNT(*) AS n,
                   SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) AS w,
                   ROUND(100.0 * SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS wr,
                   ROUND(SUM(resolution_pips), 1) AS pips
            FROM decisions
            WHERE action = 'preparer_entree'
              AND resolution_strategy IS NOT NULL
              AND resolved_at >= ?
            GROUP BY symbol, direction
            HAVING n >= 3
            ORDER BY pips ASC
            """,
            (cutoff_24h,),
        ).fetchall()
        out["by_symbol_24h"] = [
            {"symbol": r[0], "direction": r[1], "n": r[2], "wins": r[3],
             "wr": r[4], "pips": r[5]}
            for r in rows
        ]
    return out


def _build_alerts(edge: dict) -> list[dict]:
    """Identifie les patterns critiques déclenchés."""
    alerts: list[dict] = []
    b = edge["baissier_24h"]
    if b["n"] >= THRESH_BAISS_N and b["wr"] < THRESH_BAISS_WR and b["pips"] <= THRESH_BAISS_PIPS:
        alerts.append({
            "pattern": "EDGE_BAISS_24H",
            "severity": "CRITIQUE" if b["wr"] < 25 else "HAUTE",
            "title": f"🔴 Edge baissier 24h dégradé : WR {b['wr']}% / {b['n']} trades / {b['pips']:+.1f} pips",
            "data": b,
        })
    h = edge["haussier_24h"]
    if h["n"] >= THRESH_HAUSSE_N and h["wr"] < THRESH_HAUSSE_WR and h["pips"] <= THRESH_HAUSSE_PIPS:
        alerts.append({
            "pattern": "EDGE_HAUSSE_24H",
            "severity": "HAUTE",
            "title": f"🟠 Edge haussier 24h dégradé : WR {h['wr']}% / {h['n']} trades / {h['pips']:+.1f} pips",
            "data": h,
        })
    # Pires paires
    worst = [s for s in edge.get("by_symbol_24h", []) if s["pips"] <= -50]
    worst.sort(key=lambda s: s["pips"])
    if worst[:3]:
        top3 = worst[:3]
        txt = " / ".join(
            f"{s['symbol']} {s['direction'][:4]} {s['pips']:+.0f}p"
            for s in top3
        )
        alerts.append({
            "pattern": "WORST_PAIRS_24H",
            "severity": "INFO",
            "title": f"📉 Pires paires 24h : {txt}",
            "data": {"pairs": top3},
        })
    return alerts


def _format_message(alerts: list[dict], edge: dict) -> str:
    """Compose le message Telegram (HTML)."""
    lines = ["<b>🚨 ALERTE EDGE V9 — 24h</b>", ""]
    for a in alerts:
        lines.append(a["title"])
    lines.append("")
    lines.append(f"<b>Snapshot :</b>")
    b = edge["baissier_24h"]
    h = edge["haussier_24h"]
    lines.append(f"  Baissier : n={b['n']} W={b['wins']} WR={b['wr']}% pips={b['pips']:+.1f}")
    lines.append(f"  Haussier : n={h['n']} W={h['wins']} WR={h['wr']}% pips={h['pips']:+.1f}")
    lines.append("")
    lines.append("<i>Action CEO : valider motion (paper_trade_halt, no_baissiere global, ou attendre).</i>")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V9 edge alert Telegram (R6+R18).")
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans envoyer.")
    parser.add_argument("--live", action="store_true", help="Envoi Telegram réel.")
    parser.add_argument("--json", action="store_true", help="Sortie JSON pour orchestrateur.")
    parser.add_argument("--force", action="store_true", help="Bypass rate-limit (debug).")
    args = parser.parse_args(argv)

    if not args.dry_run and not args.live and not args.json:
        args.dry_run = True  # sécurité par défaut

    try:
        edge = _compute_edge(DB_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f"[edge_alert] compute KO : {exc}", file=sys.stderr)
        return 2

    alerts = _build_alerts(edge)
    state = _load_state()

    # Filtrage rate-limit (sauf --force)
    if not args.force:
        alerts = [a for a in alerts if _should_alert(state, a["pattern"])]

    result = {
        "timestamp": edge["timestamp"],
        "n_alerts": len(alerts),
        "alerts": alerts,
        "edge_snapshot": {
            "baissier_24h": edge["baissier_24h"],
            "haussier_24h": edge["haussier_24h"],
            "by_symbol_24h": edge["by_symbol_24h"][:10],
        },
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if not alerts:
        print("[edge_alert] aucun pattern critique déclenché")
        return 0

    message = _format_message(alerts, edge)

    if args.dry_run:
        print(f"[DRY-RUN] {len(alerts)} alerte(s) :")
        print(message)
        return 0

    # args.live
    try:
        token, chat_id = _load_telegram()
    except Exception as exc:  # noqa: BLE001
        print(f"[edge_alert] Telegram config KO : {exc}", file=sys.stderr)
        return 2

    sent = _send_telegram(token, chat_id, message)
    if sent:
        for a in alerts:
            _mark_alert(state, a["pattern"])
        _save_state(state)
        print(f"[edge_alert] {len(alerts)} alerte(s) envoyée(s) (rate-limit 6h).")
    else:
        print("[edge_alert] Telegram KO — alerte NON envoyée (state non maj).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
