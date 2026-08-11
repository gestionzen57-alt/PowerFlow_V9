"""Z4 — Grammar Audit Script (fix 11/08/2026).

Audit canonique du pipeline grammar V10 :
  - Vérifie que chaque concept grammar réel (v10_grammar_v9, _extra, _final)
    est détectable avec des paramètres déclenchants (R6 fail-open)
  - Produit un rapport JSON horodaté (R9)
  - Zéro ordre réel (R10)

Fix Z4-FIX-5 (11/08) : la v1 importait des modules fantômes
(v10_grammar_canonical / v10_grammar_validator — jamais existés) → fail-open
assumait OK → faux PASS 100% (assumed_ok_modules_absent). L'audit est
désormais branché sur les 3 modules grammar réels et leurs fonctions pures.

Usage :
  python scripts/run_grammar_audit.py
  python scripts/run_grammar_audit.py --verbose
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORTS_DIR = ROOT / "reports"
COVERAGE_TARGET = 0.80  # 80% couverture minimum

# ── Concepts grammar canoniques V10 (référence C22) ──────────────────
# Chaque concept = fonction pure réelle dans core/v10/v10_grammar_v9*.py
CANONICAL_PATTERNS: list[str] = [
    # v10_grammar_v9.py (canonique)
    "LEADER_FOLLOWER",
    "PULLBACK",
    "TENSION",
    "RESPIRATION",
    "LOCK",
    "OPPOSITION",
    # v10_grammar_v9_extra.py
    "ADAPTIVE_VOL_GATE",
    "ELASTIC_BREATH",
    "EXHAUSTION",
    "VELOCITY_CLIMAX_GUARD",
    "NODE_BIRTH",
    # v10_grammar_v9_final.py
    "CONTEXTE",
    "CROISEMENT",
    "CROISEMENT_CONFIRMATION",
    "GRAVITY_RESPRING",
    "POWER_ANGLE_BREAK",
    "RAW_NODE_BIRTH",
    "SIGNAL_OPEN",
]

# ── Import guards (R6 fail-open) ────────────────────────────────────
try:
    from core.v10.v10_grammar_v9 import (  # noqa: F401
        leader_follower,
        lock,
        opposition,
        pullback,
        respiration,
        tension,
    )
    _GRAMMAR_V9_OK = True
except Exception as _e:
    log.warning("[Z4] v10_grammar_v9 import KO (fail-open): %s", _e)
    _GRAMMAR_V9_OK = False

try:
    from core.v10.v10_grammar_v9_extra import (  # noqa: F401
        adaptive_vol_gate,
        elastic_breath,
        exhaustion,
        node_birth,
        velocity_climax_guard,
    )
    _GRAMMAR_EXTRA_OK = True
except Exception as _e:
    log.warning("[Z4] v10_grammar_v9_extra import KO (fail-open): %s", _e)
    _GRAMMAR_EXTRA_OK = False

try:
    from core.v10.v10_grammar_v9_final import (  # noqa: F401
        contexte,
        croisement,
        croisement_confirmation,
        gravity_respring,
        power_angle_break,
        raw_node_birth,
        signal_open,
    )
    _GRAMMAR_FINAL_OK = True
except Exception as _e:
    log.warning("[Z4] v10_grammar_v9_final import KO (fail-open): %s", _e)
    _GRAMMAR_FINAL_OK = False


# ── Cas de test par concept (paramètres déclenchants) ───────────────
# Chaque entrée : (concept, callable, kwargs déclenchants)
def _cases() -> list[tuple[str, Callable, dict]]:
    return [
        # v10_grammar_v9.py
        ("LEADER_FOLLOWER", leader_follower,
         {"regime_name": "MARKUP", "leader": "USD", "follower": "EUR"}),
        ("PULLBACK", pullback,
         {"regime_name": "MARKUP", "bascule_detectee": True,
          "bascule_intensite": 0.7, "trend_direction": "UP"}),
        ("TENSION", tension,
         {"pliure_detectee": True, "tension_score": 1.2, "pente": 0.5}),
        ("RESPIRATION", respiration,
         {"zone_type": "respiration", "compression_etat": "compression"}),
        ("LOCK", lock,
         {"compression_etat": "compression", "zone_type": "respiration"}),
        ("OPPOSITION", opposition,
         {"antagonismes_count": 3, "bascule_intensite": 20.0}),
        # v10_grammar_v9_extra.py
        ("ADAPTIVE_VOL_GATE", adaptive_vol_gate,
         {"vol_regime": "HIGH", "baseline_ok": True}),
        ("ELASTIC_BREATH", elastic_breath,
         {"state": "ACCUMULATING", "absorbed_pullbacks": 2}),
        ("EXHAUSTION", exhaustion,
         {"z_current": 2.5, "state": "EARLY_EXTREME"}),
        ("VELOCITY_CLIMAX_GUARD", velocity_climax_guard,
         {"velocite_moyenne": 0.12, "session_marche": True}),
        ("NODE_BIRTH", node_birth,
         {"state": "ACCUMULATING"}),
        # v10_grammar_v9_final.py
        ("CONTEXTE", contexte,
         {"marche_ouvert": True, "session_marche": True}),
        ("CROISEMENT", croisement,
         {"bascule_detectee": True, "bascule_devise_dominante": "USD"}),
        ("CROISEMENT_CONFIRMATION", croisement_confirmation,
         {"croisement_detecte": True, "vitesse": 0.9}),
        ("GRAVITY_RESPRING", gravity_respring,
         {"state": "ACCUMULATING", "prev_state": "MARKDOWN"}),
        ("POWER_ANGLE_BREAK", power_angle_break,
         {"state": "RUPTURE", "tension_score": 1.2}),
        ("RAW_NODE_BIRTH", raw_node_birth,
         {"prev_state": "NEUTRAL", "state": "ACCUMULATING"}),
        ("SIGNAL_OPEN", signal_open,
         {"window_statut": "ouverte", "confiance_qualification": 80}),
    ]


def _audit_patterns() -> dict:
    """Vérifie la détection de chaque concept canonique (R6 fail-open)."""
    results = {}
    for concept, fn, kwargs in _cases():
        ok = False
        reason = "not_tested"
        try:
            g = fn(**kwargs)
            ok = bool(getattr(g, "detected", False))
            reason = "detected" if ok else "not_detected"
        except Exception as exc:
            reason = f"grammar_error: {exc}"
        results[concept] = {"ok": ok, "reason": reason}
    return results


def run_grammar_audit(verbose: bool = False) -> dict:
    """Lance l'audit grammar et retourne le rapport."""
    ts = datetime.now(UTC).isoformat()
    pattern_results = _audit_patterns()

    total = len(pattern_results)
    passed = sum(1 for v in pattern_results.values() if v["ok"])
    coverage = round(passed / total, 4) if total > 0 else 0.0
    status = "PASS" if coverage >= COVERAGE_TARGET else "FAIL"

    report = {
        "generated_at": ts,
        "grammar_version": "C22",
        "total_patterns": total,
        "patterns_ok": passed,
        "coverage": coverage,
        "coverage_target": COVERAGE_TARGET,
        "status": status,
        "modules_active": {
            "grammar_v9": _GRAMMAR_V9_OK,
            "grammar_v9_extra": _GRAMMAR_EXTRA_OK,
            "grammar_v9_final": _GRAMMAR_FINAL_OK,
        },
        "patterns": pattern_results,
        "r10": "compute only, zero order real",
    }

    if verbose:
        print(json.dumps(report, indent=2))
    else:
        print(f"[Z4] Grammar audit: {status} — {passed}/{total} patterns ({coverage*100:.1f}% coverage)")

    # Sauvegarde R9
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts_file = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = REPORTS_DIR / f"grammar_audit_{ts_file}.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log.debug("[Z4] rapport sauvegardé : %s", path)
    except Exception as exc:
        log.warning("[Z4] sauvegarde rapport échouée (R6): %s", exc)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Z4 — Grammar Audit V10")
    parser.add_argument("--verbose", action="store_true", help="Rapport JSON complet")
    args = parser.parse_args()

    report = run_grammar_audit(verbose=args.verbose)
    coverage = report.get("coverage", 0)
    status = report.get("status", "FAIL")

    # Exit code différencié
    if status == "PASS":
        print(f"✅ Grammar PASS — {coverage*100:.1f}% coverage ≥ {COVERAGE_TARGET*100:.0f}%")
        sys.exit(0)
    else:
        print(f"❌ Grammar FAIL — {coverage*100:.1f}% coverage < {COVERAGE_TARGET*100:.0f}%")
        sys.exit(1)


if __name__ == "__main__":
    main()
