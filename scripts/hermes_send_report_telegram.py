#!/usr/bin/env python3
"""Hermes — envoi one-shot du rapport CEO Søn sur Telegram.

Usage : python scripts/hermes_send_report_telegram.py
- Génère un rapport court (≤10 lignes) PowerFlow V9 GBPUSD.
- L'envoie via le channel Telegram du notifier (même token/chat_id).
- Pas de modification de core/v9/* — outillage pur.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Réutilise le module notifier (token + chat_id + send_telegram)
from scripts.v9_telegram_notifier import (
    load_telegram_config,
    send_telegram,
)

UTC = datetime.now(timezone.utc)
CEST = UTC.astimezone(timezone.utc)  # placeholder, l'utilisateur est GMT+1 (Paris)

REPORT = (
    "*PowerFlow V9 — Rapport CEO Søn — 2026-07-07 21h15 CEST*\n"
    "\n"
    "*Marché GBPUSD (live)*\n"
    "• Dernier tick M5 : 1.3362, range 1.3360–1.3375\n"
    "• Reversal baissier 30 dernières min (-13 pips)\n"
    "• Zones D1 AUD/NZD + CHF/EUR/JPY encore en place H4\n"
    "• Toutes zones en NEUTRAL (tension=0) — pas d'extrême\n"
    "\n"
    "*Pipeline V9*\n"
    "✅ Orchestrateur VIVANT (PID 42608, port 31685)\n"
    "✅ 419 décisions directionnelles aujourd'hui (8h→19h)\n"
    "✅ 72 184 snapshots, 44 252 scenes DB\n"
    "✅ 9/9 principes ACTIVE déclenchables (signal NZD fort aujourd'hui)\n"
    "❌ 0 paper trade (range, comportement nominal)\n"
    "\n"
    "*Session macro*\n"
    "⏳ Aucune news HIGH jusqu'à 2026-08-03 (ISM_PMI)\n"
    "⏳ Prochain driver : NFP ven 2026-08-07 12h30 UTC\n"
    "\n"
    "*Note honnête Søn* : j'avais annoncé `orchestrateur arrêté` dans mon rapport précédent. Faux. PID 42608 tourne depuis 9h43 sans interruption. Serveur 31685 = sockets MT4 bruts, pas HTTP (curl timeout ≠ down). Mauvaise lecture de ma part, corrigée.\n"
    "\n"
    "_Mode A — VEILLE_"
)


def main() -> int:
    cfg = load_telegram_config()
    ok = send_telegram(REPORT, cfg)
    print("[OK] Telegram envoyé." if ok else "[KO] Telegram failed.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
