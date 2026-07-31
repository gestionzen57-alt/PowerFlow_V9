"""v9_pre_live_check.py — Phase 14 motion CEO « EDGE FUND MAX ».

Execute les 4 verifications pre-LIVE en une commande :
1. Bridge MT4 check (v9_check_orderbridge)
2. Heartbeat capture (v9_heartbeat_capture)
3. Boot alerts (v9_boot_alerts)
4. Mirror readiness (v9_mirror_check)

Verdict global : ready_live / fix_issues_first.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Bootstrap path pour execution directe via `python scripts/v9_pre_live_check.py`.
# Sans ca, `from core.v9.config import DB_PATH` echoue en CLI.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.pre_live_check")


def run_all_checks(workspace: Path | str = ".") -> dict[str, object]:
    """Execute les 4 checks et retourne verdict global."""
    workspace = Path(workspace)
    from core.v9.config import DB_PATH

    checks = {}

    # 1. Bridge MT4
    try:
        from scripts.v9_check_orderbridge import check_orderbridge
        checks["orderbridge"] = check_orderbridge(workspace)
    except Exception as exc:
        checks["orderbridge"] = {"ok": False, "alert": True,
                                  "error": str(exc)}

    # 2. Heartbeat capture
    try:
        from scripts.v9_heartbeat_capture import check_heartbeat
        checks["heartbeat"] = check_heartbeat(DB_PATH)
    except Exception as exc:
        checks["heartbeat"] = {"ok": False, "alert": True,
                                "error": str(exc)}

    # 3. Boot alerts (utilise env var V9_BOOT_CONTEXT=prod)
    try:
        os.environ.setdefault("V9_BOOT_CONTEXT", "prod")
        from core.v9.v9_boot_alerts import check_kill_switch_coherence
        boot_warnings = check_kill_switch_coherence(db_path=DB_PATH)
        checks["boot_alerts"] = {
            "ok": len(boot_warnings) == 0,
            "n_warnings": len(boot_warnings),
            "warnings": boot_warnings,
        }
    except Exception as exc:
        checks["boot_alerts"] = {"ok": False, "alert": True,
                                  "error": str(exc)}

    # 4. Mirror readiness
    try:
        from scripts.v9_mirror_check import check_mirror_readiness
        checks["mirror"] = check_mirror_readiness(DB_PATH)
    except Exception as exc:
        checks["mirror"] = {"ok": False, "alert": True,
                             "error": str(exc)}

    # Verdict global
    all_ok = all(c.get("ok", False) for c in checks.values())
    any_alert = any(c.get("alert", False) for c in checks.values())

    return {
        "ready_live": all_ok,
        "any_alert": any_alert,
        "checks": checks,
        "recommendation": (
            "ready_live_motion" if all_ok
            else "fix_issues_first"
        ),
        "blocking_human_actions": [
            "1. Rotation tokens Telegram CEO (BLOQUANT humain)",
            "2. 100 trades live expectancy check",
            "3. DB backup MD5 (R8 doctrine)",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    workspace = Path(argv[0]) if argv else Path(".")
    result = run_all_checks(workspace)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ready_live"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())