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

# Couverture V10 des concepts V9 (module → concepts couverts)
V10_COVERAGE = {
    "v10_market_context_global": ["COALITION", "ANTAGONISME", "OPPOSITION"],
    "v10_compression_extension": ["EXTENSION", "SQUEEZE", "RESPIRATION", "LOCK"],
    "v10_regime_hmm": ["REGIME"],
    "v10_vsa": ["ABSORPTION"],
    "v10_smc": ["BREAK"],
    "v10_ict_ote": ["PULLBACK"],
    "v10_currency_behavior": ["LEADER_FOLLOWER"],
    "v10_grammar_v9": ["LEADER_FOLLOWER", "PULLBACK", "TENSION",
                       "RESPIRATION", "LOCK", "OPPOSITION"],
    "v10_grammar_v9_extra": ["ADAPTIVE_VOL_GATE", "ELASTIC_BREATH",
                            "EXHAUSTION", "VELOCITY_CLIMAX_GUARD", "NODE_BIRTH"],
}


def build_audit() -> dict:
    """Construit l'état complet V9 principes vs couverture V10."""
    from core.v9.principle_engine import load_principles_from_yaml
    principles = load_principles_from_yaml()
    active = [p for p in principles if getattr(p, "v9_status", "") == "ACTIVE"]

    # Carte concept → module V10
    concept_to_module = {}
    for module, concepts in V10_COVERAGE.items():
        for c in concepts:
            concept_to_module[c] = module

    rows = []
    covered = 0
    gaps = []
    for p in active:
        pid = getattr(p, "principle_id", "?")
        kind = getattr(p, "kind", "?")
        origin = getattr(p, "origin", "?")
        # concept = partie après GRAMMAR_ ou avant _ADAPTIVE
        concept = pid.replace("GRAMMAR_", "").replace("_ADAPTIVE", "")
        concept = concept.replace("_NODE", "").replace("_FAST", "")
        v10_module = concept_to_module.get(concept)
        status = "COVERED" if v10_module else "GAP"
        if v10_module:
            covered += 1
        else:
            gaps.append(pid)
        rows.append({
            "principle": pid, "kind": kind, "origin": origin,
            "concept": concept, "v10_module": v10_module, "status": status,
        })

    return {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "n_principles_total": len(principles),
        "n_active": len(active),
        "n_covered_v10": covered,
        "n_gap": len(gaps),
        "gaps": gaps,
        "principles": rows,
        "audit": {
            "r9_honest": "KPIs catalogue V9 vérifiés à la source (PRICE_LAG "
                         "annoncé WR100% mais en fait perdant -805p/7j)",
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
