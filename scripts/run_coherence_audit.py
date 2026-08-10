#!/usr/bin/env python3
"""run_coherence_audit.py — Audit de cohérence V10 (Z8, 2026-08-10).

Produit `reports/coherence_audit_<date>.json` avec :
  - orphans        : modules de lecture orphelins (consommés par personne)
  - wired          : modules de lecture branchés (avec leurs consommateurs)
  - n_orphans / n_wired / verdict
  - recommendations : plan d'action par module (WIRE / DEFER / DONE)
  - meta           : R6 fail-open, R9 traçabilité, R10 compute only

Réutilise le moteur `audit_orphans()` de core/v10/v10_coherence_audit.py
(Phase 4, Cognitive Continuum) — R2 additif, aucune modification de la
logique existante.

Usage :
    python scripts/run_coherence_audit.py            # console
    python scripts/run_coherence_audit.py --json     # JSON seul
    python scripts/run_coherence_audit.py --report   # écrit le rapport fichier

Exit codes : 0 = COHERENT, 1 = ORPHANS_DETECTED.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v10.v10_coherence_audit import audit_orphans  # noqa: E402

REPORTS_DIR = ROOT_DIR / "reports"

# ─────────────────────────────────────────────────────────────────────
# Plan d'action par module (Z8 — recommandations statiques, révisées
# à chaque session ; la vérité runtime est dans `wired`/`orphans`).
# ─────────────────────────────────────────────────────────────────────
RECOMMENDATIONS = {
    "v10_compression_extension": "WIRE — VSA multi-TF utile pour H8 quality gate "
                                 "(compute_vsa_signal branché dans le pipeline Z9)",
    "v10_memory_bridge": "WIRE — recall_patterns() utile pour WFA",
    "v10_behavior_registry": "DEFER — logging comportemental futur",
    "v10_cortex": "WIRE — decide() peut remplacer bridge_decide dans replay",
    "v10_fatman_bible_signals": "DONE — 6 signaux branchés orchestrateur/replay (Z11: Signal 7)",
    "v10_delta_flow": "DONE — connecté via cortex",
}


def _recommendation_for(mod: str) -> str:
    return RECOMMENDATIONS.get(
        mod,
        "REVUE — vérifier l'intention de branchement de ce module",
    )


def build_audit() -> dict:
    """Assemble le rapport complet (R6 : échec → audit vide fail-open)."""
    report: dict = {
        "report": "coherence_audit",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "core.v10.v10_coherence_audit.audit_orphans()",
        "doctrine": {"r6": "fail-open", "r9": "audit traçable", "r10": "compute only"},
    }
    try:
        res = audit_orphans()
        orphans = list(res.get("orphans", []))
        wired = [
            {"module": c["module"], "consumers": list(c.get("consumers", []))}
            for c in res.get("connected", [])
        ]
        report["orphans"] = sorted(orphans)
        report["n_orphans"] = len(orphans)
        report["wired"] = wired
        report["n_wired"] = len(wired)
        report["verdict"] = "COHERENT" if not orphans else "ORPHANS_DETECTED"
        report["recommendations"] = {
            m: {"status": "WIRE" if m in orphans else "OK", "plan": _recommendation_for(m)}
            for m in sorted(set(orphans) | set(RECOMMENDATIONS))
        }
        report["meta"] = {
            "error": None,
            "modules_scanned": res.get("n_connected", 0) + len(orphans),
        }
    except Exception as exc:  # R6 fail-open
        report["orphans"] = []
        report["wired"] = []
        report["n_orphans"] = 0
        report["n_wired"] = 0
        report["verdict"] = "AUDIT_ERROR"
        report["recommendations"] = {}
        report["meta"] = {"error": f"{type(exc).__name__}: {exc}"}
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit de cohérence V10 (Z8)")
    ap.add_argument("--json", action="store_true", help="sortie JSON seule")
    ap.add_argument("--report", action="store_true", help="écrit reports/coherence_audit_<date>.json")
    args = ap.parse_args()

    report = build_audit()

    if args.report:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        # Nom exact exigé par la spec Z8 : coherence_audit_<YYYY_MM_DD>.json
        stamp = report["date"].replace("-", "_")
        out_path = REPORTS_DIR / f"coherence_audit_{stamp}.json"
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"[run_coherence_audit] rapport écrit : {out_path}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"verdict        : {report['verdict']}")
        print(f"n_orphans      : {report['n_orphans']}")
        print(f"n_wired        : {report['n_wired']}")
        print(f"orphans        : {report['orphans']}")
        for rec in sorted(report.get("recommendations", {})):
            r = report["recommendations"][rec]
            print(f"  {rec:<32} [{r['status']}] {r['plan']}")

    return 0 if report["verdict"] == "COHERENT" else 1


if __name__ == "__main__":
    sys.exit(main())
