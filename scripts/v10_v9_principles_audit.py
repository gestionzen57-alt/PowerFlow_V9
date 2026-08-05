"""V10 V9 Principles Audit — état complet V9 principes vs couverture V10 (Phase R).

Produit un rapport d'état complet : les 47 principes V9 ACTIVE, leur logique,
et la couverture V10 correspondante (module + concept). Identifie les gaps
(concepts V9 non portés) et les doublons (déjà couverts).

R9 honnête : les KPIs catalogue V9 (WR/PnL) sont vérifiés à la source, pas
repris aveuglément (ex. PRICE_LAG_AT_NODE_BIRTH annoncé WR 100% mais en fait
structurellement perdant -805 pips sur 7j). R10 : compute only.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

# Couverture V10 des concepts V9 (module → principes couverts, IDs exacts)
V10_COVERAGE = {
    "v10_market_context_global": ["COALITION_NODE", "GRAMMAR_COALITION",
                                  "GRAMMAR_ANTAGONISME", "GRAMMAR_OPPOSITION"],
    "v10_compression_extension": ["GRAMMAR_EXTENSION", "GRAMMAR_SQUEEZE",
                                   "GRAMMAR_RESPIRATION", "GRAMMAR_LOCK"],
    "v10_regime_hmm": ["GRAMMAR_REGIME"],
    "v10_vsa": ["GRAMMAR_ABSORPTION"],
    "v10_smc": ["GRAMMAR_BREAK"],
    "v10_ict_ote": ["GRAMMAR_PULLBACK"],
    "v10_currency_behavior": ["GRAMMAR_LEADER_FOLLOWER"],
    "v10_grammar_v9": ["GRAMMAR_LEADER_FOLLOWER", "GRAMMAR_PULLBACK",
                       "GRAMMAR_TENSION", "GRAMMAR_RESPIRATION", "GRAMMAR_LOCK",
                       "GRAMMAR_OPPOSITION"],
    "v10_grammar_v9_extra": ["ADAPTIVE_VOL_GATE", "ELASTIC_BREATH",
                            "GRAMMAR_EXHAUSTION", "VELOCITY_CLIMAX_GUARD",
                            "NODE_BIRTH_FAST", "RAW_NODE_BIRTH"],
    "v10_grammar_v9_final": ["GRAMMAR_CONTEXTE", "GRAMMAR_CROISEMENT",
                            "GRAMMAR_CROISEMENT_CONFIRMATION",
                            "GRAVITY_RESPRING_NODE", "POWER_ANGLE_BREAK_TO_PRICE_IMPACT",
                            "SIGNAL_OPEN"],
}


def build_audit() -> dict:
    """Construit l'état complet V9 principes vs couverture V10."""
    from core.v9.principle_engine import load_principles_from_yaml
    principles = load_principles_from_yaml()
    active = [p for p in principles if getattr(p, "v9_status", "") == "ACTIVE"]

    # Carte principe → module V10 (IDs exacts)
    principle_to_module = {}
    for module, pids in V10_COVERAGE.items():
        for pid in pids:
            principle_to_module[pid] = module

    # Concepts délibérément exclus (R9 : structurellement perdants)
    EXCLUDED = {"PRICE_LAG_AT_NODE_BIRTH": "perdant -805p/7j (R9)"}

    rows = []
    covered = 0
    gaps = []
    excluded = []
    for p in active:
        pid = getattr(p, "principle_id", "?")
        kind = getattr(p, "kind", "?")
        origin = getattr(p, "origin", "?")
        v10_module = principle_to_module.get(pid)
        # Les variantes _ADAPTIVE sont couvertes par le concept de base
        if pid.endswith("_ADAPTIVE"):
            base = pid[:-len("_ADAPTIVE")]
            base_module = principle_to_module.get(base)
            if base_module:
                v10_module = base_module
                status = "COVERED_BY_BASE"
                covered += 1
            elif base in EXCLUDED:
                status = "EXCLUDED_R9"
                excluded.append(pid)
            else:
                status = "GAP"
                gaps.append(pid)
        elif pid in EXCLUDED:
            status = "EXCLUDED_R9"
            excluded.append(pid)
        elif v10_module:
            status = "COVERED"
            covered += 1
        else:
            status = "GAP"
            gaps.append(pid)
        rows.append({
            "principle": pid, "kind": kind, "origin": origin,
            "v10_module": v10_module, "status": status,
        })

    return {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "n_principles_total": len(principles),
        "n_active": len(active),
        "n_covered_v10": covered,
        "n_gap": len(gaps),
        "n_excluded_r9": len(excluded),
        "gaps": gaps,
        "excluded_r9": excluded,
        "principles": rows,
        "audit": {
            "r9_honest": "KPIs catalogue V9 vérifiés à la source (PRICE_LAG "
                         "annoncé WR100% mais en fait perdant -805p/7j, exclu)",
            "r10": "compute only",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    report = build_audit()

    date = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y%m%d")
    out_path = Path(args.output) if args.output else \
        ROOT / "reports" / f"v10_v9_principles_audit_{date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    print(f"V9 principes: {report['n_principles_total']} total, "
          f"{report['n_active']} ACTIVE")
    print(f"Couverture V10: {report['n_covered_v10']} couverts, "
          f"{report['n_gap']} gaps")
    if report["gaps"]:
        print("Gaps (concepts V9 non portés):")
        for g in report["gaps"]:
            print(f"  - {g}")
    log.info("Rapport audit écrit: %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
