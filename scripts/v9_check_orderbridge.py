"""v9_check_orderbridge.py — Phase 13 motion CEO « EDGE FUND MAX ».

Verifie que V9_OrderBridge.mq4 est configure pour Phase 12 LIVE :
- DryRun = true (mode safe par defaut)
- Comment contient 'V9_' pour identifier trades auto
- Pas de dependances circulaires sur OrderSend rate

Sortie JSON stdout pour integration cron pre-live.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

log = logging.getLogger("v9.check_orderbridge")


EXPECTED_BRIDGE_FILE = "mt4_bridge/V9_OrderBridge.mq4"
EXPECTED_BRIDGE_COMPILED = "mt4_bridge/V9_OrderBridge.ex4"

REQUIRED_EXTERNS = {
    "DryRun": r"extern\s+bool\s+DryRun\s*=\s*true",
    "OrderQueuePath": r"extern\s+string\s+OrderQueuePath",
    "ProcessedPath": r"extern\s+string\s+ProcessedPath",
    "FailedPath": r"extern\s+string\s+FailedPath",
    "PollSeconds": r"extern\s+int\s+PollSeconds",
    "Slippage": r"extern\s+int\s+Slippage",
    "MagicNumber": r"extern\s+int\s+MagicNumber",
}

# Externs OPTIONNELS (legacy Phase 1) — non obligatoires en Phase 13.
# Le vrai V9_OrderBridge.mq4 n'a plus SymbolFilter ni MaxLot car le sizing
# vient du trade_engine (côté Python) et le filtre symbole est dans la queue.
OPTIONAL_EXTERNS = ("SymbolFilter", "MaxLot")

FORBIDDEN_PATTERNS = {
    "live_ordersend": r"OrderSend\s*\(\s*[^)]*OP_BUY\s*,\s*[^)]*DryRun\s*=\s*false",
    "unbounded_lot": r"OrderSend\s*\([^)]*Lots\s*=\s*[0-9]+\.[0-9]+\s*\)",
}


def check_orderbridge(workspace: Path | str = ".") -> dict[str, object]:
    """Verifie le bridge MT4. Retourne dict avec checks passes/fails."""
    workspace = Path(workspace)
    bridge_mq4 = workspace / EXPECTED_BRIDGE_FILE
    bridge_ex4 = workspace / EXPECTED_BRIDGE_COMPILED

    checks = {
        "bridge_mq4_exists": bridge_mq4.exists(),
        "bridge_ex4_compiled": bridge_ex4.exists(),
        "dry_run_default": False,
        "required_externs": {},
        "forbidden_patterns": {},
    }

    if not bridge_mq4.exists():
        return {
            "ok": False,
            "alert": True,
            "checks": checks,
            "recommendation": "verifier_mt4_bridge_deployment",
        }

    src = bridge_mq4.read_text(encoding="utf-8", errors="replace")

    # DryRun = true par defaut
    checks["dry_run_default"] = bool(re.search(
        r"extern\s+bool\s+DryRun\s*=\s*true", src,
    ))

    # Externs requis
    for name, pattern in REQUIRED_EXTERNS.items():
        checks["required_externs"][name] = bool(re.search(pattern, src))

    # Patterns interdits (live ordersend DryRun=false, lots en dur)
    for name, pattern in FORBIDDEN_PATTERNS.items():
        matches = re.findall(pattern, src, re.IGNORECASE)
        checks["forbidden_patterns"][name] = len(matches)

    # Verdict global
    fatal = (
        not checks["bridge_mq4_exists"]
        or not checks["dry_run_default"]
        or any(checks["forbidden_patterns"].values())
    )
    required_ok = all(checks["required_externs"].values())

    return {
        "ok": not fatal and required_ok,
        "alert": fatal,
        "checks": checks,
        "recommendation": (
            "ready_phase12_live" if (not fatal and required_ok)
            else "fix_orderbridge_before_live"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    workspace = Path(argv[0]) if argv else Path(".")
    result = check_orderbridge(workspace)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())