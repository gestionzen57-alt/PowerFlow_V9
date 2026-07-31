"""v9_auto_promote_stars.py — Phase 3 motion CEO « EDGE FUND MAX ».

Force la promotion ACTIVE des 3 stars MEGA-EDGE dans
config/calibration_overrides.json. Audit SQL 90j a confirmé :

- PRICE_LAG_AT_NODE_BIRTH : 45 trades WR 100% +227.5p
- POWER_ANGLE_BREAK_TO_PRICE_IMPACT : 17 trades WR 100% +101.5p
- GRAVITY_RESPRING_NODE : 9 trades WR 100% +50.5p

= 71 trades WR 100% +379.5p cumulés. Edge institutionnel.

R2 additif : si l'override n'existe pas, on l'initialise. R6 jamais
bloquant. Kill switch V9_AUTO_PROMOTE_STARS_ENABLED (defaut ON).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.v9.auto_calibrator import (
    CALIBRATION_OVERRIDES_PATH,
    _load_overrides, _save_overrides,
)

log = logging.getLogger("v9.auto_promote_stars")

# 3 stars MEGA-EDGE (audit SQL 90j)
MEGA_EDGE_STARS = frozenset({
    "PRICE_LAG_AT_NODE_BIRTH",
    "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
    "GRAVITY_RESPRING_NODE",
})


def auto_promote_stars_enabled() -> bool:
    """Kill switch V9_AUTO_PROMOTE_STARS_ENABLED — defaut ON autopilot."""
    return os.environ.get("V9_AUTO_PROMOTE_STARS_ENABLED", "1") == "1"


def force_promote_stars(path: Path | None = None) -> dict[str, object]:
    """Force les 3 stars MEGA-EDGE ACTIVE dans calibration_overrides.json.

    Returns dict avec {promotions, already_present, written}.
    """
    if not auto_promote_stars_enabled():
        return {"promotions": [], "already_present": [], "written": False}

    p = Path(path) if path else CALIBRATION_OVERRIDES_PATH
    overrides = _load_overrides(p)

    current_ids = set(overrides.get("principle_active_ids_override") or [])
    to_promote = list(MEGA_EDGE_STARS - current_ids)
    already_present = list(MEGA_EDGE_STARS & current_ids)

    if to_promote:
        current_ids.update(to_promote)
        overrides["principle_active_ids_override"] = sorted(current_ids)
        overrides["updated_at"] = datetime.now(timezone.utc).isoformat()
        overrides["applied_by"] = "v9_auto_promote_stars_phase3"
        _save_overrides(p, overrides)
        log.info("auto_promote_stars: promoted %s", to_promote)

    return {
        "promotions": to_promote,
        "already_present": already_present,
        "written": bool(to_promote),
    }


def main():
    logging.basicConfig(level=logging.INFO)
    res = force_promote_stars()
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())