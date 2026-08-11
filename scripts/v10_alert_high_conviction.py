"""scripts/v10_alert_high_conviction.py — Alertes Telegram haute-conviction (C22).

Objectif CEO : recevoir UNIQUEMENT ce qui mérite attention, sans surveiller
le marché en continu. N'envoie que :
  1. Signaux A1 (haute conviction) — BUY/SELL avec signal_level A1
  2. Changement d'état notable : passage de WAIT→BUY/SELL sur une paire
  3. Alerte santé : health_score DEGRADED/ERROR (pipeline en panne)

Anti-spam : ne renvoie PAS le même signal deux fois (dédup par pair+tf+action).
Silence si rien de pertinent → tu ne reçois que l'essentiel.

R10 : notification only, zéro ordre. R6 fail-open.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.v9_telegram_notifier import (  # noqa: E402
    load_telegram_config,
    send_telegram,
)

DEFAULT_LATEST = ROOT / "reports" / "v10_live_decision_latest.json"
STATE_FILE = ROOT / "reports" / "v10_alert_high_conviction_state.json"

# Seuil : signal_level A1 = haute conviction
HIGH_CONVICTION_LEVELS = ("A1",)


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def build_high_conviction(latest_path: Path) -> str | None:
    """Retourne un message si un signal A1 est présent, sinon None (silence)."""
    if not latest_path.exists():
        return None  # silence : pas de rapport = pas d'alerte
    try:
        d = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    results = d.get("tick_results", [])
    # Signaux A1 actifs
    a1 = [
        r for r in results
        if r.get("action") in ("BUY", "SELL")
        and r.get("signal_level") in HIGH_CONVICTION_LEVELS
    ]
    if not a1:
        return None  # silence : pas de signal A1

    lines = [f"🎯 V10 HAUTE CONVICTION ({len(a1)} signal(s) A1)"]
    lines.append("─" * 20)
    for r in a1:
        lines.append(
            f"  {r.get('pair')} {r.get('timeframe')} {r.get('action')} "
            f"(A1, lot={r.get('lot_size')})"
        )
    return "\n".join(lines)


def build_health_alert() -> str | None:
    """Alerte si le pipeline est dégradé (health_score < seuil)."""
    try:
        from scripts.run_live_session_report import health_score
        h = health_score()
        score = float(h.get("score", 0.0))
        status = str(h.get("status", "ERROR"))
        if status == "ERROR" or score < 50.0:
            return (
                f"🚨 V10 PIPELINE DÉGRADÉ\n"
                f"  health_score={score} ({status})\n"
                f"  {h.get('error', '')}"
            )
    except Exception:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", default=str(DEFAULT_LATEST))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-health", action="store_true",
                    help="inclut l'alerte santé pipeline")
    args = ap.parse_args()

    msgs = []
    # 1. Signaux A1 (dédup par état)
    msg = build_high_conviction(Path(args.latest))
    if msg:
        state = _load_state()
        key = msg  # message complet comme clé de dédup
        if state.get("last_sent") != key:
            msgs.append(msg)
            state["last_sent"] = key
            _save_state(state)

    # 2. Alerte santé (optionnelle, pour ne pas spammer)
    if args.include_health:
        health = build_health_alert()
        if health:
            msgs.append(health)

    if not msgs:
        if args.dry_run:
            print("[DRY-RUN] rien de pertinent — silence (aucun envoi)")
        return 0

    text = "\n\n".join(msgs)
    if args.dry_run:
        print(text)
        print("[DRY-RUN] non envoyé")
        return 0

    try:
        config = load_telegram_config()
        ok = send_telegram(text, config)
        print(f"Envoyé: {ok}")
        return 0 if ok else 1
    except Exception as exc:
        print(f"Envoi Telegram échoué: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
