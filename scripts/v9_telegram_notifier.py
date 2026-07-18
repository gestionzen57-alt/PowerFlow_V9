#!/usr/bin/env python3
"""v9_telegram_notifier.py — Alertes Telegram live sur décisions GBPUSD.

Polling toutes les 60s sur la table `decisions` de v9_forces.db.
Filtre : symbol='GBPUSD', confiance > 80, direction != 'neutre'.
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
import ssl
import subprocess
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
LOCK_PATH = ROOT_DIR / "logs" / ".telegram_daemon.lock"  # Anti-multi-instance (CEO 2026-07-11)

# ── Constantes ─────────────────────────────────────────────
POLL_INTERVAL_S = 2  # Polling rapide pour réponse quasi-instantanée (~2s latence max)
POLL_HEARTBEAT_S = 30  # Log "alive" toutes les 30s pour confirmer que le daemon tourne


# ── SSL context global (fix Windows : certifi CA bundle) ──
def _make_ssl_context() -> ssl.SSLContext:
    """Construit un contexte SSL qui charge le CA bundle certifi.

    Sans ça, Python utilise le bundle système Windows (VeriSign/GlobalSign anciens)
    qui ne reconnaît pas les CA modernes de api.telegram.org → CERTIFICATE_VERIFY_FAILED.
    """
    ctx = ssl.create_default_context()
    # Priorité 1 : SSL_CERT_FILE env var (si le wrapper .bat la pose)
    env_cert = os.environ.get("SSL_CERT_FILE", "").strip()
    if env_cert and Path(env_cert).exists():
        try:
            ctx.load_verify_locations(env_cert)
            return ctx
        except Exception:
            pass
    # Priorité 2 : CA bundle certifi du venv Hermes (chemin Windows par défaut)
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


_SSL_CTX = _make_ssl_context()
CONFIANCE_MIN = 80  # Mode silencieux (CEO 2026-07-13) : 65→80 pour réduire le spam
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
    """Envoie un message au LLM (OpenRouter) avec mémoire de conversation.

    Fix 2026-07-18 : OpenRouter remplace Ollama Cloud (405 Method Not Allowed).
    Si LLM non configuré ou erreur → fallback redirige vers les commandes.
    """
    import time as _time
    t0 = _time.time()
    cfg = _read_llm_config()
    if not cfg["key"]:
        logger.warning("LLM: no key found, using fallback redirige")
        return _fallback_redirige(user_text)

    logger.info("LLM call: text=%r (len=%d)", user_text[:80], len(user_text))

    # Construire les messages avec historique
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es Hermes, l'opérateur IA unique de PowerFlow V9 — un système cognitif de "
                "lecture forex (GBPUSD) construit sur 9 couches déterministes. Tu parles à Søn, "
                "le CEO, en français, de façon concise (max 1500 chars) et directe. "
                "Mode Y : exécution proactive, tu proposes des actions concrètes (commande bash, "
                "check pipeline, lecture STATE.md) et attends validation avant exécution. "
                "Doctrine 30 règles (cf. R28 tu es l'opérateur git unique, R18 zéro LLM dans la "
                "boucle critique, R22 une session = un périmètre = une livraison, R30 apprentissage "
                "WIN/LOSS progressif seuils 5/20/50/200). "
                "État courant (2026-07-15) : pipeline live ACTIF port 31685, DB v9_forces.db "
                "~1.4 GB, 64K+ décisions (DYNAMIC 88.6% WR), 53 principes YAML (27 ACTIVE + "
                "26 SHADOW), 1330 tests verts, branche feat/v9-foundation-clean HEAD b2a6842. "
                "Phase 14 livrée : learning_offset_applier + kill switch "
                "V9_LEARNING_OFFSET_ENABLED (OFF par défaut). Kill switches : TRADER_MINI=1, "
                "AUTO_CALIBRATOR=1, SHADOW=1, WIRE=1, EXECUTION=0 (gelé). "
                "Tu peux suggérer : /status (pipeline live), /last (dernière décision), "
                "/wr (audit WR), /principles (hit rate), /signals (5 derniers), /paper "
                "(paper trades), /proposals (meta-agent), /help (16 commandes). "
                "Ne jamais trader. Pour les questions de marché, demander à Søn de consulter "
                "STATE.md + DOCTRINE.md ou d'ouvrir le dashboard Tailscale."
            ),
        }
    ]
    for turn in conversation[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_text})

    payload = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": 600,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://powerflow.v9",
            "X-Title": "PowerFlow V9 Telegram",
        },
        method="POST",
    )
    try:
        ctx = _make_ssl_context()
        with urllib.request.urlopen(req, timeout=HERMES_TIMEOUT_S, context=ctx) as resp:
            data = json.loads(resp.read())
            elapsed = _time.time() - t0
            logger.info("LLM response in %.1fs (len=%d chars)", elapsed, len(data["choices"][0]["message"]["content"]))
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        code = e.code
        body = e.read().decode("utf-8", errors="replace")[:200]
        elapsed = _time.time() - t0
        logger.error("LLM HTTPError %d in %.1fs : %s", code, elapsed, body)
        if code in (401, 403, 404, 405):
            return (
                "⚠️ LLM OpenRouter erreur " + str(code) + " (clé/modèle/quota).\n\n"
                + _fallback_redirige(user_text)
            )
        return (
            "⚠️ LLM erreur " + str(code) + ".\n\n" + _fallback_redirige(user_text)
        )
    except Exception as e:
        elapsed = _time.time() - t0
        logger.error("LLM exception in %.1fs : %s", elapsed, e)
        return (
            f"⚠️ LLM indisponible ({type(e).__name__}).\n\n"
            + _fallback_redirige(user_text)
        )


def _fallback_redirige(user_text: str) -> str:
    """Mode dégradé : redirige le texte libre vers la commande Telegram la plus pertinente.

    Si un mot-clé correspond, exécute DIRECTEMENT la commande et retourne son résultat.
    Si plusieurs mots-clés correspondent, exécute la première commande détectée.
    Pas de LLM requis. Toujours disponible.
    """
    import sqlite3 as _sql
    text_lower = user_text.lower()

    # Mapping mots-clés → commande (premier match = commande exécutée)
    keyword_map = [
        ("état", "/status"), ("pipeline", "/status"), ("port", "/status"),
        ("snapshot", "/status"), ("online", "/status"), ("en ligne", "/status"),
        ("dernier signal", "/last"), ("signal", "/signals"),
        ("wr", "/wr"), ("win", "/wr"), ("loss", "/wr"), ("biais", "/wr"),
        ("principe", "/principles"), ("hit rate", "/principles"),
        ("scène", "/scenes"), ("régime", "/regime"), ("regime", "/regime"),
        ("session", "/regime"),
        ("paper", "/paper"), ("résolu", "/resolve"), ("proposition", "/proposals"),
        ("meta", "/proposals"), ("calibr", "/calibrate"),
        ("replay", "/replay"), ("arbiter", "/arbiter"),
        ("marché", "/wr"), ("market", "/wr"),
        ("force", "/regime"),
        ("volatil", "/wr"),
        ("news", "/regime"), ("nfp", "/regime"),
        ("stop", "/pause"), ("aide", "/help"), ("help", "/help"),
    ]

    # Trouver la première commande correspondante
    detected_cmd = None
    for kw, cmd in keyword_map:
        if kw in text_lower:
            detected_cmd = cmd
            break

    # Cas spéciaux : salutations / questions simples
    if not detected_cmd:
        if any(w in text_lower for w in ["salut", "bonjour", "coucou", "hello", "hey", "çava", "ça va"]):
            return (
                "👋 Salut Søn ! Hermes en ligne.\n"
                "Pipeline live actif, 16 commandes dispo.\n"
                "Tape /help pour la liste, ou pose ta question directement."
            )
        if "?" in user_text:
            # Question sans mot-clé → suggestions
            detected_cmd = "/status"

    if detected_cmd:
        # Exécuter la commande directement
        try:
            conn = _sql.connect(str(DB_PATH), timeout=5.0)
            conn.row_factory = _sql.Row
            cursor = conn.cursor()
            result = _handle_command(detected_cmd, {}, cursor, None)
            conn.close()
            if result:
                return f"💬 \"{user_text[:60]}\"\n→ {detected_cmd}\n\n{result}"
            return f"💬 \"{user_text[:60]}\"\n→ {detected_cmd}\n\n(résultat vide)"
        except Exception as e:
            logger.error("Fallback execute error for %s: %s", detected_cmd, e)
            return f"💬 \"{user_text[:60]}\"\n→ {detected_cmd} (erreur: {e})"

    # Aucun match
    return (
        f"💬 \"{user_text[:80]}\"\n\n"
        "Pas de mot-clé reconnu. Tape /help pour la liste des commandes,\n"
        "ou utilise directement /status /wr /signals /regime etc."
    )


def _read_llm_config() -> dict[str, str]:
    """Lit la config LLM (clé + modèle) depuis .env Hermes / projet.

    Fournisseur : OpenRouter (fix 2026-07-18 — Ollama Cloud renvoyait 405).
    Priorité variables (RESPECTÉE) : OPENROUTER_API_KEY > V9_LLM_API_KEY >
    LLM_API_KEY > OLLAMA_API_KEY. Modèle : V9_LLM_MODEL sinon défaut
    tencent/hy3:free.

    Retourne {"key": str, "model": str}. key vide => LLM non configuré.
    """
    env_paths = [
        Path.home() / "AppData" / "Local" / "hermes" / ".env",
        Path.home() / ".hermes" / ".env",
        Path.home() / ".hermes" / "profiles" / "powerflow" / ".env",
        Path(".env"),
    ]
    key_names = (
        "OPENROUTER_API_KEY",
        "V9_LLM_API_KEY",
        "LLM_API_KEY",
        "OLLAMA_API_KEY",
    )
    # 1) Charger toutes les vars utiles dans un dict (1er fichier trouvé gagne).
    env_vars: dict[str, str] = {}
    model = "tencent/hy3:free"
    for env_path in env_paths:
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("\"'")
                if k == "V9_LLM_MODEL" and v:
                    model = v
                if k in key_names and k not in env_vars and v and not v.startswith("#"):
                    env_vars[k] = v
        except Exception:
            pass
        if env_vars:
            break
    # 2) Retourner selon l'ordre de priorité EXPLICITE.
    found_key = ""
    for name in key_names:
        if env_vars.get(name):
            found_key = env_vars[name]
            break
    return {"key": found_key, "model": model}


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
def _strip_markdown(text: str) -> str:
    """Retire le markup Markdown simple (**...**) pour envoi en texte brut."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text)


def send_telegram(
    text: str,
    config: dict[str, str],
    timeout: int = 15,
    parse_mode: str | None = None,
) -> bool:
    """Envoie un message via l'API Telegram. Retourne True si succès.

    `timeout` (défaut 15s, CLI/daemon) — paramétrable pour les appelants
    best-effort qui exigent un délai court (ex: hook live decision_logger,
    Brief O3 — 5s, jamais bloquant pour le pipeline).

    `parse_mode` (défaut None = texte brut) : on n'utilise PAS le parse_mode
    HTML/Markdown de Telegram — les messages de commandes mélangent du Markdown
    et des emojis que le parseur HTML rejette en 400 Bad Request. Envoyer en
    texte brut élimine toute erreur de formatage (CEO fix 2026-07-18)."""
    url = TELEGRAM_API.format(token=config["token"])
    payload: dict[str, str] = {
        "chat_id": config["chat_id"],
        "text": _strip_markdown(text) if parse_mode is None else text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("ok"):
                logger.info("Message Telegram envoyé avec succès.")
                return True
            else:
                logger.warning("Telegram API a retourné ok=false : %s", body)
                return False
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logger.error("Telegram HTTPError %s : %s", e.code, detail)
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

    Version debug 2026-07-11 (writing-plans fix) :
    - Logs explicites de chaque update reçu (update_id, text, chat_id).
    - _write_offset TOUJOURS appelé (au lieu de conditionnel) — la condition
      `if offset > _read_offset()` ratait des écritures quand l'offset
      en mémoire égalait l'offset persisté (= boucle infinie sans
      persistance).
    """
    offset = _read_offset()
    url = f"{GET_UPDATES_API.format(token=config['token'])}?offset={offset}&timeout=5"
    logger.info("getUpdates offset=%d", offset)
    try:
        with urllib.request.urlopen(url, timeout=10, context=_SSL_CTX) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        logger.error("getUpdates URLError : %s", e)
        return []
    except json.JSONDecodeError as e:
        logger.error("getUpdates JSONDecodeError : %s", e)
        return []

    if not body.get("ok"):
        logger.error("getUpdates not ok : %s", body)
        return []

    raw_count = len(body.get("result", []))
    logger.info("getUpdates returned %d raw updates", raw_count)

    messages = []
    for update in body.get("result", []):
        update_id = update.get("update_id", 0)
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        logger.info(
            "update_id=%d text=%r chat_id=%s (target=%s)",
            update_id, text[:50], chat_id, config.get("chat_id", ""),
        )
        if text and chat_id:
            messages.append({
                "text": text,
                "chat_id": chat_id,
                "update_id": update_id,
            })
        # Toujours avancer l'offset (update_id + 1 = marquer comme lu).
        # ATTENTION : utiliser >= et pas > (CEO 2026-07-11 fix boucle /replay) :
        # si update_id == offset, on doit quand même incrémenter pour ne pas
        # re-recevoir le même message au prochain cycle.
        if update_id >= offset:
            offset = update_id + 1

    # TOUJOURS persister l'offset, même s'il n'a pas changé.
    # 1 write de 20 bytes par cycle, négligeable.
    _write_offset(offset)
    logger.debug("offset persisted: %d", offset)

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
    """Traite une commande Telegram. Retourne la réponse à envoyer, ou None si ignorée.

    Commandes disponibles (étendues Phase 13 CEO 2026-07-10) :
      /status, /last, /pause, /resume, /help — originales.
      /principles, /signals, /scenes, /regime, /resolve — lectures DB V9.
      /calibrate, /replay, /arbiter, /meta, /emit, /tests — outils Phase 13.
      /ask <question> — LLM fallback Ollama Cloud (si dispo).
    """
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

    # ── Lectures DB étendues ──────────────────────────────
    if cmd_lower == "/principles":
        return _build_principles_response(cursor)
    if cmd_lower == "/signals":
        return _build_signals_response(cursor)
    if cmd_lower == "/scenes":
        return _build_scenes_response(cursor)
    if cmd_lower == "/regime":
        return _build_regime_response(cursor)
    if cmd_lower == "/resolve":
        return _build_resolve_response(cursor)
    if cmd_lower == "/wr":
        return _build_wr_response(cursor)
    if cmd_lower == "/paper":
        return _build_paper_response(cursor)
    if cmd_lower == "/proposals":
        return _build_proposals_response()

    # ── Outils Phase 13 (sous-processus, lecture stdout) ─
    if cmd_lower == "/calibrate":
        return _run_script_capture("v9_calibration.py --stats", max_lines=30)
    if cmd_lower == "/replay":
        return _run_script_capture(
            "v9_replay_param.py --limit 500 --timeframes M5 M15", max_lines=20
        )
    if cmd_lower == "/arbiter":
        return _run_script_capture("v9_recalibrate_arbiter.py", max_lines=30)
    if cmd_lower == "/meta":
        return _run_script_capture("v9_meta_agent.py --scan --hours 24", max_lines=15)
    if cmd_lower == "/emit":
        return _run_script_capture(
            "v9_meta_agent_emit.py --once --lookback-hours 24", max_lines=10
        )
    if cmd_lower == "/tests":
        return _run_script_capture(
            "v9_resolve_decision_auto.py --dry-run --limit 5", max_lines=8
        )

    # ── Help enrichi ─────────────────────────────────────
    if cmd_lower == "/help":
        return _build_help()

    # ── LLM fallback : /ask <question> ───────────────────
    if cmd_lower.startswith("/ask "):
        question = cmd[5:].strip()
        if not question:
            return "❓ /ask nécessite une question. Ex: /ask combien de paper trades ouverts"
        return _ask_llm(question)

    # Commande inconnue
    return (
        "❓ Commande inconnue. Tape /help pour la liste complète.\n"
        "💬 Texte libre — Hermes te répond (LLM Ollama Cloud si dispo)."
    )


# ── Builders commandes étendues ────────────────────────────────
def _build_principles_response(cursor: sqlite3.Cursor) -> str:
    """Hit rate des 25 principes ACTIVE sur les 24h."""
    cursor.execute("""
        SELECT pe.principle_id,
               COUNT(*) AS n_eval,
               SUM(CASE WHEN pe.triggered = 1 THEN 1 ELSE 0 END) AS n_trig,
               ROUND(AVG(CASE WHEN pe.triggered = 1 THEN pe.confidence END), 1) AS avg_conf
        FROM principle_evaluations pe
        WHERE pe.timestamp > datetime('now', '-24 hours', 'utc')
        GROUP BY pe.principle_id
        ORDER BY n_trig DESC
        LIMIT 15
    """)
    rows = cursor.fetchall()
    if not rows:
        return "📊 Aucun principe évalué sur les dernières 24h."
    lines = ["📊 **Top 15 principes (24h)**\n"]
    lines.append(f"{'Principe':<38} {'Éval':>5} {'Trig':>5} {'Conf':>6}")
    lines.append("-" * 60)
    for r in rows:
        pid, n_eval, n_trig, avg_conf = r[0], r[1], r[2] or 0, r[3] or 0
        lines.append(f"{pid:<38} {n_eval:>5} {n_trig:>5} {avg_conf:>6.1f}")
    return "\n".join(lines)


def _build_signals_response(cursor: sqlite3.Cursor) -> str:
    """5 derniers signaux directionnels."""
    cursor.execute("""
        SELECT timestamp, direction, confiance, action
        FROM decisions
        WHERE direction IS NOT NULL AND direction != 'neutre'
        ORDER BY timestamp DESC LIMIT 5
    """)
    rows = cursor.fetchall()
    if not rows:
        return "📡 Aucun signal directionnel récent."
    lines = ["📡 **5 derniers signaux**\n"]
    for r in rows:
        ts = _format_cest_timestamp(r[0])
        emoji = "🟢" if r[1] == "haussiere" else "🔴"
        lines.append(f"{emoji} {ts}  {r[1]:<10} {r[2]:>3}%  {r[3]}")
    return "\n".join(lines)


def _build_scenes_response(cursor: sqlite3.Cursor) -> str:
    """Compte scènes par TF sur 1h."""
    cursor.execute("""
        SELECT timeframe, COUNT(*) AS n
        FROM scenes
        WHERE timestamp > datetime('now', '-1 hour', 'utc')
        GROUP BY timeframe
        ORDER BY n DESC
    """)
    rows = cursor.fetchall()
    if not rows:
        return "🎬 Aucune scène sur la dernière heure."
    lines = ["🎬 **Scènes / 1h par TF**\n"]
    for r in rows:
        lines.append(f"  {r[0]:<5}: {r[1]} scènes")
    return "\n".join(lines)


def _build_regime_response(cursor: sqlite3.Cursor) -> str:
    """Régime actuel par TF + timestamp."""
    cursor.execute("""
        SELECT timeframe, regime_type, timestamp
        FROM regime_snapshots
        WHERE symbol = ? AND stale = 0
        ORDER BY timeframe, timestamp DESC
    """, (SYMBOL,))
    rows = cursor.fetchall()
    if not rows:
        return "🌀 Aucun régime détecté."
    seen_tf = set()
    lines = ["🌀 **Régime actuel par TF**\n"]
    for r in rows:
        if r[0] in seen_tf:
            continue
        seen_tf.add(r[0])
        ts = _format_cest_timestamp(r[2])
        lines.append(f"  {r[0]:<5}: {r[1]} ({ts})")
    return "\n".join(lines)


def _build_resolve_response(cursor: sqlite3.Cursor) -> str:
    """Stats WIN/LOSS résolues."""
    cursor.execute("""
        SELECT
            SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN is_win IS NULL THEN 1 ELSE 0 END) AS open,
            COUNT(*) AS total
        FROM decisions
        WHERE action = 'preparer_entree'
    """)
    r = cursor.fetchone()
    if not r or r[3] == 0:
        return "🎯 Aucune décision preparer_entree."
    wins, losses, open_dec, total = r
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    return (
        f"🎯 **WIN/LOSS resolver**\n"
        f"  Wins        : {wins}\n"
        f"  Losses      : {losses}\n"
        f"  Open        : {open_dec}\n"
        f"  Total       : {total}\n"
        f"  WR résolu   : {wr:.2f}%\n"
        f"  (biais structurel documenté, voir /arbiter)"
    )


def _build_wr_response(cursor: sqlite3.Cursor) -> str:
    """Audit WR rapide + biais structurel."""
    cursor.execute("""
        SELECT resolution_pips FROM decisions
        WHERE is_win IS NOT NULL AND resolution_pips IS NOT NULL
    """)
    pips = [r[0] for r in cursor.fetchall()]
    if not pips:
        return "📊 Aucun WIN/LOSS résolu."
    n_pos = sum(1 for p in pips if p > 0)
    n_neg = sum(1 for p in pips if p <= 0)
    pips_pos = [p for p in pips if p > 0]
    pips_neg = [p for p in pips if p <= 0]
    mean_all = sum(pips) / len(pips)
    mean_pos = sum(pips_pos) / len(pips_pos) if pips_pos else 0
    mean_neg = sum(pips_neg) / len(pips_neg) if pips_neg else 0
    max_p = max(pips)
    return (
        f"📊 **WR audit (résolu: {len(pips)})**\n"
        f"  Wins         : {n_pos} ({n_pos/len(pips)*100:.1f}%)\n"
        f"  Losses       : {n_neg} ({n_neg/len(pips)*100:.1f}%)\n"
        f"  Mean all     : {mean_all:+.2f} pips\n"
        f"  Mean wins    : {mean_pos:+.2f} pips\n"
        f"  Mean losses  : {mean_neg:+.2f} pips\n"
        f"  Max          : {max_p:+.2f} pips\n"
        f"  ⚠ Biais : WR>95% sur range post-FOMC = artefact MFE>0 fenêtre 4h.\n"
        f"    Voir /paper pour audit RiskManager."
    )


def _build_paper_response(cursor: sqlite3.Cursor) -> str:
    """Paper trades ouverts + historique récent."""
    cursor.execute("""
        SELECT trade_id, direction, confiance, opened_at, is_win
        FROM paper_trades
        ORDER BY opened_at DESC LIMIT 5
    """)
    rows = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM paper_trades WHERE closed_at IS NULL")
    n_open = cursor.fetchone()[0]
    if not rows:
        return (
            f"📝 Paper trades : 0 ouvert, 0 historique (range post-FOMC, "
            f"gate conf 70). /resolve pour état WIN/LOSS global."
        )
    lines = [f"📝 **Paper trades** : {n_open} ouvert(s)\n"]
    for r in rows:
        ts = _format_cest_timestamp(r[3]) if r[3] else "?"
        status = "WIN" if r[4] == 1 else ("LOSS" if r[4] == 0 else "OPEN")
        lines.append(f"  {status:<6} {r[1]:<10} {r[2]:>3}% {ts}")
    return "\n".join(lines)


def _build_proposals_response() -> str:
    """Propositions meta-agent en attente (bus agent_bus)."""
    try:
        from core.v9.meta_agent import get_proposals
        props = get_proposals(limit=5, db_path=None)
        if not props:
            return "🧠 Aucune proposition meta-agent en attente."
        lines = [f"🧠 **Propositions meta-agent (top {len(props)})**\n"]
        for p in props:
            lines.append(f"  [{p.get('confidence', 0):.2f}] {p.get('action_type')} → {p.get('target')}")
            lines.append(f"      {p.get('rationale', '')[:100]}")
        return "\n".join(lines)
    except Exception as e:
        return f"🧠 Bus meta-agent injoignable : {e}"


def _run_script_capture(cmd: str, max_lines: int = 30) -> str:
    """Lance un script V9 en sous-processus et capture les N premières lignes."""
    try:
        # Ajoute scripts/ au début du path de la commande
        parts = cmd.split()
        if parts and not parts[0].startswith("scripts/"):
            parts[0] = f"scripts/{parts[0]}"
        result = subprocess.run(
            [sys.executable] + parts,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, cwd=str(ROOT_DIR),
        )
        out = (result.stdout or "").strip().splitlines()[:max_lines]
        if not out:
            return f"⏱ {cmd} : aucun output (exit={result.returncode})"
        header = f"⏱ {cmd} (exit={result.returncode})\n"
        return header + "\n".join(out)
    except subprocess.TimeoutExpired:
        return f"⏱ {cmd} : timeout 60s"
    except Exception as e:
        return f"❌ {cmd} : {e}"


def _ask_llm(question: str) -> str:
    """Question au LLM OpenRouter (fix 2026-07-18 : OpenRouter remplace Ollama).

    Réutilise _call_hermes (même provider, sans historique) si LLM configuré.
    Sinon, redirige vers les commandes V9.
    """
    cfg = _read_llm_config()
    if not cfg["key"]:
        return (
            "🤖 LLM non configuré (OPENROUTER_API_KEY / V9_LLM_API_KEY dans .env Hermes).\n"
            "   Pose ta question via les commandes :\n"
            "   /status /principles /signals /scenes /regime /resolve /wr /paper /proposals\n"
            "   ou demande /help pour la liste complète."
        )
    try:
        return _call_hermes(question, [])
    except Exception as e:
        return f"🤖 LLM erreur : {e}\n   Fallback : /status /principles /wr"


def _build_help() -> str:
    """Help enrichi Phase 13 — 16 commandes."""
    return (
        "📋 **V9 Telegram — 16 commandes**\n\n"
        "**Pipeline** :\n"
        "/status  — snapshot live (port, DB, dernier signal)\n"
        "/last    — dernier signal complet (contexte 3 principes)\n"
        "/signals — 5 derniers signaux directionnels\n"
        "/scenes  — compte scènes / 1h par TF\n"
        "/regime  — régime actuel par TF\n"
        "/principles — hit rate 15 top principes / 24h\n"
        "/wr      — audit WR + biais structurel\n"
        "/resolve — stats WIN/LOSS résolues\n"
        "/paper   — paper trades ouverts + récents\n"
        "/proposals — propositions meta-agent en attente\n\n"
        "**Outils Phase 13** :\n"
        "/calibrate — v9_calibration.py --stats\n"
        "/replay    — v9_replay_param.py baseline 500 snapshots\n"
        "/arbiter   — v9_recalibrate_arbiter.py (propositions R29)\n"
        "/meta      — v9_meta_agent.py --scan 24h\n"
        "/emit      — v9_meta_agent_emit.py --once 24h\n\n"
        "**Contrôle** :\n"
        "/pause    — suspendre les alertes automatiques\n"
        "/resume   — réactiver les alertes\n"
        "/ask <q>  — question LLM (OpenRouter, si configuré)\n"
        "/help     — cette aide\n\n"
        "💬 Texte libre — Hermes (LLM OpenRouter) te répond directement."
    )


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
                # Texte libre → conversation LLM (OpenRouter, fix 2026-07-18).
                # Repli automatique vers _fallback_redirige si LLM KO.
                logger.info("Texte libre → LLM : %s", text[:80])
                conversation = _load_conversation()
                try:
                    hermes_response = _call_hermes(text, conversation)
                except Exception as e:
                    logger.error("LLM call failed, fallback : %s", e)
                    hermes_response = _fallback_redirige(text)
                conversation.append({"role": "user", "content": text})
                conversation.append({"role": "assistant", "content": hermes_response})
                _save_conversation(conversation)
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
    parser.add_argument(
        "--send-help",
        action="store_true",
        help="Envoie le message /help (valide que l'envoi ne fait plus 400).",
    )
    parser.add_argument(
        "--send-text",
        metavar="TEXT",
        default="",
        help="Envoie un texte libre (teste le LLM OpenRouter).",
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

    if args.send_help:
        ok = send_telegram(_build_help(), config)
        print(("OK /help envoyé" if ok else "ÉCHEC envoi /help"))
        return

    if args.send_text:
        conversation = _load_conversation()
        try:
            reply = _call_hermes(args.send_text, conversation)
        except Exception as e:
            logger.error("LLM test failed : %s", e)
            reply = _fallback_redirige(args.send_text)
        print("Réponse LLM :\n" + reply)
        send_telegram(reply, config)
        return

    # ── Anti-multi-instance (lock file, CEO 2026-07-11) ─────────
    # Empêche 2 daemons Telegram de se battre pour le même token (= HTTP 409
    # Conflict sur getUpdates). Le 1er daemon crée le lock, les suivants
    # crashent immédiatement.
    if LOCK_PATH.exists():
        try:
            existing_pid = int(LOCK_PATH.read_text(encoding="utf-8").strip())
            existing_proc = __import__("subprocess").run(
                ["tasklist", "/FI", f"PID eq {existing_pid}"],
                capture_output=True, text=True, timeout=5,
            )
            if str(existing_pid) in existing_proc.stdout:
                logger.error(
                    "Daemon Telegram déjà actif (PID %d, lock=%s). "
                    "Refus de démarrer pour éviter HTTP 409.",
                    existing_pid, LOCK_PATH,
                )
                print(
                    f"❌ Daemon Telegram déjà actif (PID {existing_pid}).\n"
                    f"   Lock file : {LOCK_PATH}\n"
                    f"   Tue-le : powershell Stop-Process -Id {existing_pid}",
                    file=sys.stderr,
                )
                return 1
        except Exception:
            pass
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    logger.info("Lock file créé : %s (PID %d)", LOCK_PATH, os.getpid())

    last_id = _read_last_sent_id()
    logger.info(
        "Démarrage notificateur Telegram (symbole=%s, confiance_min=%d, last_id=%s)",
        SYMBOL, CONFIANCE_MIN, last_id or "(aucun)",
    )

    if args.once:
        _poll_once(config, last_id)
        LOCK_PATH.unlink(missing_ok=True)
        return

    if args.watch:
        logger.info(
            "Mode WATCH — polling toutes les %d secondes + commandes + chat Hermes.",
            POLL_INTERVAL_S,
        )
        last_heartbeat = time.monotonic()
        try:
            while True:
                try:
                    last_id = _poll_once(config, last_id)
                except KeyboardInterrupt:
                    logger.info("Arrêt demandé par l'opérateur.")
                    break
                except Exception:
                    logger.exception("Erreur inattendue dans la boucle de polling.")
                # Heartbeat interne : log toutes les POLL_HEARTBEAT_S pour confirmer la survie du daemon
                now = time.monotonic()
                if now - last_heartbeat >= POLL_HEARTBEAT_S:
                    logger.info("Daemon alive — last_id=%s — uptime=%.0fs", last_id or "(none)", now)
                    last_heartbeat = now
                time.sleep(POLL_INTERVAL_S)
        finally:
            LOCK_PATH.unlink(missing_ok=True)
            logger.info("Lock file supprimé (daemon arrêté).")
        return

    # Default : --once
    _poll_once(config, last_id)
    LOCK_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
