#!/usr/bin/env python3
"""v10_market_reader_telegram.py — Rapport Telegram unifié GBPUSD (Fatman+VSA+niveaux).

Combine la lecture multi-couche (Fatman, VSA, MTF) ET la lecture par niveaux
(structure) en un rapport lisible, puis l'envoie sur Telegram. R10 : lecture
only, zéro ordre réel.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.v9_telegram_notifier import load_telegram_config, send_telegram  # noqa: E402


def _load(name):
    p = ROOT / "reports" / name
    if p.exists():
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def build_report() -> str:
    mc = _load("v10_market_reader_gbp_2026-08-11.json")
    lv = _load("v10_level_reader_gbp_2026-08-11.json")

    h4 = mc.get("H4", {})
    fat = h4.get("fatman", {})
    vsa = h4.get("vsa", {})
    brk = h4.get("breakdown", {})

    lvH4 = lv.get("H4", {})
    lvRead = lvH4.get("reading", {})
    lvVerdict = lv.get("verdict", {})

    # Verdict combiné (max de gravité)
    mc_action = mc.get("verdict", {}).get("action", "NEUTRAL")
    lv_action = lvVerdict.get("action", "NEUTRAL")
    if "SELL" in lv_action or "SELL" in mc_action:
        final = "SELL_BIAS (pic + résistance majeure)"
    elif "WATCH" in lv_action or "WATCH" in mc_action:
        final = "WATCH_SELL"
    else:
        final = "NEUTRAL"

    lines = [
        "POWERFLOW V10 — LECTURE GBPUSD (Fatman + VSA + Niveaux)",
        f"🕐 {datetime.now(UTC).strftime('%d/%m %H:%M UTC')}",
        "",
        "*Fatman H4*",
        f"  GBP force {fat.get('base_score')} · USD {fat.get('quote_score')}",
        f"  Momentum {fat.get('momentum')} · rang GBP {fat.get('base_rank')}/8",
        "",
        "*VSA H4*",
        f"  État {vsa.get('state')} · volume rel {vsa.get('volume_relative')}",
        f"  Stopping/Climax : {'OUI' if (vsa.get('stopping') or vsa.get('climax')) else 'non'}",
        "",
        "*Structure / Niveaux*",
        f"  Prix {lvRead.get('close')} → résistance H4 {lvRead.get('nearest_resistance')}",
        f"  Distance {lvRead.get('dist_to_res_pips')} pips · touches {lvRead.get('res_touches')}x",
        f"  Position range {brk.get('range_position', 0)*100:.0f}% (extrême haut {brk.get('at_extreme_high')})",
        "",
        f"*VERDICT : {final}*",
    ]
    reasons = mc.get("verdict", {}).get("reasons", []) + lvVerdict.get("reasons", [])
    for r in reasons[:5]:
        lines.append(f"  • {r}")
    lines += [
        "",
        "Lecture only R10. Vendre le pic = attendre un REJET (close sous le",
        "niveau) + SL au-dessus du sommet. Zéro ordre réel.",
    ]
    return "\n".join(lines)


def main() -> int:
    msg = build_report()
    print(msg)
    cfg = load_telegram_config()
    ok = send_telegram(msg, cfg)
    print(f"\n[{'OK' if ok else 'KO'}] Telegram rapport lecture GBPUSD envoyé.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
