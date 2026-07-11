#!/usr/bin/env python3
"""v9_supervisor.py — Bibliothèque partagée et point d'entrée unique pour
l'outillage opérationnel PowerFlow V9 (reboot machine, ouverture marché,
reprise de session).

Couche cognitive : outillage de déploiement/observation uniquement. Aucune
logique de trading, aucune décision, aucune modification de `core/v9/*`.
Ce module ne fait qu'orchestrer des vérifications déjà exposées par
`scripts/deploy_v9.py` et `core/v9/market_calendar.py`, et fournit des
fonctions partagées (gestion de port stale, démarrage serveur en arrière-
plan, health snapshot, génération de mini-checkpoint) réutilisées par
`v9_bootstrap.py`, `v9_market_open.py` et `v9_session_resume.py`.

Aucune dépendance externe (stdlib uniquement) — aucun LLM requis pour
démarrer.

Usage :
    python scripts/v9_supervisor.py --health
    python scripts/v9_supervisor.py --boot
    python scripts/v9_supervisor.py --market-open
    python scripts/v9_supervisor.py --resume
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH, LISTEN_HOST, LISTEN_PORT, LOG_PATH  # noqa: E402
from core.v9.market_calendar import MarketCalendar  # noqa: E402
from scripts.deploy_v9 import (  # noqa: E402
    CORE_MODULES,
    PID_FILE,
    check_db,
    check_modules_importable,
    check_python_version,
)

OPS_LOG_PATH = ROOT_DIR / "logs" / "v9_ops.log"
MINI_CHECKPOINT_DIR = ROOT_DIR / "workspace" / "perplexity" / "mini_checkpoints"


# ── Logging ───────────────────────────────────────────────
def setup_logging(name: str) -> logging.Logger:
    """Logger partagé (fichier `logs/v9_ops.log` + console), un seul handler
    de fichier par process pour éviter les lignes dupliquées entre scripts
    appelés en cascade (`v9_supervisor` -> `v9_bootstrap` par ex.)."""
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    OPS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(OPS_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger


# ── Git helpers ───────────────────────────────────────────
def git_branch() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(ROOT_DIR), capture_output=True, text=True, check=True, encoding="utf-8", errors="replace",
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return "inconnue"


def git_last_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h %s"],
            cwd=str(ROOT_DIR), capture_output=True, text=True, check=True, encoding="utf-8", errors="replace",
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return "inconnu"


# ── Gestion de port stale ─────────────────────────────────
def is_port_available(port: int = LISTEN_PORT, host: str = LISTEN_HOST) -> bool:
    """Vrai si `port` peut être bindé (donc libre). Aucune écriture, aucun
    effet de bord persistant : socket fermé immédiatement."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def find_pid_on_port(port: int) -> int | None:
    """Cherche le PID qui écoute sur `port` via `netstat` (Windows
    uniquement — le déploiement V9 ne cible que cette machine). Retourne
    None si non trouvé ou plateforme non supportée."""
    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace"
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in result.stdout.splitlines():
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_addr = parts[1]
        if not local_addr.endswith(f":{port}"):
            continue
        try:
            return int(parts[-1])
        except ValueError:
            continue
    return None


def kill_pid(pid: int, logger: logging.Logger) -> bool:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"], check=True, capture_output=True
            )
        else:
            os.kill(pid, signal.SIGTERM)
        logger.info(f"Process stale PID {pid} arrete.")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Echec arret du process stale PID {pid} : {exc}")
        return False


def ensure_port_free(port: int, logger: logging.Logger) -> bool:
    """Libère `port` si un process stale (sans PID file V9 correspondant,
    ou PID file perime) l'occupe déjà. Ne touche jamais un serveur de
    capture légitime déjà suivi par le PID file V9 (`logs/v9_capture.pid`)
    — retourne True immédiatement dans ce cas, le port étant considéré
    correctement occupé par notre propre process. Retourne True si le
    port est libre en sortie (qu'il l'était déjà, qu'il était légitimement
    occupé, ou qu'il vient d'être libéré)."""
    if is_port_available(port):
        logger.info(f"Port {port} deja libre.")
        return True

    running, own_pid = is_server_running()
    pid_on_port = find_pid_on_port(port)

    if running and pid_on_port is not None and pid_on_port == own_pid:
        logger.info(
            f"Port {port} occupe par notre propre serveur de capture (PID {own_pid}) "
            f"— occupation legitime, aucune action."
        )
        return True

    if pid_on_port is None:
        logger.warning(
            f"Port {port} occupe mais PID introuvable "
            f"(plateforme non-Windows, ou parsing netstat en echec)."
        )
        return False

    logger.warning(
        f"Port {port} occupe par un process stale (PID {pid_on_port}, "
        f"sans PID file V9 correspondant) — arret."
    )
    kill_pid(pid_on_port, logger)
    time.sleep(1.0)
    freed = is_port_available(port)
    if freed:
        logger.info(f"Port {port} libere avec succes.")
    else:
        logger.error(f"Port {port} toujours occupe apres tentative d'arret du PID {pid_on_port}.")
    return freed


# ── Serveur de capture ────────────────────────────────────
def is_server_running() -> tuple[bool, int | None]:
    """Statut du serveur de capture d'après le PID file (`logs/v9_capture.pid`,
    partagé avec `deploy_v9.py`). Vérifie que le PID est bien vivant, pas
    seulement que le fichier existe (fichier perime possible)."""
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return False, None

    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace"
            )
            alive = str(pid) in result.stdout
        except (OSError, subprocess.TimeoutExpired):
            alive = False
    else:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    return alive, pid


def start_capture_server_background(logger: logging.Logger) -> subprocess.Popen:
    """Démarre `core.v9.capture_server` en sous-processus détaché (non
    bloquant, contrairement à `deploy_v9.py --start`) afin que le script
    appelant puisse enchaîner d'autres vérifications. Écrit le même PID
    file que `deploy_v9.py`, donc `deploy_v9.py --status`/`--stop` restent
    utilisables pour piloter ce process."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    # P0-C audit 2026-07-11 : kill switch zone_diagnostics (ROI -315 MB DB).
    # Zone_detector n'est consommé par aucun module downstream (vérifié grep).
    # On force V9_DISABLE_ZONE_DIAGNOSTICS=1 sauf si l'opérateur l'a déjà
    # positionné explicitement (respect override humain).
    child_env = os.environ.copy()
    child_env.setdefault("V9_DISABLE_ZONE_DIAGNOSTICS", "1")
    proc = subprocess.Popen(
        [sys.executable, "-m", "core.v9.capture_server"],
        cwd=str(ROOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        env=child_env,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    logger.info(
        f"Serveur de capture demarre en arriere-plan (PID {proc.pid}) sur "
        f"{LISTEN_HOST}:{LISTEN_PORT}. Log dedie : {LOG_PATH}."
    )
    return proc


# ── Anomalie connue : calendrier canonique UTC fixe vs activité live (DST) ──
# `core/v9/market_calendar.py` ancre l'ouverture/fermeture du marché sur 22h
# UTC fixe (`config.py` : MARKET_OPEN_UTC_HOUR/MARKET_CLOSE_UTC_HOUR),
# calibré sur l'heure d'hiver US (EST, UTC-5). Le marché forex réel ouvre/
# ferme à 17h heure de New York, soit 21h UTC pendant la période DST US
# (~mi-mars à début novembre, EDT UTC-4). Conséquence : chaque dimanche/
# vendredi en DST, il existe une fenêtre 21h-22h UTC où `is_market_open()`
# répond FERME alors que le marché réel (et donc le flux EA) est déjà actif.
# Corriger ce calcul canonique est hors périmètre de cette session (rouvrirait
# une décision Phase 7 canonisée et casserait les tests de
# `tests/test_market_calendar.py` qui figent l'hypothèse 22h UTC) — voir
# `workspace/perplexity/INCIDENTS.md` 2026-07-06. Ce module se contente de
# signaler la divergence à l'opérateur, sans jamais modifier le calendrier
# canonique ni sa source de vérité.
LIVE_ACTIVITY_WARNING_THRESHOLD_SECONDS = 90


def market_status_warning(
    market_open: bool, last_snapshot: dict | None, now_utc: datetime
) -> str | None:
    """Avertissement si le calendrier canonique dit FERME mais qu'un snapshot
    récent et non-stale indique une activité live réelle (cas typique :
    fenêtre DST US, voir commentaire ci-dessus). None si rien à signaler."""
    if market_open or not last_snapshot:
        return None
    if last_snapshot.get("stale"):
        return None
    created_at = last_snapshot.get("created_at")
    if not created_at:
        return None
    try:
        ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_seconds = (now_utc - ts.astimezone(timezone.utc)).total_seconds()
    if 0 <= age_seconds <= LIVE_ACTIVITY_WARNING_THRESHOLD_SECONDS:
        return (
            f"activite live detectee (dernier snapshot il y a {int(age_seconds)}s) "
            "alors que le calendrier canonique (UTC fixe) dit FERME — "
            "possible fenetre DST US, voir INCIDENTS.md"
        )
    return None


# ── Health snapshot ───────────────────────────────────────
def _db_counts() -> dict:
    """Compteurs bruts par table, lecture seule. Retourne un dict vide si
    la DB n'existe pas encore (pas une erreur — cas attendu avant --boot)."""
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(str(DB_PATH))
    counts = {}
    for table in ("forces_snapshots", "scenes", "behaviors", "windows", "exploitability"):
        try:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            counts[table] = None
    last = conn.execute(
        "SELECT created_at, symbol, timeframe, stale FROM forces_snapshots "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone() if counts.get("forces_snapshots") else None
    conn.close()
    if last:
        counts["last_snapshot"] = {
            "created_at": last[0], "symbol": last[1], "timeframe": last[2], "stale": bool(last[3]),
        }
    else:
        counts["last_snapshot"] = None
    return counts


def read_health_snapshot() -> dict:
    """Rassemble l'état système en un dict structuré : réutilisé par
    --health, et par les générateurs de mini-checkpoint des 3 autres
    scripts. Ne modifie rien (health check pur, lecture seule)."""
    now_utc = datetime.now(timezone.utc)
    server_running, server_pid = is_server_running()
    modules_ok = check_modules_importable()
    db_counts = _db_counts()
    market_open = MarketCalendar.is_market_open(now_utc)
    return {
        "timestamp_utc": now_utc.isoformat(timespec="seconds"),
        "python_ok": check_python_version(),
        "modules_ok": modules_ok,
        "modules_count": len(CORE_MODULES),
        "db_ok": check_db(),
        "port_available": is_port_available(LISTEN_PORT),
        "server_running": server_running,
        "server_pid": server_pid,
        "market_open": market_open,
        "market_session": MarketCalendar.current_session(now_utc),
        "market_status_warning": market_status_warning(
            market_open, db_counts.get("last_snapshot"), now_utc
        ),
        "db_counts": db_counts,
        "git_branch": git_branch(),
        "git_last_commit": git_last_commit(),
    }


def format_health_report(snapshot: dict) -> str:
    """Rendu texte lisible opérateur d'un health snapshot."""
    lines = ["=" * 60, "PowerFlow V9 - Health snapshot", "=" * 60]
    lines.append(f"Horodatage (UTC)      : {snapshot['timestamp_utc']}")
    lines.append(f"Branche / commit      : {snapshot['git_branch']} / {snapshot['git_last_commit']}")
    lines.append(f"Python 3.11+          : {'OK' if snapshot['python_ok'] else 'FAIL'}")
    lines.append(
        f"Modules core/v9/ ({snapshot['modules_count']}) : "
        f"{'OK' if snapshot['modules_ok'] else 'FAIL'}"
    )
    lines.append(f"Base de donnees       : {'OK' if snapshot['db_ok'] else 'FAIL'}")
    lines.append(
        f"Port {LISTEN_PORT}            : "
        f"{'libre' if snapshot['port_available'] else 'occupe'}"
    )
    server_state = "actif" if snapshot["server_running"] else "inactif"
    pid_suffix = f" (PID {snapshot['server_pid']})" if snapshot["server_running"] else ""
    lines.append(f"Serveur de capture    : {server_state}{pid_suffix}")
    market_state = "OUVERT" if snapshot["market_open"] else "FERME"
    lines.append(f"Marche                : {market_state} (session: {snapshot['market_session']})")
    if snapshot.get("market_status_warning"):
        lines.append(f"  ATTENTION           : {snapshot['market_status_warning']}")

    counts = snapshot.get("db_counts") or {}
    if counts:
        lines.append("-" * 60)
        for table in ("forces_snapshots", "scenes", "behaviors", "windows", "exploitability"):
            if table in counts:
                lines.append(f"  {table:<18}: {counts[table]}")
        last = counts.get("last_snapshot")
        if last:
            lines.append(
                f"  dernier snapshot  : {last['created_at']} {last['symbol']} "
                f"tf={last['timeframe']} stale={last['stale']}"
            )
    lines.append("=" * 60)
    return "\n".join(lines)


# ── Génération de mini-checkpoint ─────────────────────────
# Réutilise TEL QUEL le gabarit de `workspace/perplexity/assets/CHECKPOINT_TEMPLATE.md`
# §« Mini-checkpoint (usage workspace uniquement) ». Aucune duplication de contenu
# hors de ce module (DOC_GOVERNANCE.md règle 8) : ce dict n'est qu'un remplissage
# mécanique des 5 sections déjà définies par ce gabarit, jamais une redéfinition.
_MINI_CHECKPOINT_TEMPLATE = """## Mini-checkpoint — {horodatage}
### Contexte
{contexte}

### Observé
{observe}

### Écart vs attendu
{ecart}

### Action immédiate
{action}

### Suite
{suite}
"""


def generate_mini_checkpoint(
    kind: str,
    contexte: str,
    observed_lines: list[str],
    ecart: str = "Aucun ecart releve automatiquement — a completer par l'operateur si pertinent.",
    action: str = "Aucune (observation uniquement) — a completer par l'operateur si pertinent.",
    suite: str = "A completer par l'operateur (ACTIVE_TASKS.md / INCIDENTS.md / memory/DECISIONS_LOG.md).",
) -> Path:
    """Remplit le gabarit mini-checkpoint existant et l'écrit dans
    `workspace/perplexity/mini_checkpoints/` (jamais `docs/checkpoints/`,
    réservé aux checkpoints de phase officiels — voir gabarit source).
    Ne nécessite pas d'entrée `docs/DOC_REGISTRY.yml` (mini-checkpoint =
    hors registre, par définition du gabarit source)."""
    now = datetime.now(timezone.utc)
    horodatage = now.strftime("%Y-%m-%d %H:%M UTC")
    observe = "\n".join(f"- {line}" for line in observed_lines) if observed_lines else "- (aucune observation)"
    content = _MINI_CHECKPOINT_TEMPLATE.format(
        horodatage=horodatage, contexte=contexte, observe=observe,
        ecart=ecart, action=action, suite=suite,
    )
    MINI_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{kind}.md"
    path = MINI_CHECKPOINT_DIR / filename
    path.write_text(content, encoding="utf-8")
    return path


def health_snapshot_to_observed_lines(snapshot: dict) -> list[str]:
    """Traduit un health snapshot en puces factuelles pour la section
    « Observé » d'un mini-checkpoint (faits bruts, pas d'interprétation)."""
    lines = [
        f"Python 3.11+ : {'OK' if snapshot['python_ok'] else 'FAIL'}",
        f"Modules core/v9/ importables : {'OK' if snapshot['modules_ok'] else 'FAIL'}",
        f"Base de donnees : {'OK' if snapshot['db_ok'] else 'FAIL'}",
        f"Port {LISTEN_PORT} : {'libre' if snapshot['port_available'] else 'occupe'}",
        f"Serveur de capture : {'actif (PID ' + str(snapshot['server_pid']) + ')' if snapshot['server_running'] else 'inactif'}",
        f"Marche : {'OUVERT' if snapshot['market_open'] else 'FERME'} (session: {snapshot['market_session']})",
    ]
    if snapshot.get("market_status_warning"):
        lines.append(f"ATTENTION : {snapshot['market_status_warning']}")
    counts = snapshot.get("db_counts") or {}
    if counts.get("forces_snapshots") is not None:
        lines.append(f"forces_snapshots total : {counts['forces_snapshots']}")
    last = counts.get("last_snapshot")
    if last:
        lines.append(
            f"Dernier snapshot : {last['created_at']} {last['symbol']} "
            f"tf={last['timeframe']} stale={last['stale']}"
        )
    return lines


# ── CLI ────────────────────────────────────────────────────
def run_health() -> int:
    logger = setup_logging("v9.supervisor")
    snapshot = read_health_snapshot()
    print(format_health_report(snapshot))
    blocking_ok = snapshot["python_ok"] and snapshot["modules_ok"] and snapshot["db_ok"]
    if not blocking_ok:
        logger.error("Health check : au moins une verification bloquante a echoue.")
        return 1
    logger.info("Health check : toutes les verifications bloquantes sont passees.")
    return 0


# ── Auto-restart serveur capture ────────────────────────────
def run_autorestart() -> int:
    """Garantit que le serveur de capture tourne (VPS H24, cron 5 min).

    Logique :
    1. Vérifie l'état du serveur via PID file (is_server_running).
    2. S'il est déjà actif et que le port est légitimement occupé → exit 0.
    3. Sinon (serveur inactif OU port stale OU PID file périmé) :
       a. Libère le port si bloqué par un process stale.
       b. Démarre un nouveau serveur de capture en arrière-plan.
    4. Émet une alerte Telegram best-effort sur tout redémarrage effectif
       (règle 18 : non bloquant).
    5. Écrit l'événement dans logs/v9_ops.log.

    Idempotent : peut être appelé toutes les 5 min sans effet de bord.
    N'altère pas core/v9/*, ne touche pas la DB, n'écrit dans v9_forces.db.
    """
    logger = setup_logging("v9.supervisor.autorestart")
    running, own_pid = is_server_running()
    port_busy = not is_port_available(LISTEN_PORT, LISTEN_HOST)
    pid_on_port = find_pid_on_port(LISTEN_PORT)

    # Cas 1 : serveur déjà vivant et légitimement sur le port → rien à faire.
    if running and pid_on_port is not None and pid_on_port == own_pid:
        logger.info(
            f"Auto-restart : serveur deja actif (PID {own_pid}, port {LISTEN_PORT} "
            f"legitimement occupe). Aucune action."
        )
        return 0

    # Cas 2 : décision de redémarrer.
    reason_parts = []
    if not running:
        reason_parts.append(
            f"serveur inactif (PID file={'present' if own_pid else 'absent'}, "
            f"pid_recorded={own_pid})"
        )
    if not port_busy:
        reason_parts.append(f"port {LISTEN_PORT} libre")
    elif pid_on_port != own_pid:
        reason_parts.append(
            f"port {LISTEN_PORT} occupe par PID stale {pid_on_port} "
            f"(différent du PID file {own_pid})"
        )
    reason = " ; ".join(reason_parts) or "etat indefini"

    logger.warning(f"Auto-restart declenche. Raison : {reason}")

    # Libère le port si nécessaire.
    ensure_port_free(LISTEN_PORT, logger)

    # Démarre le nouveau serveur.
    start_capture_server_background(logger)

    # Alerte Telegram best-effort (config via .env, jamais bloquant).
    try:
        env_path = ROOT_DIR / ".env"
        env = dict(os.environ)
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
        token = env.get("TELEGRAM_BOT_TOKEN")
        chat_id = env.get("TELEGRAM_CHAT_ID")
        if token and chat_id:
            text = (
                f"⚠️ V9 AUTO-RESTART — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"Raison : {reason}\n"
                f"Nouveau serveur demarre sur {LISTEN_HOST}:{LISTEN_PORT}.\n"
                f"Pipeline remis en ligne automatiquement."
            )
            import json as _json  # local import : evite pollution namespace
            from urllib.request import Request, urlopen
            from urllib.error import URLError
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = _json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
            req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urlopen(req, timeout=10) as resp:
                    _json.loads(resp.read().decode("utf-8"))
                    logger.info("Alerte Telegram auto-restart envoyee.")
            except (URLError, OSError, _json.JSONDecodeError) as exc:
                logger.warning(f"Envoi Telegram auto-restart echoue (best-effort): {exc}")
        else:
            logger.info("Telegram non configure : alerte auto-restart non envoyee (log uniquement).")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Alerte Telegram auto-restart echouee (best-effort): {exc}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Supervision et automatisation operationnelle PowerFlow V9"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--boot", action="store_true", help="Procedure de reboot machine (delegue a v9_bootstrap.py)")
    group.add_argument("--health", action="store_true", help="Health snapshot immediat (lecture seule)")
    group.add_argument("--market-open", action="store_true", help="Procedure d'ouverture marche (delegue a v9_market_open.py)")
    group.add_argument("--resume", action="store_true", help="Reprise de session (delegue a v9_session_resume.py)")
    group.add_argument("--autorestart", action="store_true", help="Garantit que le serveur de capture tourne (VPS H24, cron 5min)")
    args = parser.parse_args()

    if args.health:
        return run_health()
    if args.boot:
        from scripts.v9_bootstrap import run_boot
        return run_boot()
    if args.market_open:
        from scripts.v9_market_open import run_market_open
        return run_market_open()
    if args.resume:
        from scripts.v9_session_resume import run_resume
        return run_resume()
    if args.autorestart:
        return run_autorestart()
    return 1


if __name__ == "__main__":
    sys.exit(main())
