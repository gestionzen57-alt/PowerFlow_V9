#!/usr/bin/env python3
"""v9_telegram_notifier.py — Alertes Telegram live sur décisions GBPUSD.

Polling toutes les 60s sur la table `decisions` de v9_forces.db.
Filtre : symbol='GBPUSD', confiance > 65, direction != 'neutre'.
Anti-doublon par decision_id (fichier local .last_sent_id).
Enrichissement depuis principle_evaluations et scenes.

Mode watch : boucle bidirectionnelle — alerte les nouvelles décisions,
répond aux commandes Telegram (/status, /last, /pause, /resume, /help)
ET forwarde le texte libre vers Hermes pour une conversation avec mémoire.

Couche cognitive : outillage de notification uniquement.
Aucune écriture dans v9_forces.db, aucune logique de trading,
aucune modification de core/v9/*.

Usage :
    python scripts/v9_telegram_notifier.py --watch        # boucle live + commandes + chat
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
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402

# ── Chemins ───────────────────────────────────────────────
LAST_SENT_PATH = ROOT_DIR / "logs" / ".telegram_last_sent_id"
OFFSET_PATH = ROOT_DIR / "logs" / ".telegram_offset"
PAUSED_PATH = ROOT_DIR / "logs" / ".telegram_paused"
CONVERSATION_PATH = ROOT_DIR / "logs" / ".telegram_conversation.json"
LOG_PATH = ROOT_DIR / "logs" / "telegram_notifier.log"
CONFIG_PATH = ROOT_DIR / "config" / "telegram.json"

# ── Constantes ─────────────────────────────────────────────
POLL_INTERVAL_S = 60
CONFIANCE_MIN = 65
SYMBOL = "GBPUSD"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
GET_UPDATES_API = "https://api.telegram.org/bot{token}/getUpdates"
CEST_OFFSET = timedelta(hours=2)
MAX_CONVERSATION_TURNS = 20  # garde-fou mémoire : 20 échanges max
HERMES_TIMEOUT_S = 60        # timeout pour la réponse Hermes

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


# ── Persistance fichiers ──────────────────────────────────
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


def _read_offset() -> int:
    """Retourne le dernier offset getUpdates, ou 0."""
    if OFFSET_PATH.exists():
        val = OFFSET_PATH.read_text(encoding="utf-8").strip()
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return 0


def _write_offset(offset: int) -> None:
    """Persiste l'offset getUpdates."""
    OFFSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(str(offset), encoding="utf-8")


def _is_paused() -> bool:
    """Retourne True si les alertes automatiques sont suspendues."""
    if PAUSED_PATH.exists():
        return PAUSED_PATH.read_text(encoding="utf-8").strip() == "1"
    return False


def _set_paused(paused: bool) -> None:
    """Persiste l'état pause (1 = suspendu, 0 = actif)."""
    PAUSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAUSED_PATH.write_text("1" if paused else "0", encoding="utf-8")


# ── Mémoire de conversation Hermes ───────────────────────
def _load_conversation() -> list[dict[str, str]]:
    """Charge l'historique de conversation depuis le fichier JSON.

    Retourne une liste de {role, content} (max MAX_CONVERSATION_TURNS échanges).
    """
    if not CONVERSATION_PATH.exists():
        return []
    try:
        data = json.loads(CONVERSATION_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[-MAX_CONVERSATION_TURNS:]
    except (json.JSONDecodeError, ValueError):
        logger.warning("Fichier conversation corrompu, réinitialisation.")
    return []


def _save_conversation(conversation: list[dict[str, str]]) -> None:
    """Sauvegarde l'historique de conversation (tronqué à MAX_CONVERSATION_TURNS)."""
    CONVERSATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = conversation[-MAX_CONVERSATION_TURNS:]
    CONVERSATION_PATH.write_text(
        json.dumps(trimmed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _call_hermes(user_text: str, conversation: list[dict[str, str]]) -> str:
    """Envoie un message à l'API LLM (Ollama Cloud) avec mémoire de conversation.

    Appel API direct — réponse en 2-3 secondes, pas de sous-process Hermes.
    Utilise le modèle qwen3-coder-next:cloud via Ollama Cloud.
    """
    api_key = _read_ollama_key()
    if not api_key:
        return "⚠️ Clé API Ollama Cloud non configurée."

    # Construire les messages avec historique
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es Hermes, assistant PowerFlow V9. "
                "Réponds en français, sois concis et précis. "
                "Tu aides un trader à analyser le marché GBPUSD. "
                "Tu peux suggérer d'utiliser /status ou /last pour des données live."
            ),
        }
    ]
    # Ajouter l'historique (max 10 derniers échanges pour éviter de dépasser le contexte)
    for turn in conversation[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    # Ajouter le message actuel
    messages.append({"role": "user", "content": user_text})

    payload = json.dumps({
        "model": "qwen3-coder-next:cloud",
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://ollama.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            msg = body["choices"][0]["message"]
            # Certains modèles (deepseek-v4-flash) mettent la réponse
            # dans 'reasoning' plutôt que 'content'
            content = (msg.get("content") or msg.get("reasoning") or "").strip()
            if content:
                return content
            return "🤖 Pas de réponse."
    except urllib.error.HTTPError as e:
        logger.error("Erreur HTTP LLM : %s", e)
        return "⚠️ Erreur API LLM. Réessaie dans une minute."
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        logger.error("Erreur appel LLM : %s", e)
        return "⚠️ Erreur de communication. Réessaie plus tard."


def _read_ollama_key() -> str | None:
    """Lit la clé Ollama Cloud depuis le .env du profil powerflow."""
    env_paths = [
        Path("D:/hermes/profiles/powerflow/.env"),
        Path.home() / ".hermes" / ".env",
        Path.home() / ".hermes" / "profiles" / "powerflow" / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if "OLLAMA_API_KEY" in line:
                        key = line.split("=", 1)[1].strip().strip("\"'")
                        if key:
                            return key
            except Exception:
                pass
    return None


# ── Timestamp CEST format court ────────────────────────────
def _format_cest_timestamp(ts_raw: str | None) -> str:
    """Convertit un timestamp ISO UTC en format court CEST.

    Exemple : "2026-07-06T14:35:29.463604+00:00" → "06/07 16h35 CEST"
    """
    if not ts_raw:
        dt_utc = datetime.now(timezone.utc)
    else:
        try:
            if ts_raw.endswith("Z"):
                ts_raw = ts_raw[:-1] + "+00:00"
            dt_utc = datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            dt_utc = datetime.now(timezone.utc)
    dt_cest = dt_utc.astimezone(timezone(CEST_OFFSET))
    return dt_cest.strftime("%d/%m %Hh%M CEST")


# ── Format TF alignés (dédupliqué + compté + score) ───────
def _format_tf_alignes(tf_list: list[str]) -> str:
    """Formate les TF alignés : déduplication, comptage, score emoji.

    Exemple d'entrée : ["D1→H4", "D1→H4", "H4→H1", "H4→H1", "H1→M30"]
    Sortie : "🟢 D1→H4 ×2  H4→H1 ×2  H1→M30 ×1"
    """
    if not tf_list:
        return "⚠️ 0 TF alignés"

    counter = Counter(tf_list)
    # Trier par ordre décroissant de TF (D1 > H4 > H1 > M30 > M15 > M5)
    tf_order = {"D1": 6, "H4": 5, "H1": 4, "M30": 3, "M15": 2, "M5": 1}

    def _sort_key(item: tuple[str, int]) -> int:
        link = item[0]
        parts = link.split("→")
        if parts:
            return tf_order.get(parts[0], 0)
        return 0

    sorted_links = sorted(counter.items(), key=_sort_key, reverse=True)
    unique_count = len(sorted_links)

    # Score emoji
    if unique_count >= 5:
        score_emoji = "🟢"
    elif unique_count >= 3:
        score_emoji = "✅"
    else:
        score_emoji = "⚠️"

    parts = [f"{link} ×{count}" for link, count in sorted_links]
    return f"{score_emoji} {'  '.join(parts)}"


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
    """Formate une décision en message Telegram structuré (nouveau format)."""
    ts_cest = _format_cest_timestamp(d.get("timestamp", ""))

    direction = d.get("direction", "neutre").upper()
    confiance = d.get("confiance", 0)
    emoji = "🟢" if direction == "HAUSSIERE" else "🔴"

    # TF alignés formatés
    tf_alignes = d.get("tf_alignes", [])
    tf_str = _format_tf_alignes(tf_alignes)

    # Compter le nombre de TF uniques pour la ligne d'en-tête
    unique_tf_count = len(set(tf_alignes)) if tf_alignes else 0
    tf_score_emoji = "🟢" if unique_tf_count >= 5 else ("✅" if unique_tf_count >= 3 else "⚠️")

    # Principes
    principes = d.get("principes", [])
    if not principes and d.get("principes_actifs"):
        principes = [p["id"] for p in d["principes_actifs"]]
    principes_str = "\n".join(f"   {p}" for p in principes) if principes else "   aucun"

    # Scène
    scene_type = d.get("scene_type", "N/A")
    regime_type = d.get("regime_type", "N/A")
    behavior = d.get("behavior_qualification", "")
    scene_part = scene_type
    if behavior:
        scene_part += f" | {behavior}"

    lines = [
        "━" * 20,
        f"{emoji} GBPUSD — {ts_cest}",
        f"{direction} | {confiance}% | {tf_score_emoji} {unique_tf_count} TF alignés",
        "━" * 20,
        tf_str,
        "📊 Principes :",
        principes_str,
        f"🎯 Scène : {scene_part}",
        f"   Régime : {regime_type}",
        "━" * 20,
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


# ── Commandes Telegram entrantes ──────────────────────────
def _fetch_commands(config: dict[str, str]) -> list[dict[str, Any]]:
    """Récupère les messages entrants via getUpdates.

    Retourne une liste de messages (dict) avec 'text', 'chat_id', 'update_id'.
    Gère l'offset pour ne pas rejouer les anciens messages.
    """
    offset = _read_offset()
    url = f"{GET_UPDATES_API.format(token=config['token'])}?offset={offset}&timeout=5"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        logger.debug("Erreur getUpdates : %s", e)
        return []

    if not body.get("ok"):
        return []

    messages = []
    for update in body.get("result", []):
        update_id = update.get("update_id", 0)
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if text and chat_id:
            messages.append({
                "text": text,
                "chat_id": chat_id,
                "update_id": update_id,
            })
        # Toujours avancer l'offset (update_id + 1 = marquer comme lu)
        if update_id > offset:
            offset = update_id + 1

    if offset > _read_offset():
        _write_offset(offset)

    return messages


def _build_status_response(cursor: sqlite3.Cursor) -> str:
    """Construit la réponse /status : snapshot live du pipeline."""
    now_cest = _format_cest_timestamp(datetime.now(timezone.utc).isoformat())

    # Dernier signal
    cursor.execute("""
        SELECT direction, confiance, timestamp
        FROM decisions
        WHERE symbol = ? AND direction != 'neutre' AND confiance > ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (SYMBOL, CONFIANCE_MIN))
    last_sig = cursor.fetchone()

    # Principes actifs sur le dernier snapshot
    principes_str = "aucun"
    if last_sig:
        snap_id = last_sig[3] if len(last_sig) > 3 else None
        cursor.execute("""
            SELECT principle_id FROM principle_evaluations
            WHERE snapshot_id = ? AND triggered = 1
            ORDER BY confidence DESC
            LIMIT 3
        """, (snap_id,))
        triggered = cursor.fetchall()
        if triggered:
            principes_str = ", ".join(p[0] for p in triggered)

    # Scènes récentes
    cursor.execute("""
        SELECT COUNT(*) FROM scenes
        WHERE timestamp > datetime('now', '-10 minutes', 'utc')
    """)
    scenes_10min = cursor.fetchone()[0]

    # Régime actuel
    cursor.execute("""
        SELECT regime_type FROM regime_snapshots
        WHERE symbol = ? AND stale = 0
        ORDER BY timestamp DESC
        LIMIT 1
    """, (SYMBOL,))
    regime_row = cursor.fetchone()
    regime = regime_row[0] if regime_row else "N/A"

    if last_sig:
        direction = last_sig[0].upper()
        confiance = last_sig[1]
        ts_raw = last_sig[2] or ""
        try:
            ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - ts_dt
            ago = f"il y a {int(delta.total_seconds() // 60)} min"
        except (ValueError, TypeError):
            ago = "N/A"
        emoji = "🟢" if direction == "HAUSSIERE" else "🔴"
        signal_line = f"Dernier signal : {emoji} {direction} {confiance}% ({ago})"
    else:
        signal_line = "Aucun signal directionnel en base"

    lines = [
        f"📡 GBPUSD — {now_cest}",
        signal_line,
        f"Principes actifs : {principes_str}",
        f"Scènes last 10 min : {scenes_10min} | Régime : {regime}",
    ]
    return "\n".join(lines)


def _build_last_response(cursor: sqlite3.Cursor) -> str:
    """Construit la réponse /last : dernier signal complet."""
    cursor.execute("""
        SELECT decision_id, timestamp, direction, confiance,
               principes_json, regime_type, scene_id, behavior_id,
               snapshot_id
        FROM decisions
        WHERE symbol = ? AND direction != 'neutre' AND confiance > ?
        ORDER BY timestamp DESC
        LIMIT 1
    """, (SYMBOL, CONFIANCE_MIN))
    row = cursor.fetchone()
    if not row:
        return "Aucun signal directionnel en base pour GBPUSD."

    cols = ["decision_id", "timestamp", "direction", "confiance",
            "principes_json", "regime_type", "scene_id", "behavior_id",
            "snapshot_id"]
    d = dict(zip(cols, row))
    d = _enrich_decision(cursor, d)
    return _format_message(d)


def _handle_command(
    cmd: str,
    config: dict[str, str],
    cursor: sqlite3.Cursor,
    last_id: str | None,
) -> str | None:
    """Traite une commande Telegram. Retourne la réponse à envoyer, ou None si ignorée."""
    cmd_lower = cmd.lower().strip()

    if cmd_lower == "/status":
        return _build_status_response(cursor)

    if cmd_lower == "/last":
        return _build_last_response(cursor)

    if cmd_lower == "/pause":
        _set_paused(True)
        logger.info("Alertes Telegram suspendues par commande /pause")
        return "⏸ Alertes suspendues. Tape /resume pour réactiver."

    if cmd_lower == "/resume":
        _set_paused(False)
        logger.info("Alertes Telegram réactivées par commande /resume")
        return "▶️ Alertes actives."

    if cmd_lower == "/help":
        return (
            "📋 Commandes disponibles :\n"
            "/status — snapshot live du pipeline GBPUSD\n"
            "/last — dernier signal complet\n"
            "/pause — suspendre les alertes automatiques\n"
            "/resume — réactiver les alertes\n"
            "/help — cette aide\n\n"
            "💬 Texte libre — parle à Hermes directement !"
        )

    # Commande inconnue
    return "❓ Commande inconnue. Tape /help pour la liste des commandes."


# ── Cycle de polling ──────────────────────────────────────
def _poll_once(config: dict[str, str], last_id: str | None) -> str | None:
    """Exécute un cycle de polling : requête DB → envoi → retourne last_id.

    En mode watch, traite aussi les commandes entrantes et le texte libre.
    """
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
        # ── Traiter les messages entrants ──
        commands = _fetch_commands(config)
        for cmd_msg in commands:
            chat_id = cmd_msg["chat_id"]
            text = cmd_msg["text"]
            # Ne répondre que si le message vient de notre CHAT_ID
            if chat_id != config["chat_id"]:
                logger.debug("Message ignoré (chat_id différent) : %s", chat_id)
                continue

            if text.startswith("/"):
                # Commande → réponse locale
                response = _handle_command(text, config, cursor, last_id)
                if response:
                    send_telegram(response, config)
            else:
                # Texte libre → forward à Hermes avec mémoire
                logger.info("Message libre → Hermes : %s", text[:80])
                conversation = _load_conversation()
                # Ajouter le message utilisateur
                conversation.append({"role": "user", "content": text})
                # Appeler Hermes
                hermes_response = _call_hermes(text, conversation)
                # Ajouter la réponse à l'historique
                conversation.append({"role": "assistant", "content": hermes_response})
                _save_conversation(conversation)
                # Envoyer la réponse
                send_telegram(hermes_response, config)

        # ── Envoyer les nouvelles décisions (sauf si pause) ──
        if _is_paused():
            logger.debug("Alertes suspendues — aucune décision envoyée.")
            return last_id

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
        help="Boucle de polling continue (toutes les 60s) + commandes + chat Hermes.",
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
        "Configuration OK — le bot est opérationnel.\n"
        "Commandes : /status /last /pause /resume /help\n"
        "💬 Texte libre = parle à Hermes !"
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
        logger.info(
            "Mode WATCH — polling toutes les %d secondes + commandes + chat Hermes.",
            POLL_INTERVAL_S,
        )
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
