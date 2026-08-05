"""V10 Daily Bilan Telegram — notifie le bilan quotidien sur Telegram (Phase R).

Envoie le bilan de la journée (décisions, outcomes, apprentissage, reco R8)
sur le canal Telegram du projet. Lisible pour le CEO.

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


def build_bilan_message() -> str:
    """Construit le message bilan depuis le dernier rapport daily_bilan."""
    files = sorted(glob.glob(str(ROOT / "reports" / "v10_daily_bilan_*.json")))
    if not files:
        return "⚠️ V10 : aucun bilan quotidien trouvé"
    try:
        d = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    except Exception as exc:
        return f"⚠️ V10 : erreur lecture bilan ({type(exc).__name__})"

    dec = d.get("decisions_today", {})
    learning = d.get("learning", {})
    lines = [f"📅 V10 BILAN {d.get('date', '?')}"]
    lines.append("─" * 20)
    lines.append(f"  Décisions: {dec.get('n_trades', 0)}")
    lines.append(f"  WR: {dec.get('wr', 0):.2f}  PnL: {dec.get('total_pnl', 0):.1f}p")
    if dec.get("sharpe_like"):
        lines.append(f"  Sharpe: {dec['sharpe_like']:.2f}")
    if learning.get("drift_detected"):
        lines.append(f"  ⚠️ Drift: OUI (recalibration nécessaire)")
    lines.append(f"  Reco: {d.get('recommendation', 'HOLD')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    msg = build_bilan_message()
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
