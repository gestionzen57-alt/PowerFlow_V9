#!/usr/bin/env python3
"""v9_cognitive_telegram.py — Pont Telegram minimal pour le JOURNAL COGNITIF.

Réutilise config/telegram.json (même token que scripts/v9_telegram_notifier.py).
Capture une lecture V9 fraîche puis l'envoie à Søn avec une demande de
correction structurée. Aucune écriture dans data/v9_forces.db, aucune
modification de core/v9/config.py, orchestrator.py, principle_engine.py,
principles/*.yaml.

Usage :
    python scripts/v9_cognitive_telegram.py --send
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9 import cognitive_journal  # noqa: E402

CONFIG_PATH = ROOT_DIR / "config" / "telegram.json"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _ensure_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_telegram_config() -> dict[str, str] | None:
    """Charge BOT_TOKEN/CHAT_ID depuis config/telegram.json, ou None si absent/invalide."""
    if not CONFIG_PATH.exists():
        return None
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    token = cfg.get("BOT_TOKEN", "").strip()
    chat_id = cfg.get("CHAT_ID", "").strip()
    if not token or not chat_id or token == "TON_TOKEN_ICI":
        return None
    return {"token": token, "chat_id": chat_id}


def send_telegram(text: str, config: dict[str, str]) -> bool:
    """Envoie un message via l'API Telegram. Retourne True si succès."""
    url = TELEGRAM_API.format(token=config["token"])
    payload = json.dumps({"chat_id": config["chat_id"], "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return False


def build_correction_request(reading_id: int, narrative: str) -> str:
    return (
        "🧠 V9 voit :\n"
        f"{narrative}\n\n"
        "Tu vois quoi ? Réponds avec :\n"
        f"/correct {reading_id} narrative:... direction:LONG/SHORT/NEUTRE patterns:..."
    )


def run_send(
    market_db_path: Path | None = None, journal_db_path: Path | None = None
) -> tuple[int, str]:
    """Capture une lecture V9 fraîche, l'envoie sur Telegram. Retourne (code, message)."""
    config = load_telegram_config()
    if config is None:
        return 1, "BOT_TOKEN/CHAT_ID manquant — configurer config/telegram.json."

    reading_id = cognitive_journal.log_v9_reading(
        market_db_path=market_db_path, db_path=journal_db_path
    )
    reading = cognitive_journal.get_reading(reading_id, db_path=journal_db_path)
    narrative = reading["v9_narrative"] if reading else ""
    message = build_correction_request(reading_id, narrative)

    ok = send_telegram(message, config)
    if not ok:
        return 1, f"Échec de l'envoi Telegram.\n{message}"
    return 0, message


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Pont Telegram — JOURNAL COGNITIF V9.")
    parser.add_argument("--send", action="store_true", help="Envoie la dernière lecture V9 + demande de correction.")
    parser.add_argument("--db", type=Path, default=None, help="DB du journal (data/v9_cognitive.db par défaut).")
    parser.add_argument("--market-db", type=Path, default=None, help="DB marché (data/v9_forces.db par défaut).")
    args = parser.parse_args(argv)

    if args.send:
        code, message = run_send(args.market_db, args.db)
        print(message)
        return code

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
