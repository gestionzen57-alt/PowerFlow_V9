#!/usr/bin/env python3
"""v9_heartbeat.py — Watchdog + heartbeat Telegram pour V9 sur VPS H24.

Vérifie toutes les N minutes que le pipeline V9 est vivant :
  1. Port 31685 (LISTEN_PORT) occupé (= serveur de capture MT4 actif)
  2. DB SQLite accessible + snapshot récent (< seuil stale)
  3. Compteur d'échecs consécutifs (3 = alerte Telegram "pipeline down")

Couches cognitive : outillage d'observation. Aucune écriture dans v9_forces.db,
aucune logique de trading, aucune modification de core/v9/*.

Modes :
  --check        : un seul check, exit 0 si OK / 1 si KO (cron 5min)
  --heartbeat    : check + envoie Telegram "alive" toutes les HEARTBEAT_INTERVAL_MIN
  --reset        : remet à zéro le compteur d'échecs (après recovery manuel)

Fichiers d'état (logs/) :
  .heartbeat_state.json   → état compteur + last_alive + last_check_utc
  heartbeat.log           → log dédié

Usage :
  python scripts/v9_heartbeat.py --check
  python scripts/v9_heartbeat.py --heartbeat
  python scripts/v9_heartbeat.py --reset
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH, LISTEN_HOST, LISTEN_PORT  # noqa: E402
from scripts.deploy_v9 import check_db  # noqa: E402
from scripts.v9_supervisor import is_port_available  # noqa: E402

# ── Chemins ────────────────────────────────────────────────
HEARTBEAT_STATE_PATH = ROOT_DIR / "logs" / ".heartbeat_state.json"
HEARTBEAT_LOG_PATH = ROOT_DIR / "logs" / "heartbeat.log"

# ── Constantes watchdog ────────────────────────────────────
MAX_CONSECUTIVE_FAILURES = 3       # 3 checks ratés (5min × 3 = 15min) → alerte
STALE_SNAPSHOT_MINUTES = 30        # au-delà, le pipeline est considéré stale
HEARTBEAT_INTERVAL_MIN = 60        # Telegram "alive" toutes les 60 min
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# ── Logging ─────────────────────────────────────────────────
def setup_logging() -> logging.Logger:
    logger = logging.getLogger("v9_heartbeat")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(HEARTBEAT_LOG_PATH, encoding="utf-8")
        sh = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        fh.setFormatter(fmt)
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
    return logger


log = setup_logging()


# ── État persistant ─────────────────────────────────────────
def load_state() -> dict:
    """Charge l'état watchdog (compteur échecs, last_alive, last_check)."""
    if HEARTBEAT_STATE_PATH.exists():
        try:
            return json.loads(HEARTBEAT_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("État corrompu, reset: %s", e)
    return {
        "consecutive_failures": 0,
        "last_alive_utc": None,
        "last_check_utc": None,
        "last_alert_utc": None,
    }


def save_state(state: dict) -> None:
    HEARTBEAT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── Checks ──────────────────────────────────────────────────
def check_server_alive() -> tuple[bool, str]:
    """Le port 31685 est-il occupé (= serveur de capture MT4 tourne) ?"""
    available = is_port_available(LISTEN_PORT, LISTEN_HOST)
    if available:
        return False, f"Port {LISTEN_PORT} libre (serveur inactif)"
    return True, f"Port {LISTEN_PORT} occupé (serveur actif)"


def check_db_fresh() -> tuple[bool, str]:
    """La DB est-elle accessible et contient-elle un snapshot < 30 min ?

    Note : la table s'appelle `forces_snapshots` (cf. core/v9/db_schema.py),
    pas `snapshots` (corrigé 2026-07-07 — bug heartbeat 18 échecs consécutifs).
    """
    try:
        if not check_db():
            return False, "DB inaccessible ou schéma invalide"
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT MAX(bar_time) FROM forces_snapshots"
            ).fetchone()
        if not row or not row[0]:
            return False, "Aucun snapshot en DB"
        # bar_time stocké en epoch UTC (secondes) cf. core/v9/db_schema.py
        last_bar_epoch = row[0]
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        age_min = (now_epoch - last_bar_epoch) / 60.0
        if age_min > STALE_SNAPSHOT_MINUTES:
            return False, f"Dernier snapshot il y a {age_min:.1f} min (seuil {STALE_SNAPSHOT_MINUTES})"
        return True, f"Dernier snapshot il y a {age_min:.1f} min"
    except sqlite3.Error as e:
        return False, f"Erreur SQLite: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"Erreur inattendue: {e}"


def run_full_check() -> tuple[bool, list[str]]:
    """Exécute tous les checks, retourne (global_ok, [messages])."""
    msgs = []
    srv_ok, srv_msg = check_server_alive()
    db_ok, db_msg = check_db_fresh()
    msgs.append(f"  Serveur : {srv_msg}")
    msgs.append(f"  DB      : {db_msg}")
    return srv_ok and db_ok, msgs


# ── Telegram ────────────────────────────────────────────────
def load_telegram_config() -> dict | None:
    """Lit TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID depuis env (.env ou os.environ)."""
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
    if not token or not chat_id:
        return None
    return {"token": token, "chat_id": chat_id}


def send_telegram(text: str, config: dict[str, str]) -> bool:
    """Envoi Telegram best-effort (règle 18 : LLM/Telegram non bloquant)."""
    url = TELEGRAM_API.format(token=config["token"])
    payload = json.dumps({"chat_id": config["chat_id"], "text": text}).encode("utf-8")
    req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok"))
    except (URLError, json.JSONDecodeError, OSError) as e:
        log.warning("Envoi Telegram échoué: %s", e)
        return False


def maybe_send_alive(state: dict, config: dict[str, str] | None) -> None:
    """Envoie Telegram 'alive' toutes les HEARTBEAT_INTERVAL_MIN si OK."""
    if not config:
        return
    now = datetime.now(timezone.utc)
    last_alive = state.get("last_alive_utc")
    if last_alive:
        try:
            last_dt = datetime.fromisoformat(last_alive)
            if (now - last_dt) < timedelta(minutes=HEARTBEAT_INTERVAL_MIN):
                return
        except ValueError:
            pass
    text = (
        f"✅ V9 alive — {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Pipeline stable, surveillance H24 active."
    )
    if send_telegram(text, config):
        state["last_alive_utc"] = now.isoformat()
        log.info("Heartbeat Telegram envoyé.")


def maybe_send_alert(state: dict, reason: str, config: dict[str, str] | None) -> None:
    """Envoie alerte Telegram si 3 échecs consécutifs (anti-doublon: 1/h max)."""
    if not config:
        log.error("ALERTE (Telegram non configuré): %s", reason)
        return
    now = datetime.now(timezone.utc)
    last_alert = state.get("last_alert_utc")
    if last_alert:
        try:
            last_dt = datetime.fromisoformat(last_alert)
            if (now - last_dt) < timedelta(hours=1):
                log.warning("Alerte déjà envoyée il y a < 1h, on n'envoie pas de doublon.")
                return
        except ValueError:
            pass
    text = (
        f"❌ V9 PIPELINE DOWN — {now.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Raison : {reason}\n"
        f"Échecs consécutifs : {state['consecutive_failures']}\n"
        f"Action requise : vérifier le serveur de capture / DB / réseau VPS."
    )
    if send_telegram(text, config):
        state["last_alert_utc"] = now.isoformat()
        log.error("ALERTE Telegram envoyée: %s", reason)


# ── Modes CLI ───────────────────────────────────────────────
def cmd_check() -> int:
    """Un check, exit 0 OK / 1 KO. Pour cron 5min."""
    state = load_state()
    ok, msgs = run_full_check()
    state["last_check_utc"] = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)
    log.info("Check @ %s — %s", now.strftime("%H:%M:%S"), "OK" if ok else "KO")
    for m in msgs:
        log.info(m)
    if ok:
        state["consecutive_failures"] = 0
    else:
        state["consecutive_failures"] += 1
        if state["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            cfg = load_telegram_config()
            reason = "; ".join(line.strip() for line in msgs)
            maybe_send_alert(state, reason, cfg)
    save_state(state)
    return 0 if ok else 1


def cmd_heartbeat() -> int:
    """Check + Telegram 'alive' toutes les HEARTBEAT_INTERVAL_MIN."""
    state = load_state()
    ok, msgs = run_full_check()
    state["last_check_utc"] = datetime.now(timezone.utc).isoformat()
    if ok:
        cfg = load_telegram_config()
        maybe_send_alive(state, cfg)
        state["consecutive_failures"] = 0
    else:
        state["consecutive_failures"] += 1
        if state["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            cfg = load_telegram_config()
            reason = "; ".join(line.strip() for line in msgs)
            maybe_send_alert(state, reason, cfg)
    save_state(state)
    return 0 if ok else 1


def cmd_reset() -> int:
    """Reset manuel du compteur (après recovery)."""
    state = load_state()
    state["consecutive_failures"] = 0
    state["last_alert_utc"] = None
    save_state(state)
    log.info("Compteur d'échecs reset.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="V9 heartbeat / watchdog (VPS H24)")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="Check unique (cron 5min)")
    g.add_argument("--heartbeat", action="store_true", help="Check + Telegram alive/alert")
    g.add_argument("--reset", action="store_true", help="Reset compteur d'échecs")
    args = parser.parse_args()
    if args.reset:
        return cmd_reset()
    if args.heartbeat:
        return cmd_heartbeat()
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())