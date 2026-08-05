"""V10 Telegram Alert — notifie les signaux actifs BUY/SELL via Telegram (Sprint 19).

Envoie sur le canal Telegram du projet (v9_telegram_notifier) les signaux
actifs BUY/SELL produits par le pipeline V10. Réutilise le notifier existant
(token + chat_id + anti-spam) — n'invente pas de canal, ne touche pas aux secrets.

R10 : notification only, aucun ordre réel.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_telegram_notifier import (  # noqa: E402
    load_telegram_config,
    send_telegram,
)

log = logging.getLogger(__name__)
DEFAULT_LATEST = ROOT / "reports" / "v10_live_decision_latest.json"


def build_message(latest_path: Path) -> str:
    """Construit un message Telegram lisible depuis le dernier rapport live."""
    if not latest_path.exists():
        return "⚠️ V10 : aucun rapport live decision trouvé"
    try:
        d = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"⚠️ V10 : erreur lecture rapport ({type(exc).__name__})"

    results = d.get("tick_results", [])
    active = [r for r in results if r.get("action") in ("BUY", "SELL")]
    if not active:
        return "🟡 V10 : aucun signal actif (tous WAIT)"

    lines = [f"🔔 V10 SIGNALS ({len(active)}/{len(results)})"]
    lines.append("─" * 20)
    for r in active:
        lines.append(
            f"  {r['pair']} {r['action']} "
            f"(regime={r.get('regime')}, level={r.get('filtered_level')}, "
            f"lot={r.get('lot_size')})")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", default=str(DEFAULT_LATEST))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    msg = build_message(Path(args.latest))
    log.info("Message: %s", msg.replace("\n", " | "))

    if args.dry_run:
        print(msg)
        print("[DRY-RUN] non envoyé")
        return 0

    try:
        config = load_telegram_config()
        ok = send_telegram(msg, config)
        print(f"Envoyé: {ok}")
        return 0 if ok else 1
    except Exception as exc:
        log.error("Envoi Telegram échoué: %s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
