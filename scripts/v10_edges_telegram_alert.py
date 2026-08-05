"""V10 Edges Telegram Alert — notifie la carte des edges sur Telegram (Sprint R).

Envoie le résumé de la carte des edges du replay batch (les configurations
validées à trader) sur le canal Telegram du projet.

R10 : notification only, zéro ordre réel.
"""
from __future__ import annotations

import argparse
import glob
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


def build_edges_message() -> str:
    """Construit le message carte des edges depuis le dernier replay batch."""
    files = sorted(glob.glob(str(ROOT / "reports" / "v10_replay_batch_*.json")))
    if not files:
        return "⚠️ V10 : aucun rapport replay batch trouvé"
    try:
        d = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    except Exception as exc:
        return f"⚠️ V10 : erreur lecture replay ({type(exc).__name__})"

    edge_map = d.get("edge_map", {})
    lm = d.get("learning_model", {})
    yes = [kv for kv in edge_map.items() if kv[1].get("edge") == "YES"]
    yes.sort(key=lambda kv: -kv[1]["wr"])

    lines = [f"📊 V10 EDGE MAP ({len(yes)} edges / {len(edge_map)})"]
    lines.append("─" * 20)
    lines.append(f"  Modèle: {lm.get('n_trades_total', 0)} trades, "
                 f"WR {lm.get('wr', 0):.2f}")
    if lm.get("drift_detected"):
        lines.append("  ⚠️ Drift détecté (recalibration nécessaire)")
    lines.append("")
    for k, v in yes[:10]:
        lines.append(f"  {k}: WR {v['wr']:.2f} ({v['n']} trades, {v['direction']})")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    msg = build_edges_message()
    print(msg)
    if args.dry_run:
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
