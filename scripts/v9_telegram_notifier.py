#!/usr/bin/env python3
"""v9_telegram_notifier.py — Alertes Telegram live sur décisions GBPUSD.

Polling toutes les 60s sur la table `decisions` de v9_forces.db.
Filtre : symbol='GBPUSD', confiance > 65, direction != 'neutre'.
Anti-doublon par decision_id (fichier local .last_sent_id).
Enrichissement depuis principle_evaluations et scenes.

Couche cognitive : outillage de notification uniquement.
Aucune écriture dans v9_forces.db, aucune logique de trading,
aucune modification de core/v9/*.

Usage :
    python scripts/v9_telegram_notifier.py --watch        # boucle live
    python scripts/v9_telegram_notifier.py --once         # un seul cycle
    python scripts/v9_telegram_notifier.py --test-message  # envoie un message test
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402

# ── Chemins ───────────────────────────────────────────────
LAST_SENT_PATH = ROOT_DIR / "logs" / ".telegram_last_sent_id"
LOG_PATH = ROOT_DIR / "logs" / "telegram_notifier.log"
CONFIG_PATH = ROOT_DIR / "config" / "telegram.json"

# ── Constantes ─────────────────────────────────────────────
POLL_INTERVAL_S = 60
CONFIANCE_MIN = 65
SYMBOL = "GBPUSD"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# ── Logger ────────────────────────────────────────────────
logger = logging.getLogger("v9.telegram_notifier")


def _setup_logging() -> None:
    """Configure le logger fichier + console (pattern v9_supervisor)."""
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(str(LOG_PATH), encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)


# ── Config Telegram ───────────────────────────────────────
def load_telegram_config() -> dict[str, str]:
    """Charge BOT_TOKEN et CHAT_ID depuis config/telegram.json."""
    if not CONFIG_PATH.exists():
        logger.error(
            "Fichier config/telegram.json introuvable. "
            "Copier config/telegram.json.example et renseigner les champs."
        )
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    token = cfg.get("BOT_TOKEN", "").strip()
    chat_id = cfg.get("CHAT_ID", "").strip()
    if not token or not chat_id or token == "TON_TOKEN_ICI":
        logger.error(
            "BOT_TOKEN ou CHAT_ID manquant ou non renseigné dans config/telegram.json."
        )
        sys.exit(1)
    return {"token": token, "chat_id": chat_id}


# ── Anti-doublon ──────────────────────────────────────────
def _read_last_sent_id() -> str | None:
    """Retourne le dernier decision_id envoyé, ou None."""
    if LAST_SENT_PATH.exists():
        val = LAST_SENT_PATH.read_text(encoding="utf-8").strip()
        return val if val else None
    return None


def _write_last_sent_id(decision_id: str) -> None:
    """Persiste le dernier decision_id envoyé."""
    LAST_SENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_SENT_PATH.write_text(decision_id, encoding="utf-8")


# ── Requête DB ────────────────────────────────────────────
def _fetch_new_decisions(cursor: sqlite3.Cursor, last_id: str | None) -> list[dict[str, Any]]:
    """Récupère les décisions GBPUSD non neutres avec confiance > 65.

    Si last_id est fourni, ne retourne que les décisions plus récentes.
    """
    if last_id:
        query = """
            SELECT decision_id, timestamp, direction, confiance,
                   principes_json, regime_type, scene_id, behavior_id,
                   snapshot_id, symbol
            FROM decisions
            WHERE symbol = ?
              AND direction != 'neutre'
              AND confiance > ?
              AND decision_id > ?
            ORDER BY timestamp ASC
        """
        cursor.execute(query, (SYMBOL, CONFIANCE_MIN, last_id))
    else:
        query = """
            SELECT decision_id, timestamp, direction, confiance,
                   principes_json, regime_type, scene_id, behavior_id,
                   snapshot_id, symbol
            FROM decisions
            WHERE symbol = ?
              AND direction != 'neutre'
              AND confiance > ?
            ORDER BY timestamp ASC
        """
        cursor.execute(query, (SYMBOL, CONFIANCE_MIN))

    cols = ["decision_id", "timestamp", "direction", "confiance",
            "principes_json", "regime_type", "scene_id", "behavior_id",
            "snapshot_id", "symbol"]
    rows = []
    for r in cursor.fetchall():
        row = dict(zip(cols, r))
        # Parse principes_json
        if isinstance(row["principes_json"], str):
            try:
                row["principes"] = json.loads(row["principes_json"])
            except (json.JSONDecodeError, TypeError):
                row["principes"] = []
        else:
            row["principes"] = row["principes_json"] or []
        rows.append(row)
    return rows


def _enrich_decision(cursor: sqlite3.Cursor, decision: dict[str, Any]) -> dict[str, Any]:
    """Enrichit une décision avec les données de scène, comportement, TF alignés."""
    # ── Scene type depuis zone_json ──
    scene_type = "N/A"
    if decision.get("scene_id"):
        cursor.execute(
            "SELECT zone_json, confluences_mtf_json FROM scenes WHERE scene_id = ?",
            (decision["scene_id"],),
        )
        sc_row = cursor.fetchone()
        if sc_row:
            zj_raw, mtf_raw = sc_row
            if zj_raw:
                try:
                    zj = json.loads(zj_raw)
                    scene_type = zj.get("structure", "N/A")
                except (json.JSONDecodeError, TypeError):
                    pass
            # ── TF alignés depuis confluences_mtf_json ──
            tfs = _extract_tf_alignes(mtf_raw)
            decision["tf_alignes"] = tfs

    decision["scene_type"] = scene_type

    # ── Behavior qualification ──
    if decision.get("behavior_id"):
        cursor.execute(
            "SELECT qualification FROM behaviors WHERE behavior_id = ?",
            (decision["behavior_id"],),
        )
        beh_row = cursor.fetchone()
        if beh_row:
            decision["behavior_qualification"] = beh_row[0]

    # ── Principes actifs depuis principle_evaluations ──
    if decision.get("snapshot_id"):
        cursor.execute(
            "SELECT principle_id, confidence, direction FROM principle_evaluations "
            "WHERE snapshot_id = ? AND triggered = 1",
            (decision["snapshot_id"],),
        )
        triggered = cursor.fetchall()
        if triggered:
            decision["principes_actifs"] = [
                {"id": p[0], "confidence": p[1], "direction": p[2]} for p in triggered
            ]

    return decision


def _extract_tf_alignes(mtf_raw: str | None) -> list[str]:
    """Extrait la liste des TF alignés depuis confluences_mtf_json.

    Exemple de retour : ["D1→H4", "H4→H1"]
    """
    if not mtf_raw:
        return []
    try:
        mtf = json.loads(mtf_raw)
    except (json.JSONDecodeError, TypeError):
        return []
    cascades = mtf.get("cascades_temporelles", [])
    tfs = []
    for c in cascades:
        de = c.get("de_timeframe", "")
        vers = c.get("vers_timeframe", "")
        if de and vers:
            tfs.append(f"{de}→{vers}")
    return tfs


# ── Format message ────────────────────────────────────────
def _format_message(d: dict[str, Any]) -> str:
    """Formate une décision en message Telegram structuré."""
    # Timestamp → CEST (UTC+2)
    ts_raw = d.get("timestamp", "")
    try:
        if ts_raw.endswith("Z"):
            ts_raw = ts_raw[:-1] + "+00:00"
        dt_utc = datetime.fromisoformat(ts_raw)
    except (ValueError, TypeError):
        dt_utc = datetime.now(timezone.utc)
    dt_cest = dt_utc.astimezone(timezone(timedelta(hours=2)))
    ts_cest = dt_cest.strftime("%Y-%m-%d %H:%M:%S")

    direction = d.get("direction", "neutre").upper()
    confiance = d.get("confiance", 0)
    emoji = "🟢" if direction == "HAUSSIERE" else "🔴"

    # TF alignés
    tf_alignes = d.get("tf_alignes", [])
    tf_str = ", ".join(tf_alignes) if tf_alignes else "aucun"

    # Principes
    principes = d.get("principes", [])
    # Fallback sur principes_actifs enrichis
    if not principes and d.get("principes_actifs"):
        principes = [p["id"] for p in d["principes_actifs"]]
    principes_str = ", ".join(principes) if principes else "aucun"

    # Scène
    scene_type = d.get("scene_type", "N/A")
    regime_type = d.get("regime_type", "N/A")

    # Comportement
    behavior = d.get("behavior_qualification", "")
    scene_part = scene_type
    if behavior:
        scene_part += f" | {behavior}"

    lines = [
        f"{emoji} GBPUSD — {ts_cest}",
        f"Direction : {direction} | Conf : {confiance}%",
        f"TF alignés : {tf_str}",
        f"Principes : {principes_str}",
        f"Scène : {scene_part} | Régime : {regime_type}",
    ]
    return "\n".join(lines)


# ── Envoi Telegram ─────────────────────────────────────────
def send_telegram(text: str, config: dict[str, str]) -> bool:
    """Envoie un message via l'API Telegram. Retourne True si succès."""
    url = TELEGRAM_API.format(token=config["token"])
    payload = json.dumps({
        "chat_id": config["chat_id"],
        "text": text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                logger.info("Message Telegram envoyé avec succès.")
                return True
            else:
                logger.warning("Telegram API a retourné ok=false : %s", body)
                return False
    except urllib.error.URLError as e:
        logger.error("Erreur réseau Telegram : %s", e)
        return False
    except json.JSONDecodeError as e:
        logger.error("Réponse Telegram invalide : %s", e)
        return False


# ── Cycle de polling ──────────────────────────────────────
def _poll_once(config: dict[str, str], last_id: str | None) -> str | None:
    """Exécute un cycle de polling : requête DB → envoi → retourne last_id."""
    if not DB_PATH.exists():
        logger.warning("DB introuvable : %s", DB_PATH)
        return last_id

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
    except sqlite3.Error as e:
        logger.error("Erreur connexion DB : %s", e)
        return last_id

    try:
        decisions = _fetch_new_decisions(cursor, last_id)
        if not decisions:
            return last_id

        logger.info("Nouvelles décisions détectées : %d", len(decisions))
        for d in decisions:
            d = _enrich_decision(cursor, d)
            msg = _format_message(d)
            logger.debug("Message à envoyer :\n%s", msg)
            ok = send_telegram(msg, config)
            if ok:
                last_id = d["decision_id"]
                _write_last_sent_id(last_id)
            else:
                logger.warning("Échec envoi pour %s — on continue", d["decision_id"])
    except sqlite3.Error as e:
        logger.error("Erreur DB pendant le cycle : %s", e)
    finally:
        conn.close()

    return last_id


# ── CLI ────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Alertes Telegram live sur décisions GBPUSD PowerFlow V9."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Boucle de polling continue (toutes les 60s).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Un seul cycle de polling puis sortie.",
    )
    parser.add_argument(
        "--test-message",
        action="store_true",
        help="Envoie un message test de vérification.",
    )
    return parser.parse_args()


def _send_test_message(config: dict[str, str]) -> None:
    """Envoie un message test pour vérifier la configuration Telegram."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = (
        "🧪 TEST — Notificateur Telegram PowerFlow V9\n"
        f"Timestamp : {now}\n"
        "Configuration OK — le bot est opérationnel."
    )
    ok = send_telegram(msg, config)
    if ok:
        logger.info("Message test envoyé avec succès.")
    else:
        logger.error("Échec de l'envoi du message test.")


def main() -> None:
    _setup_logging()
    args = _parse_args()

    config = load_telegram_config()

    if args.test_message:
        _send_test_message(config)
        return

    last_id = _read_last_sent_id()
    logger.info(
        "Démarrage notificateur Telegram (symbole=%s, confiance_min=%d, last_id=%s)",
        SYMBOL, CONFIANCE_MIN, last_id or "(aucun)",
    )

    if args.once:
        _poll_once(config, last_id)
        return

    if args.watch:
        logger.info("Mode WATCH — polling toutes les %d secondes.", POLL_INTERVAL_S)
        while True:
            try:
                last_id = _poll_once(config, last_id)
            except KeyboardInterrupt:
                logger.info("Arrêt demandé par l'opérateur.")
                break
            except Exception:
                logger.exception("Erreur inattendue dans la boucle de polling.")
            time.sleep(POLL_INTERVAL_S)
        return

    # Default : --once
    _poll_once(config, last_id)


if __name__ == "__main__":
    main()
