#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
v9_telegram_signal_alert.py — Envoi des alertes Telegram de signaux trading.

Bypass du MCP v9__telegram cassé (bug `json` local var). Utilise urllib direct.
Lit config/telegram.json (token + chat_id) et envoie les N derniers signaux
exploitables (action=preparer_entree) avec raison détaillée (principes, régime, confiance).

Mode dry-run par défaut (--dry-run) — n'envoie pas, affiche seulement.
Mode live (--live) — envoie les alertes réelles.

Idempotent : --since-minutes N permet d'éviter le spam (rate-limit 1/alerte par run).

Kill switch : V9_TELEGRAM_SIGNAL_ALERT_ENABLED (défaut OFF, R25' motion CEO).
Lecture via core.v9.kill_switches.is_enabled() — fallback os.environ.

Usage :
    python scripts/v9_telegram_signal_alert.py --dry-run --since-minutes 5
    python scripts/v9_telegram_signal_alert.py --live --since-minutes 5
    python scripts/v9_telegram_signal_alert.py --live --min-confidence 80 --limit 3
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TELEGRAM_CONFIG = ROOT / "config" / "telegram.json"
DB_PATH = ROOT / "data" / "v9_forces.db"
KILL_SWITCH_NAME = "V9_TELEGRAM_SIGNAL_ALERT_ENABLED"


def _is_kill_switch_on() -> bool:
    """Lecture kill switch via core.v9.kill_switches (fallback os.environ)."""
    try:
        from core.v9.kill_switches import is_enabled
        return is_enabled(KILL_SWITCH_NAME)
    except Exception:
        return os.environ.get(KILL_SWITCH_NAME, "0") == "1"


def load_telegram_config():
    """Lit config/telegram.json. Echoue si manquant."""
    if not TELEGRAM_CONFIG.exists():
        raise FileNotFoundError(f"Telegram config introuvable : {TELEGRAM_CONFIG}")
    with TELEGRAM_CONFIG.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    if "BOT_TOKEN" not in cfg or "CHAT_ID" not in cfg:
        raise ValueError("Config Telegram incomplète (BOT_TOKEN / CHAT_ID)")
    return cfg["BOT_TOKEN"], cfg["CHAT_ID"]


def fetch_recent_signals(db_path: Path, since_minutes: int, min_confidence: int, limit: int):
    """Lit les N derniers signaux action=preparer_entree au-dessus du seuil confiance."""
    if not db_path.exists():
        raise FileNotFoundError(f"DB introuvable : {db_path}")
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()
    sql = """
        SELECT timestamp, symbol, timeframe, direction, confiance,
               regime_type, principes_json, scene_id
        FROM decisions
        WHERE action = 'preparer_entree'
          AND timestamp > ?
          AND confiance >= ?
        ORDER BY confiance DESC, timestamp DESC
        LIMIT ?
    """
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        cur = conn.execute(sql, (cutoff, min_confidence, limit))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def format_signal_message(sig: dict) -> str:
    """Formate un signal en alerte Telegram HTML."""
    arrow = "🔻" if sig["direction"] == "baissiere" else "🔺"
    try:
        principes = json.loads(sig["principes_json"])
        if len(principes) > 8:
            principes = principes[:8] + [f"... +{len(principes) - 8}"]
        principes_txt = "\n".join(f"• {p}" for p in principes)
    except Exception:
        principes_txt = sig.get("principes_json", "(non parsable)")
    return (
        f"🚨 <b>SIGNAL V9 — CONFIANCE {sig['confiance']}%</b> {arrow}\n\n"
        f"<b>{sig['symbol']} {sig['timeframe']} → {sig['direction'].upper()}</b>\n"
        f"🕐 {sig['timestamp']}\n"
        f"🌐 Régime : {sig.get('regime_type', '?')}\n"
        f"🎯 Action : préparer_entree\n\n"
        f"<b>📐 RAISON (principes déclenchés) :</b>\n"
        f"{principes_txt}\n\n"
        f"Scene : <code>{sig.get('scene_id', '?')}</code>"
    )


def send_telegram(token: str, chat_id: str, text: str) -> dict:
    """Envoi HTTP POST direct vers api.telegram.org."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=10)
        body = r.read().decode("utf-8")
        return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}", "body": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Envoi réel (sinon dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="Force dry-run (override --live)")
    ap.add_argument("--db-path", default=str(DB_PATH))
    ap.add_argument("--since-minutes", type=int, default=5)
    ap.add_argument("--min-confidence", type=int, default=80)
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args()

    # --dry-run override --live (sécurité)
    if args.dry_run:
        args.live = False
    mode = "LIVE" if args.live else "DRY-RUN"
    print(f"=== V9 Telegram Signal Alert ({mode}) ===")
    print(f"DB : {args.db_path}")
    print(f"Since : {args.since_minutes} min | min_conf : {args.min_confidence}% | limit : {args.limit}")

    # Garde-fou kill switch (R25' strict — promotion = motion CEO)
    if args.live and not _is_kill_switch_on():
        print(f"🛑 KILL SWITCH {KILL_SWITCH_NAME}=0 → envoi LIVE refusé.")
        print(f"   Forcez --dry-run ou activez le kill switch via motion CEO explicite.")
        return 3

    try:
        sigs = fetch_recent_signals(
            Path(args.db_path), args.since_minutes, args.min_confidence, args.limit
        )
    except Exception as e:
        print(f"❌ DB read error : {e}")
        return 1

    print(f"Found {len(sigs)} signals")
    if not sigs:
        print("Aucun signal à alerter.")
        return 0

    if not args.live:
        print("\n--- DRY-RUN (rien envoyé) ---")
        for s in sigs:
            print("\n" + format_signal_message(s))
            print("---")
        return 0

    try:
        token, chat_id = load_telegram_config()
    except Exception as e:
        print(f"❌ Telegram config error : {e}")
        return 1

    sent = 0
    for s in sigs:
        text = format_signal_message(s)
        res = send_telegram(token, chat_id, text)
        if res.get("ok"):
            msg_id = res.get("result", {}).get("message_id", "?")
            print(f"✅ {s['symbol']} {s['timeframe']} {s['direction']} conf={s['confiance']} → msg_id={msg_id}")
            sent += 1
        else:
            print(f"❌ {s['symbol']} → {res.get('error', '?')} | {res.get('body', '')[:200]}")
    print(f"\n{sent}/{len(sigs)} alertes envoyées.")
    return 0 if sent == len(sigs) else 2


if __name__ == "__main__":
    sys.exit(main())
