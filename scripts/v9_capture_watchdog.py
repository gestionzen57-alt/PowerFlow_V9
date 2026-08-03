#!/usr/bin/env python3
"""v9_capture_watchdog.py — Watchdog du serveur de capture V9.

Surveille en boucle que core.v9.capture_server écoute bien sur
127.0.0.1:<LISTEN_PORT>. Si KO : tue les zombies éventuels, relance, et
ré-essaie N fois avant d'alerter Telegram.

Conçu pour être encapsulé en service Windows (sc.exe) — NE PAS utiliser
interactivement (Ctrl+C peu propre côté service).

Doctrine : R7 (zéro régression), R26 (livraison complète). Aucune logique
de trading, aucune décision.

Usage :
    python scripts/v9_capture_watchdog.py

Configuration via variables d'environnement :
    V9_WATCHDOG_INTERVAL    secondes entre 2 checks (défaut: 30)
    V9_WATCHDOG_MAX_TRIES   tentatives max avant alerte Telegram (défaut: 3)
    V9_WATCHDOG_COOLDOWN    secondes entre 2 relances (défaut: 30)
    V9_WATCHDOG_ALERT_COOLDOWN  minutes cooldown Telegram (défaut: 60)

Logs :
    logs/v9_capture_watchdog.log   — événements watchdog
    logs/v9_capture.log            — capture_server (via RotatingFileHandler)
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import LISTEN_HOST, LISTEN_PORT, LOG_PATH  # noqa: E402

WATCHDOG_LOG = ROOT_DIR / "logs" / "v9_capture_watchdog.log"
STATE_FILE = ROOT_DIR / "logs" / "v9_capture_watchdog_state.json"
PYTHON_EXE = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
CAPTURE_CMD = [str(PYTHON_EXE), "-X", "utf8", "-m", "core.v9.capture_server"]
WORKDIR = str(ROOT_DIR)

# CREATE_NO_WINDOW (0x08000000) + DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP
# = masque complet pour qu'aucun flash de console ne soit visible lors du
# lancement/arrêt du capture_server par le watchdog.
WINDOWS_HIDE_FLAGS = 0x08000000  # CREATE_NO_WINDOW

INTERVAL = int(os.environ.get("V9_WATCHDOG_INTERVAL", "30"))
MAX_TRIES = int(os.environ.get("V9_WATCHDOG_MAX_TRIES", "3"))
COOLDOWN = int(os.environ.get("V9_WATCHDOG_COOLDOWN", "30"))
ALERT_COOLDOWN_MIN = int(os.environ.get("V9_WATCHDOG_ALERT_COOLDOWN", "60"))


def setup_logging() -> logging.Logger:
    WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            RotatingFileHandler(
                WATCHDOG_LOG,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("v9.capture_watchdog")


log = setup_logging()


# ── State (cooldown Telegram) ────────────────────────────────────────


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"last_alert_ts": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        log.warning("State illisible, reset.")
        return {"last_alert_ts": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def cooldown_ok(state: dict, name: str, now_min: float) -> bool:
    try:
        last = float(state.get("last_alert_ts", {}).get(name, "0"))
    except (TypeError, ValueError):
        last = 0.0
    return (now_min - last) >= ALERT_COOLDOWN_MIN


def mark_alert(state: dict, name: str, now_min: float) -> None:
    state.setdefault("last_alert_ts", {})[name] = str(now_min)


# ── Telegram alert ───────────────────────────────────────────────────


def send_telegram_alert(message: str) -> bool:
    """POST direct API Telegram — bypass notifier daemon."""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        log.warning("Telegram: .env absent, alerte log-only.")
        return False
    bot_token = None
    chat_id = None
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k == "TELEGRAM_BOT_TOKEN":
            bot_token = v
        elif k == "TELEGRAM_CHAT_ID":
            chat_id = v
    if not bot_token or not chat_id or "***" in bot_token:
        log.warning("Telegram: token/chat_id manquants ou sanitisé, alerte log-only.")
        return False
    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            ok = r.status == 200
        if ok:
            log.info("Telegram: alerte envoyée.")
        return ok
    except Exception as exc:  # noqa: BLE001
        log.error("Telegram: échec envoi — %s", exc)
        return False


# ── Port + process checks ────────────────────────────────────────────


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def list_capture_pids() -> list[int]:
    """Liste les PIDs des process capture_server (via PowerShell CIM)."""
    r2 = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process python -ErrorAction SilentlyContinue | "
         "Where-Object {(Get-CimInstance Win32_Process -Filter "
         "\"ProcessId=$($_.Id)\").CommandLine -match 'capture_server'} | "
         "Select-Object -ExpandProperty Id"],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        creationflags=WINDOWS_HIDE_FLAGS,
    )
    pids = []
    for line in (r2.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def kill_capture_servers() -> int:
    pids = list_capture_pids()
    for pid in pids:
        r = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=WINDOWS_HIDE_FLAGS,
        )
        log.info("kill PID %d: %s", pid, (r.stdout or "").strip() or (r.stderr or "").strip())
    return len(pids)


def launch_capture_server() -> subprocess.Popen:
    """Lance capture_server en sous-processus détaché et SANS fenêtre console."""
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | WINDOWS_HIDE_FLAGS
    return subprocess.Popen(
        CAPTURE_CMD,
        cwd=WORKDIR,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=open(LOG_PATH, "ab", buffering=0),
        stderr=subprocess.STDOUT,
    )


# ── Boucle principale ────────────────────────────────────────────────


def find_pid_on_port_31685() -> int | None:
    """Phase 152 : trouve le PID qui tient le port LISTEN_PORT (ou None).

    Utilise netstat Windows (pas de dépendance externe).
    """
    try:
        r = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=WINDOWS_HIDE_FLAGS,
        )
        needle = f":{LISTEN_PORT}"
        for line in (r.stdout or "").splitlines():
            # Format : "  TCP    127.0.0.1:31685    0.0.0.0:0    LISTENING    1234"
            if needle in line and "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        continue
    except Exception as exc:  # noqa: BLE001
        log.debug("find_pid_on_port_31685 failed: %s", exc)
    return None


def send_doublon_alert(pids: list[int], keeper_pid: int | None, killed: list[int]) -> bool:
    """Phase 153 : alerte Telegram best-effort sur kill de doublons.

    R2 additif : utilise le même canal `send_telegram_alert` que la détection
    capture_down. Le cooldown Telegram est géré par `cooldown_ok()` du state.

    Args:
        pids : tous les PIDs détectés.
        keeper_pid : PID du port-holder (celui qu'on garde).
        killed : liste des PIDs tués par check_no_duplicates.

    Returns:
        bool : True si alerte envoyée, False sinon.
    """
    msg = (
        f"⚠️ V9 WATCHDOG DOUBLON DÉTECTÉ (Phase 152)\n"
        f"capture_server en parallèle : {len(pids)} (PIDs={pids})\n"
        f"Port-holder (gardé) : {keeper_pid}\n"
        f"Doublons tués (Phase 152 auto) : {len(killed)} (PIDs={killed})\n"
        f"Cause racine corruption 03/08 colmatée."
    )
    return send_telegram_alert(msg)


def check_no_duplicates(
    kill_extras: bool = True,
    alert: bool = True,
) -> int:
    """Phase 151/152/153 : détecte, tue et alerte les doublons capture_server.

    Si > 1 process écoute sur le port (ou a la cmdline capture_server),
    il y a write contention → cause racine corruption Phase 149.
    Log WARNING + (Phase 152) KILL les doublons en gardant celui qui
    tient le port LISTEN_PORT (= celui qui travaille réellement).
    + (Phase 153) Telegram best-effort sur doublon tué.

    Args:
        kill_extras : si True (défaut), kill les doublons (PID != port-holder).
        alert : si True (défaut), envoie Telegram si doublons effectivement tués.

    Returns:
        int : nombre de doublons tués (0 si OK ou si kill_extras=False).
    """
    pids = list_capture_pids()
    if len(pids) <= 1:
        return 0
    keeper_pid = find_pid_on_port_31685()
    if keeper_pid and keeper_pid in pids:
        extras = [p for p in pids if p != keeper_pid]
    else:
        # Pas de port-holder identifié → garder le 1er, tuer le reste
        extras = pids[1:]
        keeper_pid = pids[0]
    log.warning(
        "Phase 152 anti-doublon : %d capture_server détectés (PIDs=%s), "
        "keeper=%s, extras=%s",
        len(pids), pids, keeper_pid, extras,
    )
    killed: list[int] = []
    if kill_extras:
        for pid in extras:
            r = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                creationflags=WINDOWS_HIDE_FLAGS,
            )
            ok = r.returncode == 0
            log.info(
                "Phase 152 kill doublon PID %d: %s — %s",
                pid, "OK" if ok else "KO", (r.stdout or r.stderr or "").strip(),
            )
            if ok:
                killed.append(pid)
    if killed and alert:
        if send_doublon_alert(pids, keeper_pid, killed):
            log.info("Phase 153 Telegram doublon alert envoyée (%d tués).", len(killed))
        else:
            log.warning("Phase 153 Telegram doublon alert ÉCHEC (best-effort, log-only).")
    return len(killed)


def restart_attempt() -> bool:
    """Tente UNE relance complète (kill + start + wait + check)."""
    log.warning("Port %d KO — relance capture_server.", LISTEN_PORT)
    n_killed = kill_capture_servers()
    log.info("Zombies tués: %d", n_killed)
    try:
        proc = launch_capture_server()
        log.info("capture_server lancé PID=%d", proc.pid)
    except Exception as exc:  # noqa: BLE001
        log.error("Échec lancement capture_server: %s", exc)
        return False
    time.sleep(10)
    return port_open(LISTEN_HOST, LISTEN_PORT)


def main() -> int:
    log.info("=" * 60)
    log.info("V9 Capture Watchdog — start")
    log.info("interval=%ds max_tries=%d cooldown=%ds alert_cooldown=%dmin",
             INTERVAL, MAX_TRIES, COOLDOWN, ALERT_COOLDOWN_MIN)
    log.info("target: %s:%d", LISTEN_HOST, LISTEN_PORT)
    log.info("=" * 60)

    state = load_state()
    fails_in_a_row = 0

    while True:
        ts = datetime.now(timezone.utc)
        now_min = ts.timestamp() / 60.0
        # Phase 151 : anti-doublon (cause racine corruption 03/08 18:30 UTC)
        check_no_duplicates()
        ok = port_open(LISTEN_HOST, LISTEN_PORT)
        if ok:
            if fails_in_a_row:
                log.info("Port %d OK après %d échec(s) — reset.", LISTEN_PORT, fails_in_a_row)
                fails_in_a_row = 0
            else:
                log.debug("Port %d OK", LISTEN_PORT)
        else:
            fails_in_a_row += 1
            log.warning("Port %d KO (échec %d/%d)", LISTEN_PORT, fails_in_a_row, MAX_TRIES)
            recovered = False
            for attempt in range(1, MAX_TRIES + 1):
                log.info("Tentative relance %d/%d...", attempt, MAX_TRIES)
                if restart_attempt():
                    recovered = True
                    log.info("Relance %d/%d réussie.", attempt, MAX_TRIES)
                    fails_in_a_row = 0
                    break
                log.warning("Relance %d/%d échouée.", attempt, MAX_TRIES)
                time.sleep(COOLDOWN)
            if not recovered:
                msg = (
                    f"🚨 V9 capture_server DOWN\n"
                    f"Port {LISTEN_PORT} KO après {MAX_TRIES} tentatives\n"
                    f"Action manuelle requise (vérifier MT4 + EA)"
                )
                if cooldown_ok(state, "capture_down", now_min):
                    log.error(msg)
                    if send_telegram_alert(msg):
                        mark_alert(state, "capture_down", now_min)
                        save_state(state)
                else:
                    log.error("Alerte Telegram en cooldown (skip): %s", msg.replace("\n", " | "))
                fails_in_a_row = MAX_TRIES  # évite spam log

        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log.info("Watchdog arrêté manuellement.")
        sys.exit(0)