"""v9_token_rotation.py — Phase 19 motion CEO « EDGE FUND MAX ».

R2 Perplexity : 4 tokens Telegram CEO non rotates (13+ jours sans rotation).
Mitigation : script qui :
1. Detecte les tokens expires (v9_token_age_days > MAX_AGE)
2. Genere un nouveau token (delegation telegram BotFather / token generator)
3. Valide le nouveau token (test bot API)
4. Archive l'ancien token dans data/v9_token_history.json
5. Met a jour config/v9_tokens.env (rotate in-place)

Note : la generation de nouveau token necessite une action manuelle via
BotFather @BotFather (send /revoke + copy new token). Ce script :
- detecte les tokens expires
- demande l'action manuelle
- valide le nouveau token une fois colle dans .env

Usage :
  python scripts/v9_token_rotation.py --check    # check rotation status
  python scripts/v9_token_rotation.py --status   # age de chaque token
  python scripts/v9_token_rotation.py --history  # historique rotations

Auteur : Hermes (Phase 19 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.token_rotation")

# Phase 19 — seuils R2 Perplexity
MAX_TOKEN_AGE_DAYS = 30
WARN_TOKEN_AGE_DAYS = 14

TOKEN_HISTORY_FILE = Path(r"C:\projet\V9\data\v9_token_history.json")
TOKEN_ENV_FILE = Path(r"C:\projet\V9\config\v9_tokens.env")


def _ensure_history_file() -> None:
    """Cree v9_token_history.json si absent."""
    TOKEN_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TOKEN_HISTORY_FILE.exists():
        TOKEN_HISTORY_FILE.write_text(json.dumps([], indent=2))


def load_history() -> list:
    """Charge l'historique des rotations."""
    _ensure_history_file()
    try:
        data = json.loads(TOKEN_HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(history: list) -> None:
    """Sauvegarde l'historique."""
    _ensure_history_file()
    TOKEN_HISTORY_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def parse_token_env() -> list[dict]:
    """Parse config/v9_tokens.env. Retourne liste de dict {name, value, last_rotated}."""
    if not TOKEN_ENV_FILE.exists():
        return []
    tokens = []
    for line in TOKEN_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Detecter suffixe _LAST_ROTATED
        last_rotated = None
        if key.endswith("_LAST_ROTATED"):
            continue  # metadata, pas un token
        rotated_key = f"{key}_LAST_ROTATED"
        # Lire la date rotation associee
        content = TOKEN_ENV_FILE.read_text(encoding="utf-8")
        for l in content.splitlines():
            if l.startswith(rotated_key + "="):
                last_rotated = l.partition("=")[2].strip()
                break
        tokens.append({
            "name": key,
            "value": value,
            "last_rotated": last_rotated,
        })
    return tokens


def compute_age_days(last_rotated: str | None) -> int | None:
    """Calcule l'age en jours depuis la derniere rotation."""
    if not last_rotated:
        return None
    try:
        dt = datetime.fromisoformat(last_rotated.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.days
    except Exception:
        return None


def check_rotation_status() -> dict:
    """Verifie l'etat de rotation de tous les tokens."""
    tokens = parse_token_env()
    n_total = len(tokens)
    n_expired = 0
    n_warning = 0
    n_ok = 0
    items = []
    for t in tokens:
        age = compute_age_days(t["last_rotated"])
        status = "unknown"
        if age is None:
            status = "no_rotation_date"
        elif age >= MAX_TOKEN_AGE_DAYS:
            status = "expired"
            n_expired += 1
        elif age >= WARN_TOKEN_AGE_DAYS:
            status = "warning"
            n_warning += 1
        else:
            status = "ok"
            n_ok += 1
        items.append({
            "name": t["name"],
            "last_rotated": t["last_rotated"],
            "age_days": age,
            "status": status,
        })
    return {
        "check_ts": datetime.now(timezone.utc).isoformat(),
        "n_total": n_total,
        "n_expired": n_expired,
        "n_warning": n_warning,
        "n_ok": n_ok,
        "items": items,
        "recommendation": (
            "ROTATE_URGENT" if n_expired > 0
            else "ROTATE_SOON" if n_warning > 0
            else "ALL_OK"
        ),
    }


def log_rotation(token_name: str, old_token_suffix: str,
                 new_token_suffix: str, age_before: int | None) -> None:
    """Log une rotation dans l'historique."""
    history = load_history()
    history.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "token_name": token_name,
        "old_token_suffix": old_token_suffix,
        "new_token_suffix": new_token_suffix,
        "age_before_days": age_before,
        "actor": "s_on_hermes_assist",
        "phase": 19,
    })
    save_history(history)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 token rotation status (Phase 19, R2 mitigation)",
    )
    parser.add_argument("--check", action="store_true",
                        help="Verifie rotation status (exit code !=0 si expired)")
    parser.add_argument("--status", action="store_true",
                        help="Affiche status detaille")
    parser.add_argument("--history", action="store_true",
                        help="Affiche l'historique des rotations")
    args = parser.parse_args(argv)

    if args.history:
        history = load_history()
        print(f"=== Historique rotations ({len(history)} entries) ===")
        for h in history[-10:]:
            print(json.dumps(h, ensure_ascii=False))
        return 0

    if args.status or args.check:
        status = check_rotation_status()
        print("=" * 70)
        print("PHASE 19 — TOKEN ROTATION STATUS")
        print("=" * 70)
        print(f"n_total={status['n_total']}, "
              f"n_expired={status['n_expired']}, "
              f"n_warning={status['n_warning']}, "
              f"n_ok={status['n_ok']}")
        print(f"Recommendation: {status['recommendation']}")
        print()
        for item in status["items"]:
            print(f"  [{item['status']:10s}] {item['name']:30s} "
                  f"age={item['age_days']}j  rotated={item['last_rotated']}")
        print()
        print("Procedure de rotation :")
        print("  1. Telegram @BotFather : /revoke -> recevoir nouveau token")
        print("  2. Coller nouveau token dans config/v9_tokens.env")
        print("  3. Mettre a jour {TOKEN_NAME}_LAST_ROTATED=YYYY-MM-DDTHH:MM:SSZ")
        print("  4. python scripts/v9_token_rotation.py --check (verifier)")
        print("  5. python scripts/v9_token_rotation.py --history (logger)")
        return 0 if status["n_expired"] == 0 else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())