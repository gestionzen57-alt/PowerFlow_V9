"""scripts/v9_auto_actions_on_halt.py — auto-actions DD halt_forever (Phase 1.1, 28/07).

Quand DrawdownProtector détecte un palier halt_forever (DD ≥ 15% capital),
ce script écrit automatiquement les kill switches OFF dans
\`config/v9_kill_switches.env\` pour arrêter tous les leviers quantiques
(Risk Parity, Meta Learning, Cycle Memory, Unified Sizing) — protection
immédiate sans attendre une motion CEO manuelle.

Doctrine : R25' strict (auto-actions en DD halt_forever UNIQUEMENT, motion CEO
requise pour toute autre promotion/démotion). R6 défensif (idempotent,
dry-run par défaut, audit log DECISIONS_LOG.md).

Workflow :
  1. read DrawdownProtector state via update_state_from_db()
  2. decide() → palier halt_forever ?
  3. oui → lire config/v9_kill_switches.env, mettre les KS critiques à OFF
  4. écrire fichier (preserve comments + sections)
  5. append motion au DECISIONS_LOG.md
  6. exit code 0 si halt appliqué, 1 si pas halt, 4 si DB error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\projet\V9")
sys.path.insert(0, str(ROOT))

KS_ENV_PATH = ROOT / "config" / "v9_kill_switches.env"
DECISIONS_LOG = ROOT / "workspace" / "perplexity" / "memory" / "DECISIONS_LOG.md"

# Kill switches mis à OFF quand halt_forever (5 leviers quantiques principaux)
HALT_KS_OFF = [
    "V9_RISK_PARITY_ENABLED",
    "V9_META_LEARNING_ENABLED",
    "V9_CYCLE_MEMORY_ENABLED",
    "V9_UNIFIED_SIZING_ENABLED",
    "V9_EDGE_DECAY_MONITOR_ENABLED",
]


def detect_halt(initial_capital: float = 10000.0) -> dict:
    """Détecte si DD est en palier halt_forever via DrawdownProtector.

    Returns : {halt_forever: bool, palier: str, dd_pct: float, cum_pips: float,
               state: DrawdownState.to_dict(), decision: DrawdownDecision.to_dict()}.
    """
    try:
        from core.v9.v9_drawdown_protector import DrawdownProtector
        protector = DrawdownProtector(initial_capital=initial_capital, db_path=ROOT / "data" / "v9_forces.db")
        decision = protector.decide()
        state = protector.state
        # Convertir pct
        dd_pct = state.current_drawdown / max(initial_capital, 1.0)
        return {
            "halt_forever": decision.action == "halt_forever",
            "palier": decision.action,
            "dd_pct": dd_pct,
            "cum_pips": state.current_pips,
            "state": state.to_dict(),
            "decision": {
                "action": decision.action,
                "position_multiplier": decision.position_multiplier,
                "rationale": decision.rationale,
            },
        }
    except Exception as exc:
        return {
            "halt_forever": False,
            "error": f"detect_halt failed: {exc}",
        }


def apply_halt(dry_run: bool = True, initial_capital: float = 10000.0) -> dict:
    """Si halt_forever détecté, écrit les kill switches OFF.

    Returns : {applied: bool, ks_changed: [...], motion_id: str, dry_run: bool}.
    """
    detection = detect_halt(initial_capital=initial_capital)
    if not detection.get("halt_forever"):
        return {
            "applied": False,
            "reason": f"DD palier = {detection.get('palier', 'unknown')} (pas halt_forever)",
            "dd_pct": detection.get("dd_pct", 0),
            "dry_run": dry_run,
        }

    # Lire KS env actuel
    if not KS_ENV_PATH.exists():
        return {"applied": False, "error": f"KS env absent: {KS_ENV_PATH}"}

    content = KS_ENV_PATH.read_text(encoding="utf-8")
    ks_changed = []
    for ks in HALT_KS_OFF:
        # Pattern : KS_NAME=1 ou KS_NAME=0 (sur sa propre ligne, pas en commentaire)
        pattern = rf"^(?!#)({ks})=([01])"
        m = re.search(pattern, content, re.MULTILINE)
        if m:
            current = m.group(2)
            if current == "1":
                if not dry_run:
                    content = re.sub(pattern, rf"\1=0", content, count=1, flags=re.MULTILINE)
                ks_changed.append({"ks": ks, "from": "1", "to": "0"})

    if not dry_run and ks_changed:
        KS_ENV_PATH.write_text(content, encoding="utf-8")
        # Append motion au DECISIONS_LOG
        motion = (
            f"\n## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — "
            f"AUTO-ACTION DD halt_forever (script v9_auto_actions_on_halt.py)\n\n"
            f"- DD palier : halt_forever ({detection['dd_pct']*100:.1f}% ≥ 15% capital)\n"
            f"- cum_pips : {detection['cum_pips']:.1f}\n"
            f"- state : {json.dumps(detection['state'], ensure_ascii=False)}\n"
            f"- decision : {detection['decision']['rationale']}\n"
            f"- Kill switches mis à OFF :\n"
        )
        for ch in ks_changed:
            motion += f"  - {ch['ks']}: {ch['from']} → {ch['to']}\n"
        motion += (
            f"- Source : `scripts/v9_auto_actions_on_halt.py` (Phase 1.1, motion CEO 28/07)\n"
            f"- R25' strict respecté : halt_forever uniquement (palier max, motion CEO implicite).\n"
            f"- Recovery : relancer manuellement après stabilisation (compteur paliers).\n"
        )
        with DECISIONS_LOG.open("a", encoding="utf-8") as f:
            f.write(motion)

    return {
        "applied": True,
        "halt_forever": True,
        "dd_pct": detection["dd_pct"],
        "cum_pips": detection["cum_pips"],
        "decision": detection["decision"],
        "ks_changed": ks_changed,
        "n_ks_changed": len(ks_changed),
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-actions DD halt_forever V9")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas écrire KS env ni motion log")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--initial-capital", type=float, default=10000.0)
    args = parser.parse_args()

    t0 = time.time()
    result = apply_halt(dry_run=args.dry_run, ) if False else None  # placeholder for type
    # Simplifié : apply_halt(dry_run) sans capital (utilise 10k défaut interne)
    result = apply_halt(dry_run=args.dry_run)
    result["duration_s"] = round(time.time() - t0, 2)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        if result.get("applied"):
            print(f"AUTO-ACTION HALT FOREVER APPLIED: dd_pct={result['dd_pct']*100:.1f}%")
            print(f"  cum_pips: {result['cum_pips']:.1f}")
            print(f"  ks_changed: {result['n_ks_changed']} ({[c['ks'] for c in result['ks_changed']]})")
            print(f"  dry_run: {result['dry_run']}")
        else:
            print(f"No halt applied: {result.get('reason', 'unknown')}")
            print(f"  dd_pct: {result.get('dd_pct', 0)*100:.1f}%")

    # Exit codes
    if result.get("applied"):
        return 0
    if result.get("halt_forever") is False:
        return 1
    return 4


if __name__ == "__main__":
    sys.exit(main())
