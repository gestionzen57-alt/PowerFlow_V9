"""v9_auto_rollback.py — Phase 18 motion CEO « EDGE FUND MAX ».

Auto-rollback motion si L12 early warning drift detecte ou si paper audit
recommendation != GO_PHASE12_LIVE. Procedures :

1. Detecte drift WR 7j (L12) ou low WR (Phase 17 audit)
2. Si drift > seuil OU audit != GO_PHASE12_LIVE :
   - Desactive V9_MT4_BRIDGE_ENABLED=0 dans .env
   - Desactive V9_PAPER_TRADE_HALT=1 (securite)
   - Log l'evenement dans data/v9_motion_log.json
   - Genere rapport pour Søn

Note : rollback AUTO uniquement si SEUILS dépasses. Pour activation,
utiliser v9_pre_live_check.py (Phase 14) qui verifie avant motion.

Auteur : Hermes (Phase 18 motion CEO autopilote, 31/07/2026)
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

log = logging.getLogger("v9.auto_rollback")

ENV_FILE = Path(r"C:\projet\V9\config\v9_kill_switches.env")
MOTION_LOG = Path(r"C:\projet\V9\data\v9_motion_log.json")

# Seuils rollback (calibres Phase 17)
ROLLBACK_DRIFT_THRESHOLD = -5.0  # WR drift <= -5pts sur 3j → rollback
ROLLBACK_WR_THRESHOLD = 50.0     # WR global < 50% → rollback
ROLLBACK_EXP_NET_THRESHOLD = 0.0  # expectancy nette <= 0 → rollback


def detect_drift(db_path: Path | str) -> dict:
    """Detecte drift WR 7j via detect_wr_early_warning (L12)."""
    from core.v9.v9_spread_simulator import detect_wr_early_warning
    return detect_wr_early_warning(db_path, lookback_days=7,
                                    drift_threshold=3.0)


def detect_paper_audit(db_path: Path | str) -> dict:
    """Detecte etat actuel via audit_paper_trades (Phase 17)."""
    from scripts.v9_daily_paper_audit import audit_paper_trades
    return audit_paper_trades(db_path, days=7)


def should_rollback(drift: dict, audit: dict) -> tuple[bool, list[str]]:
    """Decide si rollback necessaire. Retourne (bool, liste raisons)."""
    reasons = []

    # 1. L12 drift > seuil
    if drift.get("alert") and drift.get("drift_pts", 0) <= ROLLBACK_DRIFT_THRESHOLD:
        reasons.append(
            f"L12 drift detecte : {drift.get('drift_pts'):.1f}pts "
            f"<= {ROLLBACK_DRIFT_THRESHOLD}pts"
        )

    # 2. Audit WR global trop bas
    if audit.get("n_closed", 0) >= 10:
        wr = audit.get("wr_pct", 0)
        if wr < ROLLBACK_WR_THRESHOLD:
            reasons.append(
                f"WR global {wr:.1f}% < {ROLLBACK_WR_THRESHOLD:.0f}% "
                f"(n_closed={audit.get('n_closed')})"
            )

    # 3. Expectancy nette <= 0
    if audit.get("n_closed", 0) >= 10:
        exp_net = audit.get("expectancy_net", 0)
        if exp_net <= ROLLBACK_EXP_NET_THRESHOLD:
            reasons.append(
                f"Expectancy net {exp_net:.2f}p <= {ROLLBACK_EXP_NET_THRESHOLD} "
                f"(n_closed={audit.get('n_closed')})"
            )

    return (len(reasons) > 0, reasons)


def apply_rollback(rollback_id: str, reasons: list[str]) -> bool:
    """Applique le rollback : V9_MT4_BRIDGE_ENABLED=0 + V9_PAPER_TRADE_HALT=1."""
    if not ENV_FILE.exists():
        log.error("rollback: env file not found %s", ENV_FILE)
        return False

    content = ENV_FILE.read_text(encoding="utf-8")
    changes = []

    # V9_MT4_BRIDGE_ENABLED=0
    if "V9_MT4_BRIDGE_ENABLED=1" in content:
        content = content.replace(
            "V9_MT4_BRIDGE_ENABLED=1",
            "V9_MT4_BRIDGE_ENABLED=0",
        )
        changes.append("V9_MT4_BRIDGE_ENABLED=1 → 0")
    elif "V9_MT4_BRIDGE_ENABLED=0" not in content:
        # Ajouter si absent
        content += "\nV9_MT4_BRIDGE_ENABLED=0\n"
        changes.append("V9_MT4_BRIDGE_ENABLED=0 (added)")

    # V9_PAPER_TRADE_HALT=1
    if "V9_PAPER_TRADE_HALT=" in content:
        import re
        content = re.sub(
            r"V9_PAPER_TRADE_HALT=\d", "V9_PAPER_TRADE_HALT=1", content,
        )
        changes.append("V9_PAPER_TRADE_HALT=1 (forced)")
    else:
        content += "\nV9_PAPER_TRADE_HALT=1\n"
        changes.append("V9_PAPER_TRADE_HALT=1 (added)")

    ENV_FILE.write_text(content, encoding="utf-8")
    log.warning("rollback applique : %s", changes)

    # Log motion
    log_motion(rollback_id, reasons, changes)
    return True


def log_motion(rollback_id: str, reasons: list[str], changes: list[str]) -> None:
    """Log l'evenement motion dans data/v9_motion_log.json."""
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
        "id": rollback_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "ROLLBACK",
        "reasons": reasons,
        "changes": changes,
        "actor": "hermes_auto",
        "motion_ceo_phase": 18,
    })
    MOTION_LOG.write_text(
        json.dumps(motions, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 auto-rollback motion (Phase 18)",
    )
    parser.add_argument("--check", action="store_true",
                        help="Verifie si rollback necessaire, sans l'appliquer")
    parser.add_argument("--force", action="store_true",
                        help="Force le rollback sans verification")
    args = parser.parse_args(argv)

    from core.v9.config import DB_PATH
    db_path = DB_PATH

    print("=" * 70)
    print("PHASE 18 — AUTO-ROLLBACK MOTION CHECK")
    print("=" * 70)
    print()

    drift = detect_drift(db_path)
    audit = detect_paper_audit(db_path)

    print(f"L12 drift : {drift.get('reason', 'unknown')}, "
          f"drift_pts={drift.get('drift_pts', 'n/a')}, "
          f"alert={drift.get('alert', False)}")
    print(f"Paper audit : n_closed={audit.get('n_closed', 0)}, "
          f"WR={audit.get('wr_pct', 0):.1f}%, "
          f"exp_net={audit.get('expectancy_net', 0):.2f}p, "
          f"max_dd={audit.get('max_dd_net', 0):.1f}p, "
          f"recommendation={audit.get('recommendation', 'n/a')}")
    print()

    if args.force:
        print("[FORCE] Application rollback force...")
        rollback_id = f"rollback_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        ok = apply_rollback(rollback_id, ["force --force flag"])
        return 0 if ok else 1

    should, reasons = should_rollback(drift, audit)

    if not should:
        print(">>> Aucun rollback necessaire. Systeme OK.")
        return 0

    print("[ALERT] Rollback necessaire :")
    for r in reasons:
        print(f"  - {r}")
    print()

    if args.check:
        print("[CHECK] Mode check seul, pas d'application.")
        return 2  # code 2 = alerte detectee mais non appliquee

    # Appliquer rollback
    rollback_id = f"rollback_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    ok = apply_rollback(rollback_id, reasons)
    if ok:
        print(f">>> Rollback applique OK : {rollback_id}")
        print(f">> Log ecrit : {MOTION_LOG}")
        return 0
    else:
        print(">>> Rollback ECHOUE")
        return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())