"""v9_mirror_auto_activate.py — Phase 19 motion CEO « EDGE FUND MAX ».

Mirror BLOCKING activation automatique apres 20+ logs humains (Phase 14+).
Procedure :
1. Compte les trades humains dans v9_human_trades
2. Si >= MIN_HUMAN_TRADES_FOR_BLOCKING (20) :
   - Active V9_HUMAN_MIRROR_BLOCKING=1 dans .env
   - Log dans data/v9_motion_log.json
3. Sinon, retourne recommendation "wait_more_trades"

Usage :
  python scripts/v9_mirror_auto_activate.py --check    # verifie seulement
  python scripts/v9_mirror_auto_activate.py --activate # active si >= 20
  python scripts/v9_mirror_auto_activate.py --force    # force activation

Auteur : Hermes (Phase 19 motion CEO autopilote, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Bootstrap path pour execution directe CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.mirror_auto_activate")

ENV_FILE = Path(r"C:\projet\V9\config\v9_kill_switches.env")
MOTION_LOG = Path(r"C:\projet\V9\data\v9_motion_log.json")

MIN_HUMAN_TRADES_FOR_BLOCKING = 20


def count_human_trades(db_path: Path | str) -> int:
    """Compte les trades humains dans v9_human_trades."""
    db_path = Path(db_path)
    if not db_path.exists() or db_path.stat().st_size == 0:
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM v9_human_trades"
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return 0


def activate_mirror_blocking() -> bool:
    """Active V9_HUMAN_MIRROR_BLOCKING=1 dans le .env."""
    if not ENV_FILE.exists():
        return False
    content = ENV_FILE.read_text(encoding="utf-8")
    import re
    if "V9_HUMAN_MIRROR_BLOCKING=" in content:
        content = re.sub(
            r"V9_HUMAN_MIRROR_BLOCKING=\d",
            "V9_HUMAN_MIRROR_BLOCKING=1",
            content,
        )
    else:
        content += "\nV9_HUMAN_MIRROR_BLOCKING=1\n"
    ENV_FILE.write_text(content, encoding="utf-8")
    return True


def log_motion(reason: str) -> None:
    """Log dans data/v9_motion_log.json."""
    MOTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    motions = []
    if MOTION_LOG.exists():
        try:
            motions = json.loads(MOTION_LOG.read_text(encoding="utf-8"))
            if not isinstance(motions, list):
                motions = []
        except Exception:
            motions = []
    motions.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "MIRROR_BLOCKING_ACTIVATED",
        "reason": reason,
        "actor": "hermes_auto",
        "motion_ceo_phase": 19,
    })
    MOTION_LOG.write_text(
        json.dumps(motions, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 mirror BLOCKING auto-activation (Phase 19)",
    )
    parser.add_argument("--check", action="store_true",
                        help="Verifie seulement (exit 0 si >=20 trades)")
    parser.add_argument("--activate", action="store_true",
                        help="Active si >= 20 trades")
    parser.add_argument("--force", action="store_true",
                        help="Force activation (sans check)")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    n_human = count_human_trades(DB_PATH)

    print("=" * 70)
    print("PHASE 19 — MIRROR AUTO-ACTIVATION")
    print("=" * 70)
    print(f"n_human_trades = {n_human}")
    print(f"min_required   = {MIN_HUMAN_TRADES_FOR_BLOCKING}")
    print()

    if args.force:
        print("[FORCE] Activation forcee...")
        ok = activate_mirror_blocking()
        if ok:
            log_motion("force --force flag")
            print(">>> V9_HUMAN_MIRROR_BLOCKING=1 active OK")
            return 0
        else:
            print(">>> Activation echouee (env file missing)")
            return 1

    if n_human < MIN_HUMAN_TRADES_FOR_BLOCKING:
        print(f">>> WAIT_MORE_TRADES : {n_human}/{MIN_HUMAN_TRADES_FOR_BLOCKING}")
        remaining = MIN_HUMAN_TRADES_FOR_BLOCKING - n_human
        print(f">>> Encore {remaining} trades GBPUSD 11-13h UTC a logger via "
              "v9_log_human_trade.py")
        return 1 if args.check else 0

    print(f">>> READY : {n_human} trades logues >= {MIN_HUMAN_TRADES_FOR_BLOCKING}")

    if not args.activate:
        print(">>> Use --activate pour activer mirror BLOCKING")
        return 0

    print()
    print("[ACTIVATE] Activation mirror BLOCKING...")
    ok = activate_mirror_blocking()
    if ok:
        log_motion(f"{n_human} human trades >= {MIN_HUMAN_TRADES_FOR_BLOCKING}")
        print(">>> V9_HUMAN_MIRROR_BLOCKING=1 active OK")
        print(f">> Log ecrit : {MOTION_LOG}")
        return 0
    else:
        print(">>> Activation echouee")
        return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())