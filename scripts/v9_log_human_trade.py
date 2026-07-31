#!/usr/bin/env python3
"""v9_log_human_trade.py — CLI pour logger un trade manuel (J3 28/07).

Usage:
    python scripts/v9_log_human_trade.py \
        --symbol GBPUSD --direction haussiere --timeframe M5 \
        --entry 1.2543 --sl 1.2535 --tp 1.2568 \
        --conf 80 --session london \
        --principes PRICE_LAG_AT_NODE_BIRTH POWER_ANGLE_BREAK_TO_PRICE_IMPACT \
        --notes "Setup propre post-NY open"

Motion CEO « GO MAX » : le système apprend ton fingerprint.
Additif (R2), R6 jamais bloquant.

Auteur : Hermes (autopilot CEO Søn 28/07)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Permettre l'import depuis la racine du projet
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.v9.human_trades_db import insert_human_trade, init_human_trades_db
from core.v9.config import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("v9.log_human_trade")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="V9 — log un trade manuel (collecte fingerprint humain)",
    )
    parser.add_argument("--symbol", required=True, help="ex: GBPUSD")
    parser.add_argument("--direction", required=True, choices=["haussiere", "baissiere"])
    parser.add_argument("--timeframe", required=True,
                        choices=["M1", "M5", "M15", "M30", "H1", "H4", "D1"])
    parser.add_argument("--entry", required=True, type=float, help="prix d'entrée")
    parser.add_argument("--sl", type=float, help="stop loss")
    parser.add_argument("--tp", type=float, help="take profit")
    parser.add_argument("--conf", type=int, help="confiance déclarée 0-100")
    parser.add_argument("--session", choices=[
        "asie", "sydney", "london", "overlap", "new_york", "inconnu",
    ])
    parser.add_argument("--principes", nargs="+", default=[],
                        help="noms des principes déclencheurs (espacés)")
    parser.add_argument("--snapshot", help="snapshot_id live (si connu)")
    parser.add_argument("--notes", help="notes texte libre")
    parser.add_argument("--db-path", default=None, help=f"défaut: {DB_PATH}")

    args = parser.parse_args()

    if not init_human_trades_db(args.db_path):
        log.error("Migration schema v9_human_trades échouée — abandon.")
        return 2

    rid = insert_human_trade(
        db_path=args.db_path or DB_PATH,
        symbol=args.symbol,
        direction=args.direction,
        timeframe=args.timeframe,
        entry_price=args.entry,
        sl_price=args.sl,
        tp_price=args.tp,
        confiance=args.conf,
        session=args.session,
        principes=args.principes,
        snapshot_id=args.snapshot,
        notes=args.notes,
    )
    if rid is None:
        log.error("Insert échoué (R6 silencieux).")
        return 1
    log.info(
        "Trade humain logé — id=%s %s %s TF=%s entry=%.5f",
        rid, args.symbol, args.direction, args.timeframe, args.entry,
    )
    print(json.dumps({
        "status": "ok", "id": rid,
        "symbol": args.symbol, "direction": args.direction,
        "timeframe": args.timeframe, "entry": args.entry,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
