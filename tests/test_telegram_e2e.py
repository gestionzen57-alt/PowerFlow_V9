"""Test E2E : envoie un message Telegram, vérifie que le daemon --watch
le reçoit et y répond.

Pré-requis : daemon --watch actif dans un autre terminal/background.

Test manuel (pas dans pytest — nécessite daemon live + token Telegram).
Run : .venv/Scripts/python.exe tests/test_telegram_e2e.py
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Envoie un message via Telegram Bot API."""
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, method="POST",
    )
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read())["ok"]


def get_daemon_log_tail(log_path: Path, since_bytes: int) -> str:
    """Lit le fichier log à partir d'un offset."""
    if not log_path.exists():
        return ""
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        f.seek(since_bytes)
        return f.read()


def main() -> int:
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env absent")
        return 2
    env = env_path.read_text(encoding="utf-8")
    token = ""
    chat_id = ""
    for line in env.splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip()
        elif line.startswith("TELEGRAM_CHAT_ID="):
            chat_id = line.split("=", 1)[1].strip()
    if not token or not chat_id:
        print("❌ TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant dans .env")
        return 2

    log_path = Path("logs/telegram_notifier.log")
    size_before = log_path.stat().st_size if log_path.exists() else 0

    test_cmd = f"/status test_e2e_{int(time.time())}"
    print(f"Envoi : {test_cmd!r}")
    if not send_telegram(token, chat_id, test_cmd):
        print("❌ Envoi Telegram échoué")
        return 1

    print("Attente 5s pour traitement daemon...")
    time.sleep(5)

    new_logs = get_daemon_log_tail(log_path, size_before)
    print(f"\n=== Nouveaux logs ({len(new_logs)} chars) ===")
    print(new_logs[:1500])

    # Critères de succès
    has_update_id = "update_id=" in new_logs
    has_test_cmd = test_cmd in new_logs
    has_send = "sendMessage" in new_logs or "Message Telegram envoyé" in new_logs
    has_offset_persisted = "offset persisted" in new_logs

    print()
    print("=== Critères ===")
    print(f"  update_id loggé           : {'✅' if has_update_id else '❌'}")
    print(f"  test_cmd dans logs         : {'✅' if has_test_cmd else '❌'}")
    print(f"  sendMessage / réponse      : {'✅' if has_send else '❌'}")
    print(f"  offset persisté            : {'✅' if has_offset_persisted else '❌'}")

    return 0 if (has_update_id and has_test_cmd and has_send and has_offset_persisted) else 1


if __name__ == "__main__":
    sys.exit(main())