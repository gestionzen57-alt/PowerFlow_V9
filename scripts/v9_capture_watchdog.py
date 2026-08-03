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

from core.v9.config import DB_PATH, LISTEN_HOST, LISTEN_PORT, LOG_PATH  # noqa: E402

WATCHDOG_LOG = ROOT_DIR / "logs" / "v9_capture_watchdog.log"
STATE_FILE = ROOT_DIR / "logs" / "v9_capture_watchdog_state.json"
PYTHON_EXE = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
# Phase 169 (03/08) : CAPTURE_CMD utilise sys.executable au lieu de PYTHON_EXE.
# Raison : si .venv/Scripts/python.exe est un wrapper (45KB hermes-agent) qui
# re-spawn via home=uv python (pyvenv.cfg), subprocess.Popen héritera du
# re-spawn → 2 process identiques (capture_server + clone uv).
# sys.executable est le binaire REEL qui exécute le code courant (déjà
# passé par le re-spawn si applicable) → 1 seul process après Popen.
# R6 fail-open : si sys.executable n'est pas dispo, fallback PYTHON_EXE.
#
# Phase 174 (03/08) : ajoute PYTHONPATH=ROOT_DIR dans l'env du subprocess.
# Le crash "ModuleNotFoundError: yaml" observe a 19:32 UTC etait
# reproductiblement en boucle (chaque relance watchdog echouait). Cause
# exacte incertaine (sys.executable et PYTHON_EXE pointes sur le meme
# .venv/Scripts/python.exe dans CE contexte, mais Task Scheduler Windows
# peut heriter d'un env degrade). R2 additif : on force PYTHONPATH pour
# garantir que "core.v9" et site-packages du .venv sont trouvables, sans
# casser le choix sys.executable de Phase 169.
_CAPTURE_PYTHON = (
    sys.executable if sys.executable else str(PYTHON_EXE)
)
_CAPTURE_ENV = os.environ.copy()
_CAPTURE_ENV.setdefault("PYTHONPATH", str(ROOT_DIR))
CAPTURE_CMD = [_CAPTURE_PYTHON, "-X", "utf8", "-m", "core.v9.capture_server"]
WORKDIR = str(ROOT_DIR)

# CREATE_NO_WINDOW (0x08000000) + DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP
# = masque complet pour qu'aucun flash de console ne soit visible lors du
# lancement/arrêt du capture_server par le watchdog.
WINDOWS_HIDE_FLAGS = 0x08000000  # CREATE_NO_WINDOW

INTERVAL = int(os.environ.get("V9_WATCHDOG_INTERVAL", "300"))
"""Interval entre 2 checks (secondes). Defaut 300s = 5min.
Phase 167 (03/08) : passe de 30s → 300s. Spam 30s amplifieait la boucle
doublon-kill-restart. 5min laisse le temps aux processus de se stabiliser.
"""
MAX_TRIES = int(os.environ.get("V9_WATCHDOG_MAX_TRIES", "3"))
COOLDOWN = int(os.environ.get("V9_WATCHDOG_COOLDOWN", "60"))
ALERT_COOLDOWN_MIN = int(os.environ.get("V9_WATCHDOG_ALERT_COOLDOWN", "360"))
"""Cooldown alertes Telegram doublon (minutes). Defaut 360min = 6h.
Phase 167 (03/08) : passe de 60min → 360min. Empêche le spam Telegram
(8+ alertes/30min observees 03/08). Le port-holder et le doublon
peuvent coexister temporairement sans danger pour la DB (WAL writer unique).
"""


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
    # Phase 177 (03/08) : stderr dédié horodaté par relance. R2 additif pur.
    # Contexte : Phase 176 a montré crash runtime asyncio silencieux — stderr
    # était fusionné dans stdout (subprocess.STDOUT) qui pointe sur
    # v9_capture.log, mais le crash survient AVANT tout write → log vide.
    # Fix : rediriger stderr vers un fichier dédié logs/capture_server_err_
    # <UTC timestamp>.log pour que la prochaine relance capture l'erreur
    # réelle (Traceback, OSError, etc.) sans dépendre du timing d'écriture.
    _err_log = ROOT_DIR / "logs" / (
        "capture_server_err_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + ".log"
    )
    # Phase 177 v2 (03/08) : attendre que le port soit libre AVANT Popen.
    # R2 additif pur. Contexte : kill_capture_servers() tue l'ancienne
    # instance mais Windows peut garder le port en TIME_WAIT (~30-120s)
    # ou un process zombie peut détenir le port. Si Popen démarre
    # pendant que le port est encore occupé → capture_server crash avec
    # errno 10048 (vu en smoke test 22:53 UTC) → process vivant mais
    # 0 LISTENING → watchdog croit que la relance a réussi.
    # Fix : boucle 10s max testant bind(127.0.0.1, LISTEN_PORT) avec
    # SO_REUSEADDR=1 (laisse une fenêtre pour récupérer le socket).
    # R6 défensif : si le port reste occupé après 10s, on Popen quand
    # même (le crash sera capturé dans _err_log grâce au patch v1) —
    # ne JAMAIS bloquer la boucle watchdog.
    _wait_deadline = time.time() + 10
    _port_ready = False
    while time.time() < _wait_deadline:
        try:
            _probe = socket.socket()
            _probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            _probe.bind((LISTEN_HOST, LISTEN_PORT))
            _probe.close()
            _port_ready = True
            break
        except OSError as _e:
            log.info("Phase 177 v2 : port %d occupé (%s), attente 1s...",
                     LISTEN_PORT, _e)
            time.sleep(1)
    if not _port_ready:
        log.warning("Phase 177 v2 : port %d toujours occupé après 10s, "
                    "Popen quand même (crash capturé dans %s)",
                    LISTEN_PORT, _err_log.name)
    proc = subprocess.Popen(
        CAPTURE_CMD,
        cwd=WORKDIR,
        env=_CAPTURE_ENV,  # Phase 174 (03/08) : PYTHONPATH=ROOT_DIR injecte.
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=open(LOG_PATH, "ab", buffering=0),
        stderr=open(_err_log, "ab", buffering=0),
    )
    log.info("Phase 177 stderr → %s (PID=%d)", _err_log, proc.pid)
    return proc


# ── Boucle principale ────────────────────────────────────────────────

# Phase 170 (03/08) : SINGLE-INSTANCE LOCK (stdlib pur, atomic + stale-safe).
# Cause racine : le binaire .venv/Scripts/python.exe (45KB hermes-agent wrapper)
# re-spawn via home=uv python (pyvenv.cfg) → 2 process identiques au démarrage.
# Strategie : chaque instance pose un lock avec son PID. Si un lock existe avec
# un PID VIVANT different du notre → on est un doublon → exit propre (code 0).
# Si le PID est mort (lock stale) → on ecrase et on continue (R6 fail-open).
# Pas de thread daemon meurtrier : trop fragile (atexit + fork + windows).
# R2 additif : ne touche pas au reste du watchdog, juste ajoute _acquire_lock().
_LOCK_FILE = ROOT_DIR / "logs" / ".watchdog.lock"
_MY_PID = os.getpid()


def _pid_alive(pid: int) -> bool:
    """Verifie qu'un PID Windows est vivant via Get-Process (stdlib).

    Args:
        pid : PID a verifier.

    Returns:
        bool : True si le process existe et est un python, False sinon.
    """
    if pid <= 0:
        return False
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | "
             f"Select-Object -ExpandProperty ProcessName"],
            capture_output=True, text=True, timeout=5,
            creationflags=WINDOWS_HIDE_FLAGS,
        )
        # Sortie attendue : "python" sur une ligne. Anything else = KO.
        for line in (r.stdout or "").splitlines():
            if line.strip().lower() == "python":
                return True
    except Exception:
        return False
    return False


def _read_lock_pid() -> int:
    """Lit le PID stocké dans le lock file. Retourne 0 si absent/invalide."""
    if not _LOCK_FILE.exists():
        return 0
    try:
        txt = _LOCK_FILE.read_text(encoding="utf-8").strip()
        return int(txt) if txt.isdigit() else 0
    except Exception:
        return 0


def _write_lock_atomic(pid: int) -> None:
    """Ecrit le PID dans le lock file de maniere atomique (os.replace)."""
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _LOCK_FILE.with_suffix(_LOCK_FILE.suffix + ".tmp")
    tmp.write_text(str(pid), encoding="utf-8")
    os.replace(tmp, _LOCK_FILE)


def _acquire_lock() -> bool:
    """Tente d'acquerir le single-instance lock.

    Returns:
        bool : True si on a pose le lock (on est l'instance unique).
               False si un autre watchdog vivant tient deja le lock.
    """
    existing = _read_lock_pid()
    if existing == _MY_PID:
        # Lock deja a nous (re-import, etc.) — rien a faire.
        return True
    if existing > 0 and existing != _MY_PID:
        if _pid_alive(existing):
            # Doublon : un autre watchdog tient le port + le lock.
            log.warning(
                "Phase 170 lock: doublon detecte (lock PID=%d vivant, moi=%d). Sortie.",
                existing, _MY_PID,
            )
            return False
        # Lock stale : ancien watchdog mort, on ecrase.
        log.warning(
            "Phase 170 lock: PID=%d dans le lock mais mort → ecrase (R6 fail-open).",
            existing,
        )
    # Poser notre lock.
    _write_lock_atomic(_MY_PID)
    log.info("Phase 170 lock acquis (PID=%d).", _MY_PID)
    return True


def _release_lock() -> None:
    """Libere le lock si on en est le proprietaire. Best-effort."""
    try:
        if _read_lock_pid() == _MY_PID and _LOCK_FILE.exists():
            _LOCK_FILE.unlink()
    except Exception:
        pass


# NOTE: l'acquisition du lock a ete deplacee dans main() pour eviter qu'un
# simple `import scripts.v9_capture_watchdog` (ex: par pytest) declenche un
# sys.exit(0) si le lock est tenu par un autre process. Les helpers
# `_acquire_lock`, `_release_lock`, `_read_lock_pid`, `_write_lock_atomic`,
# `_pid_alive` restent exposes et testables.


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


def check_wal_size(threshold_mb: int = 100) -> int:
    """Phase 155 : surveille la taille du WAL file et alerte si > seuil.

    Si `.db-wal` dépasse `threshold_mb`, c'est qu'il y a beaucoup de
    transactions non-checkpointées. Risque = disque plein en cas de
    crash brutal. Log WARNING + (best-effort) Telegram.

    Args:
        threshold_mb : seuil d'alerte en MB (défaut 100 MB).

    Returns:
        int : taille du WAL en MB (0 si absent).
    """
    wal_path = Path(str(DB_PATH) + "-wal")
    if not wal_path.exists():
        return 0
    size_mb = wal_path.stat().st_size / (1024 * 1024)
    if size_mb > threshold_mb:
        log.warning(
            "Phase 155 WAL size: %.1f MB > %d MB seuil — checkpoint recommandé",
            size_mb, threshold_mb,
        )
        # Best-effort Telegram (cooldown géré par le state existant)
        msg = (
            f"⚠️ V9 WAL SIZE WARNING (Phase 155)\n"
            f"Fichier : {wal_path}\n"
            f"Taille : {size_mb:.1f} MB (seuil {threshold_mb} MB)\n"
            f"Risque : crash brutal = perte transactions.\n"
            f"Recommandation : lancer PRAGMA wal_checkpoint(TRUNCATE)"
        )
        # Cooldown via state file pour éviter spam
        state = load_state()
        if cooldown_ok(state, "wal_size", datetime.now(timezone.utc).timestamp() / 60.0):
            if send_telegram_alert(msg):
                mark_alert(state, "wal_size", datetime.now(timezone.utc).timestamp() / 60.0)
                save_state(state)
    return int(size_mb)


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

    Phase 167 (03/08) : si aucun port-holder identifié (race condition TCP),
    MODE SAFE : ne tue RIEN et alerte Telegram unique "doublon sans
    port-holder". Empêche la boucle doublon-kill-restart observee 03/08
    ou le watchdog tuait l'original et gardait le doublon zombie.

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
    if not keeper_pid:
        # Phase 167 : MODE SAFE — pas de port-holder identifié, on ne touche à rien.
        # Cas typique : 2 processus en train de se relayer sur le port (race TCP).
        # Tuer au hasard ferait perdre le serveur qui fonctionne réellement.
        log.warning(
            "Phase 167 MODE SAFE : %d capture_server détectés (PIDs=%s), "
            "AUCUN port-holder identifié → AUCUN KILL. ",
            len(pids), pids,
        )
        # Alerte Telegram UNIQUEMENT si doublon ECHAPPERAIT au cooldown (1x/6h).
        if alert:
            state = load_state()
            now_min = datetime.now(timezone.utc).timestamp() / 60.0
            if cooldown_ok(state, "doublon_no_holder", now_min):
                msg = (
                    f"⚠️ V9 WATCHDOG DOUBLON SANS PORT-HOLDER (Phase 167 MODE SAFE)\n"
                    f"capture_server en parallèle : {len(pids)} (PIDs={pids})\n"
                    f"Aucun PID ne tient le port 31685 — race TCP.\n"
                    f"AUCUN KILL effectué (mode safe).\n"
                    f"Action : investigation manuelle recommandée si >10min."
                )
                if send_telegram_alert(msg):
                    mark_alert(state, "doublon_no_holder", now_min)
                    save_state(state)
        return 0
    if keeper_pid and keeper_pid in pids:
        extras = [p for p in pids if p != keeper_pid]
    else:
        # keeper_pid identifié mais pas dans pids → cas anormal, MODE SAFE
        log.warning(
            "Phase 167 MODE SAFE : keeper_pid=%s pas dans pids=%s → AUCUN KILL.",
            keeper_pid, pids,
        )
        return 0
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

    # Phase 170 : acquisition du single-instance lock. Si doublon → exit propre.
    if not _acquire_lock():
        log.warning("Phase 170 doublon detecte, sortie (code 0).")
        return 0
    import atexit as _atexit_main
    _atexit_main.register(_release_lock)

    state = load_state()
    fails_in_a_row = 0

    while True:
        ts = datetime.now(timezone.utc)
        now_min = ts.timestamp() / 60.0
        # Phase 151 : anti-doublon (cause racine corruption 03/08 18:30 UTC)
        check_no_duplicates()
        # Phase 155 : WAL size monitoring
        check_wal_size()
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