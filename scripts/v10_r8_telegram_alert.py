"""V10 R8 Telegram Alert — alerte de recalibration automatique (Sprint 20).

Ferme la boucle d'alerte R8 : lit la boucle fermée (v10_closed_loop) et la
synthèse hebdo (v10_weekly_summary), et notifie le CEO sur Telegram quand
une re-calibration est recommandée / déclenchée.

Messages :
  - Recalibration DÉCLENCHÉE (drift / re-calib recommandée) avec décision
    DEPLOY/REVERT/HOLD + WR avant/après.
  - Synthèse hebdo dégradée (WR < 0.40 ou Sharpe < 0) → reco recalibrage.

R10 : notification only, zéro ordre réel. R9 : pnl proxies, edge relatif.
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


def _latest_report(pattern: str) -> dict:
    """Charge le plus récent rapport JSON correspondant au pattern."""
    files = sorted(glob.glob(str(ROOT / pattern)))
    if not files:
        return {}
    try:
        return json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("lecture %s échouée: %s", files[-1], type(exc).__name__)
        return {}


def build_alert() -> tuple:
    """Construit le message R8. Retourne (message, should_send)."""
    closed = _latest_report("reports/v10_closed_loop_*.json")
    weekly = _latest_report("reports/v10_weekly_summary_*.json")

    parts = []
    should_send = False

    # 1. Boucle fermée R8
    rc = closed.get("recalibration", {})
    if rc.get("triggered"):
        should_send = True
        parts.append("🔄 V10 RECALIBRATION")
        parts.append("─" * 20)
        parts.append(f"  Déclenché: {rc.get('reason')}")
        parts.append(f"  Décision: {rc.get('decision')}")
        parts.append(f"  WR avant: {rc.get('before_wr')} → après: {rc.get('after_wr')}")
        if rc.get("setups"):
            parts.append(f"  Setups: {rc.get('setups')}")

    # 2. Synthèse hebdo dégradée
    if weekly.get("recalibrate_recommended"):
        should_send = True
        parts.append("📊 V10 HEBDOMADAIRE DEGRADÉ")
        parts.append("─" * 20)
        for reason in weekly.get("recalibrate_reasons", []):
            parts.append(f"  {reason}")
        wr = weekly.get("decisions", {}).get("wr")
        if wr is not None:
            parts.append(f"  WR: {wr:.2f}")
        delta = weekly.get("wr_delta_pts")
        if delta is not None:
            parts.append(f"  ΔWR vs benchmark: {delta}pts")

    if not should_send:
        return None, False

    return "\n".join(parts), True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    msg, should_send = build_alert()
    if not should_send:
        print("Aucune alerte R8 nécessaire (système sain)")
        return 0

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
