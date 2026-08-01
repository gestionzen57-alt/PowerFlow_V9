#!/usr/bin/env python
"""v9_rotate_telegram_tokens.py — Script de rotation des tokens Telegram (Action A1).

Motion CEO 01/08/2026 #43 — Action A1 (rotation tokens BotFather en attente
depuis 19/07/2026). L'action CEO sur BotFather n'est PAS automatisable
(le CEO doit creer les nouveaux tokens via @BotFather). Ce script est donc
le pivot technique qui prend les nouveaux tokens en argument et les propage
dans les differents endroits ou ils sont stockes.

Doctrine : R2 additif (0 modif code applicatif), R6 defensif (verification
connexion bot avant commit final), R7 tests unitaires (mock reseau), R8
backup MD5 des fichiers touches avant rotation.

Usage :
    # Mode interactif (CEO saisit les tokens) :
    python scripts/v9_rotate_telegram_tokens.py --interactive

    # Mode arguments (CI ou secret manager) :
    python scripts/v9_rotate_telegram_tokens.py \\
        --hiphop-token "NEW_HIPHOP_TOKEN" \\
        --ipspx-token "NEW_IPSPX_TOKEN" \\
        --bot-name-hiphop "NewHiphop_bot" \\
        --bot-name-ipspx "NewIpspx_bot" \\
        --chat-id "1401055223" \\
        --apply

    # Mode dry-run (verifier sans ecrire) :
    python scripts/v9_rotate_telegram_tokens.py --hiphop-token "..." --ipspx-token "..." --dry-run

    # Mode validation connexion uniquement (apres rotation manuelle) :
    python scripts/v9_rotate_telegram_tokens.py --validate-only

Fichiers touches :
    config/telegram.json  (bot Ipspx principal)
    .env                  (TELEGRAM_BOT_TOKEN Hiphopvps + TELEGRAM_BOT_TOKEN_IPSPX)
    (futur: autres si ajoute)

Sortie :
    backups/token_rotation_YYYYMMDD_HHMMSS/
    - telegram.json.bak      (avant rotation)
    - .env.bak               (avant rotation)
    - telegram.json          (apres rotation, si --apply)
    - .env                   (apres rotation, si --apply)
    - validation.json        (resultat getMe pour chaque bot)
    - rotation.log           (log human-readable)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent.parent
CONFIG_TELEGRAM = ROOT / "config" / "telegram.json"
ENV_FILE = ROOT / ".env"

log = logging.getLogger("v9.rotate_telegram_tokens")

# Token format BotFather : <bot_id>:<base64_chars>
# bot_id = chiffres, suivi de :, suivi de ~35 chars base64-url (A-Z, a-z, 0-9, -, _)
TOKEN_PATTERN = re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{35,45}$")

# Clefs .env impliquees
ENV_KEYS = {
    "hiphop": "TELEGRAM_BOT_TOKEN",
    "ipspx": "TELEGRAM_BOT_TOKEN_IPSPX",
    "hiphop_name": "TELEGRAM_BOT_NAME",
    "chat_id": "TELEGRAM_CHAT_ID",
}

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    """ISO 8601 UTC timestamp, seconde precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_fs() -> str:
    """Filesystem-safe UTC timestamp pour les repertoires de backup."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _md5(path: Path) -> str:
    """MD5 d'un fichier (utilise pour backup R8)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_token_format(token: str, label: str) -> bool:
    """Valide le format d'un token BotFather (sans appel reseau)."""
    if not TOKEN_PATTERN.match(token):
        log.error("%s: format invalide (attendu: <bot_id>:<35-45 chars>)", label)
        return False
    return True


def _call_telegram_getme(token: str, timeout: float = 10.0) -> dict:
    """Appelle /getMe sur l'API Telegram. R6 : URLError retourne dict erreur."""
    url = TELEGRAM_API.format(token=token, method="getMe")
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as e:
        return {"ok": False, "error_code": e.code, "description": str(e)}
    except URLError as e:
        return {"ok": False, "error_code": -1, "description": f"URLError: {e.reason}"}
    except (TimeoutError, json.JSONDecodeError) as e:
        return {"ok": False, "error_code": -2, "description": f"Parse: {e}"}


# ---------------------------------------------------------------------------
# Lecture / ecriture
# ---------------------------------------------------------------------------

def read_config_telegram() -> dict:
    """Lit config/telegram.json. R6 : retourne {} si absent ou corrompu."""
    if not CONFIG_TELEGRAM.exists():
        log.warning("config/telegram.json absent")
        return {}
    try:
        return json.loads(CONFIG_TELEGRAM.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("config/telegram.json illisible: %s", exc)
        return {}


def read_env() -> dict[str, str]:
    """Lit .env en preservant l'ordre des lignes. Retourne {key: value}."""
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        log.warning(".env absent")
        return env
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def write_env(env: dict[str, str], header_comment: str | None = None) -> None:
    """Ecrit .env a partir du dict (ordre preserve)."""
    lines = []
    if header_comment:
        lines.append(f"# {header_comment}")
        lines.append(f"# Rotation le {_now_utc()}")
        lines.append("")
    for k, v in env.items():
        lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_config_telegram(cfg: dict) -> None:
    """Ecrit config/telegram.json avec 4-space indent + metadata rotation."""
    cfg["last_rotated_at"] = _now_utc()
    CONFIG_TELEGRAM.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Backup R8
# ---------------------------------------------------------------------------

def backup_files(backup_dir: Path) -> dict[str, str]:
    """Backup MD5+copie des fichiers qui vont etre modifies. R8 strict."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    md5s: dict[str, str] = {}
    for label, path in [("telegram.json", CONFIG_TELEGRAM), (".env", ENV_FILE)]:
        if not path.exists():
            log.warning("backup: %s absent (skip)", path)
            continue
        bak = backup_dir / f"{label}.bak"
        shutil.copy2(path, bak)
        digest = _md5(path)
        md5s[label] = digest
        (backup_dir / f"{label}.bak.md5").write_text(digest + "\n", encoding="utf-8")
        log.info("backup: %s -> %s (md5=%s)", path.name, bak.name, digest)
    return md5s


# ---------------------------------------------------------------------------
# Validation connexion
# ---------------------------------------------------------------------------

def validate_token_connection(token: str, label: str) -> dict:
    """Appelle getMe et retourne le resultat. R6 : pas de raise."""
    log.info("validation: %s (token=***%s)", label, token[-8:])
    res = _call_telegram_getme(token)
    if res.get("ok"):
        username = (res.get("result") or {}).get("username", "unknown")
        log.info("  -> OK bot=@%s", username)
    else:
        log.error("  -> KO: %s", res.get("description", res))
    return res


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Rotation des tokens Telegram (Action A1, motion CEO 01/08/2026)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--hiphop-token", help="Nouveau token bot Hiphopvps")
    p.add_argument("--ipspx-token", help="Nouveau token bot Ipspx (config/telegram.json)")
    p.add_argument("--bot-name-hiphop", help="Nouveau nom bot Hiphopvps (defaut: TELEGRAM_BOT_NAME existant)")
    p.add_argument("--bot-name-ipspx", help="Nouveau nom bot Ipspx (defaut: bot_name existant dans config)")
    p.add_argument("--chat-id", help="Nouveau chat_id (defaut: existant)")
    p.add_argument("--apply", action="store_true",
                   help="Applique reellement la rotation (defaut: dry-run)")
    p.add_argument("--dry-run", action="store_true",
                   help="Affiche ce qui serait fait sans rien modifier")
    p.add_argument("--validate-only", action="store_true",
                   help="Valide uniquement les tokens actuels (post-rotation manuelle)")
    p.add_argument("--interactive", action="store_true",
                   help="Saisie interactive des tokens (cache la saisie)")
    p.add_argument("--no-validate", action="store_true",
                   help="Skip l'appel getMe (utile en CI offline)")
    p.add_argument("-v", "--verbose", action="store_true")

    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.interactive:
        import getpass
        args.hiphop_token = getpass.getpass("Nouveau token Hiphopvps: ")
        args.ipspx_token = getpass.getpass("Nouveau token Ipspx: ")

    dry_run = args.dry_run or not args.apply

    # --- validate-only : verifie les tokens actuels ---
    if args.validate_only:
        cfg = read_config_telegram()
        env = read_env()
        results = {}
        if cfg.get("BOT_TOKEN"):
            results["ipspx"] = validate_token_connection(cfg["BOT_TOKEN"], "config/telegram.json")
        if env.get(ENV_KEYS["hiphop"]):
            results["hiphop"] = validate_token_connection(env[ENV_KEYS["hiphop"]], ".env Hiphopvps")
        if env.get(ENV_KEYS["ipspx"]):
            results["ipspx_env"] = validate_token_connection(env[ENV_KEYS["ipspx"]], ".env Ipspx duplique")
        ok_all = all(r.get("ok") for r in results.values()) if results else False
        return 0 if ok_all else 4

    # --- rotation ---
    if not args.hiphop_token and not args.ipspx_token:
        log.error("Aucun token fourni. Utiliser --hiphop-token, --ipspx-token ou --interactive.")
        return 2

    if args.hiphop_token and not _validate_token_format(args.hiphop_token, "hiphop"):
        return 2
    if args.ipspx_token and not _validate_token_format(args.ipspx_token, "ipspx"):
        return 2

    # Lecture etat actuel
    cfg = read_config_telegram()
    env = read_env()
    log.info("etat actuel: config.bot_name=%s env.hiphop_name=%s",
             cfg.get("bot_name"), env.get(ENV_KEYS["hiphop_name"]))

    # Backup R8
    backup_dir = ROOT / "backups" / f"token_rotation_{_now_fs()}"
    md5s = backup_files(backup_dir)
    log.info("backup: %s", backup_dir)

    # Validation pre-rotation des nouveaux tokens (sauf si skip)
    validations = {}
    if not args.no_validate:
        if args.hiphop_token:
            validations["hiphop_new"] = validate_token_connection(args.hiphop_token, "Hiphopvps (NOUVEAU)")
        if args.ipspx_token:
            validations["ipspx_new"] = validate_token_connection(args.ipspx_token, "Ipspx (NOUVEAU)")
        if not all(v.get("ok") for v in validations.values()):
            log.error("Validation NOUVEAUX tokens a echoue. Abandon (backup conserve dans %s).", backup_dir)
            return 4

    # Application
    changes: list[str] = []
    if args.ipspx_token:
        old = cfg.get("BOT_TOKEN", "")
        cfg["BOT_TOKEN"] = args.ipspx_token
        if args.bot_name_ipspx:
            cfg["bot_name"] = args.bot_name_ipspx
        # Aussi mettre a jour le token duplique dans .env
        env[ENV_KEYS["ipspx"]] = args.ipspx_token
        changes.append(f"config/telegram.json BOT_TOKEN {old[-8:] if old else 'N/A'} -> {args.ipspx_token[-8:]}")
        changes.append(f".env {ENV_KEYS['ipspx']} = {args.ipspx_token[-8:]}")

    if args.hiphop_token:
        old = env.get(ENV_KEYS["hiphop"], "")
        env[ENV_KEYS["hiphop"]] = args.hiphop_token
        if args.bot_name_hiphop:
            env[ENV_KEYS["hiphop_name"]] = args.bot_name_hiphop
        changes.append(f".env {ENV_KEYS['hiphop']} {old[-8:] if old else 'N/A'} -> {args.hiphop_token[-8:]}")

    if args.chat_id:
        old = env.get(ENV_KEYS["chat_id"], cfg.get("CHAT_ID", ""))
        env[ENV_KEYS["chat_id"]] = args.chat_id
        cfg["CHAT_ID"] = args.chat_id
        changes.append(f"chat_id {old} -> {args.chat_id}")

    if not changes:
        log.error("Aucun changement a appliquer.")
        return 2

    log.info("Changements prevus:")
    for c in changes:
        log.info("  - %s", c)

    if dry_run:
        log.info("DRY-RUN : aucun fichier modifie. Relancer avec --apply pour appliquer.")
        log.info("Backup conserve dans %s", backup_dir)
        return 0

    # Ecriture
    write_config_telegram(cfg)
    write_env(env, header_comment=f"Rotation tokens Telegram - {_now_utc()}")
    log.info("Ecriture OK : config/telegram.json + .env")

    # Validation post-rotation (sanity check)
    if not args.no_validate:
        if args.ipspx_token:
            res = validate_token_connection(cfg["BOT_TOKEN"], "config/telegram.json (POST)")
            if not res.get("ok"):
                log.error("POST validation config/telegram.json a echoue. Restaurer depuis backup %s.", backup_dir)
                return 4
        if args.hiphop_token:
            res = validate_token_connection(env[ENV_KEYS["hiphop"]], ".env Hiphopvps (POST)")
            if not res.get("ok"):
                log.error("POST validation .env Hiphopvps a echoue. Restaurer depuis backup %s.", backup_dir)
                return 4

    # Ecriture rapport de rotation
    report = {
        "rotation_at": _now_utc(),
        "applied": not dry_run,
        "backup_dir": str(backup_dir.relative_to(ROOT)),
        "md5_pre": md5s,
        "changes": changes,
        "validations": validations,
    }
    (backup_dir / "rotation_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log.info("Rapport ecrit dans %s/rotation_report.json", backup_dir.name)
    log.info("=== ROTATION TERMINEE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
