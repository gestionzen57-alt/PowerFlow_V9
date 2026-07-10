#!/usr/bin/env python3
"""mcp-v9-telegram — MCP server ciblé pour envoi Telegram (anti-spam 60min).

Tools exposés :
- send_message(text: str, chat_id: str | None) → bool
- send_alert(level: str, text: str) → bool  (ERROR/WARN/INFO, icône automatique)
- get_chat_id() → str
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT_DIR = Path(r"C:\projet\V9")
CONFIG_PATHS = [
    ROOT_DIR / ".env",
    ROOT_DIR / "config" / "telegram.json",
]

# Anti-spam cache : file-based pour persister entre redémarrages
ANTI_SPAM_FILE = ROOT_DIR / "logs" / ".telegram_mcp_anti_spam.json"
ANTI_SPAM_COOLDOWN_S = 3600  # 1h


def _load_config() -> dict:
    """Charge token + chat_id depuis .env ou config/telegram.json."""
    config = {}
    for path in CONFIG_PATHS:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if path.suffix == ".json":
            try:
                config.update(json.loads(text))
            except Exception:
                pass
        else:
            for line in text.splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    config[k.strip()] = v.strip()
    return {
        "token": config.get("TELEGRAM_BOT_TOKEN") or config.get("BOT_TOKEN") or "",
        "chat_id": config.get("TELEGRAM_CHAT_ID") or config.get("CHAT_ID") or "",
    }


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    cert = os.environ.get("SSL_CERT_FILE", "").strip()
    if cert and Path(cert).exists():
        try:
            ctx.load_verify_locations(cert)
        except Exception:
            pass
    certifi_default = (
        Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent"
        / "venv" / "Lib" / "site-packages" / "certifi" / "cacert.pem"
    )
    if certifi_default.exists():
        try:
            ctx.load_verify_locations(str(certifi_default))
        except Exception:
            pass
    return ctx


def _load_anti_spam() -> dict:
    if ANTI_SPAM_FILE.exists():
        try:
            return json.loads(ANTI_SPAM_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_anti_spam(cache: dict) -> None:
    ANTI_SPAM_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANTI_SPAM_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _send_telegram(token: str, chat_id: str, text: str) -> bool:
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, method="POST",
        )
        ctx = _make_ssl_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            import json
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr, flush=True)
        return False


def handle_send_message(args: dict) -> dict:
    text = args.get("text", "")
    chat_id_override = args.get("chat_id")
    if not text:
        return {"error": "text manquant"}
    cfg = _load_config()
    chat_id = chat_id_override or cfg["chat_id"]
    if not cfg["token"] or not chat_id:
        return {"error": "telegram config manquant (.env ou config/telegram.json)"}
    ok = _send_telegram(cfg["token"], chat_id, text)
    return {"sent": ok, "chat_id": chat_id, "length": len(text)}


def handle_send_alert(args: dict) -> dict:
    """Envoie une alerte avec icône + anti-spam 60min par (level, hash)."""
    level = args.get("level", "INFO").upper()
    text = args.get("text", "")
    icon = {"ERROR": "🔴", "WARN": "🟠", "INFO": "🟢", "CRITICAL": "🚨"}.get(level, "ℹ️")
    message = f"{icon} V9 {level}\n\n{text}"

    # Anti-spam : hash du message, si déjà envoyé dans la dernière heure, skip
    import hashlib
    msg_hash = hashlib.md5(message.encode()).hexdigest()[:12]
    cache = _load_anti_spam()
    now = time.time()
    last_sent = cache.get(msg_hash)
    if last_sent and (now - last_sent) < ANTI_SPAM_COOLDOWN_S:
        remaining = int(ANTI_SPAM_COOLDOWN_S - (now - last_sent))
        return {"sent": False, "anti_spam": True, "remaining_s": remaining, "hash": msg_hash}

    cfg = _load_config()
    if not cfg["token"] or not cfg["chat_id"]:
        return {"error": "telegram config manquant"}
    ok = _send_telegram(cfg["token"], cfg["chat_id"], message)
    if ok:
        cache[msg_hash] = now
        _save_anti_spam(cache)
    return {"sent": ok, "level": level, "hash": msg_hash}


def handle_get_chat_id(args: dict) -> dict:
    cfg = _load_config()
    return {"chat_id": cfg["chat_id"], "token_set": bool(cfg["token"])}


HANDLERS = {
    "send_message": handle_send_message,
    "send_alert": handle_send_alert,
    "get_chat_id": handle_get_chat_id,
}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            tool = req.get("tool")
            args = req.get("args", {})
            handler = HANDLERS.get(tool)
            if not handler:
                result = {"error": f"unknown tool: {tool}"}
            else:
                result = handler(args)
            print(json.dumps({"id": req.get("id"), "result": result}), flush=True)
        except Exception as e:
            print(json.dumps({"error": f"parse/handle error: {e}"}), flush=True)


if __name__ == "__main__":
    main()