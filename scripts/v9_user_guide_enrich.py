"""v9_user_guide_enrich.py — Phase 74 motion CEO 48H.

Auto-enrich user guide avec les derniers modules.
Maintient coherence docs.

Auteur : Hermes (Phase 74 motion CEO 48H non-stop, 31/07/2026)
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.user_guide_enrich")


def list_recent_modules(days: int = 7) -> list[dict]:
    """Liste les modules recents."""
    import time
    cutoff = time.time() - days * 86400
    modules = []
    scripts_dir = _ROOT / "scripts"
    for f in scripts_dir.glob("v9_*.py"):
        mtime = f.stat().st_mtime
        if mtime > cutoff:
            modules.append({
                "name": f.stem,
                "path": str(f),
                "mtime": mtime,
                "category": "script",
            })
    return sorted(modules, key=lambda m: m["mtime"], reverse=True)


def generate_user_guide() -> str:
    """Genere USER_GUIDE.md enrichi."""
    md = []
    md.append("# POWERFLOW V9 — USER GUIDE")
    md.append("")
    md.append(f"Auto-genere le {datetime.date.today().isoformat()}")
    md.append("")
    md.append("## Table des matieres")
    md.append("")
    md.append("1. Quick start")
    md.append("2. Architecture 4 couches")
    md.append("3. Modules")
    md.append("4. Operations")
    md.append("5. Maintenance")
    md.append("6. Doctrine 48H non-stop")
    md.append("")
    md.append("## 1. Quick start")
    md.append("")
    md.append("```bash")
    md.append("# Activer venv")
    md.append("cd C:/projet/V9")
    md.append("source .venv/Scripts/activate")
    md.append("")
    md.append("# Run tests")
    md.append("python -m pytest tests/ -q -m 'not slow' -p no:cacheprovider")
    md.append("")
    md.append("# Lancer dashboard")
    md.append("python scripts/v9_dashboard_enhanced.py")
    md.append("")
    md.append("# Phase 61 - Etat systeme")
    md.append("python scripts/v9_phase_tracker.py --status")
    md.append("")
    md.append("# Phase 64 - Preflight LIVE")
    md.append("python scripts/v9_real_money_preflight.py")
    md.append("```")
    md.append("")
    md.append("## 2. Architecture 4 couches")
    md.append("")
    md.append("```")
    md.append("LECTURE (Daily → M1) → DÉCISION (L1-L17) → OPTIMISATION (Boucle) → EXÉCUTION")
    md.append("```")
    md.append("")
    md.append("## 3. Modules")
    md.append("")
    md.append("### Phase 50-54 — Lecture marché")
    md.append("- `v9_multi_timeframe_reader.py` : 6 TF Daily→M1")
    md.append("- `v9_july_2026_analysis.py` : analyse cloture mensuelle")
    md.append("- `v9_market_anticipation.py` : regime phase + forward projection")
    md.append("- `v9_price_action_context.py` : patterns + S/R")
    md.append("")
    md.append("### Phase 58-60 — Chemin critique")
    md.append("- `v9_mt4_candle_bridge.py` : CSV MT4 → DB candles")
    md.append("- `v9_oos_validator.py` : walk-forward 7 folds")
    md.append("- `v9_robustness_checks.py` : bootstrap + Monte Carlo")
    md.append("")
    md.append("### Phase 61 — Pilote auto-perpetuant")
    md.append("- `v9_phase_tracker.py` : state persistence")
    md.append("- `v9_auto_plan.py` : prochaine phase generator")
    md.append("- `v9_auto_commit.py` : git ops inline")
    md.append("- `v9_autonomous_loop.py` : boucle 48H non-stop")
    md.append("")
    md.append("### Phase 62-66 — Production-grade")
    md.append("- `v9_pipeline_orchestrator.py` : supervisor + DLQ")
    md.append("- `v9_ftmo_compliance.py` : 4% daily + 8% total")
    md.append("- `v9_real_money_preflight.py` : 20+ checks")
    md.append("- `v9_smart_order_router.py` : iceberg + TWAP + VWAP")
    md.append("- `v9_live_metrics.py` : P&L + Greeks + flow")
    md.append("")
    md.append("### Phase 67-72 — Intelligence")
    md.append("- `v9_ml_forecaster.py` : features + scoring")
    md.append("- `v9_performance_persistence.py` : trend tracking")
    md.append("- `v9_cross_pair_correlation.py` : pearson matrix")
    md.append("- `v9_chaos_advanced.py` : partition + latency + loss")
    md.append("- `v9_adversarial_testing.py` : NaN/Inf/zero/extreme")
    md.append("- `v9_e2e_pipeline.py` : integration end-to-end")
    md.append("")
    md.append("## 4. Operations")
    md.append("")
    md.append("### Demarrer la boucle auto-perpetuante")
    md.append("```bash")
    md.append("python scripts/v9_autonomous_loop.py --max-hours 48")
    md.append("```")
    md.append("")
    md.append("### Voir avancement")
    md.append("```bash")
    md.append("python scripts/v9_phase_tracker.py --status")
    md.append("```")
    md.append("")
    md.append("### Cron 48H perfection")
    md.append("```bash")
    md.append("bash scripts/v9_cron_48h.sh")
    md.append("```")
    md.append("")
    md.append("## 5. Maintenance")
    md.append("")
    md.append("### Backup DB")
    md.append("```bash")
    md.append("cp data/v9_forces.db backups/v9_forces_$(date +%Y%m%d).db")
    md.append("```")
    md.append("")
    md.append("### Regenere INDEX")
    md.append("```bash")
    md.append("python scripts/v9_docs_sync.py --sync")
    md.append("```")
    md.append("")
    md.append("## 6. Doctrine 48H non-stop")
    md.append("")
    md.append("Cf. `docs/DOCTRINE_48H_NONSTOP.md` :")
    md.append("- R1 : ZERO confirmation")
    md.append("- R2 : boucle continue")
    md.append("- R3 : state persistence")
    md.append("- R4 : auto-commit inline")
    md.append("- R5 : auto-coherence docs")
    md.append("- R6 : auto-priorite")
    md.append("- R7 : auto-terminate")
    md.append("")
    md.append("---")
    md.append(f"Auto-genere via v9_user_guide_enrich.py")
    return "\n".join(md)


def enrich_user_guide() -> dict:
    """Enrichit USER_GUIDE.md."""
    doc_path = _ROOT / "docs" / "USER_GUIDE.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_user_guide()
    doc_path.write_text(content, encoding="utf-8")
    return {
        "path": str(doc_path),
        "updated": True,
        "size": len(content),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 user guide enrich (Phase 74)",
    )
    parser.add_argument("--enrich", action="store_true")
    parser.add_argument("--recent", action="store_true")
    args = parser.parse_args(argv)

    if args.recent:
        recent = list_recent_modules()
        print(f"Modules recents : {len(recent)}")
        for m in recent[:20]:
            print(f"  {m['name']}")
        return 0

    if args.enrich:
        result = enrich_user_guide()
        print("=" * 70)
        print("V9 USER GUIDE ENRICH")
        print("=" * 70)
        print(f"Path     : {result['path']}")
        print(f"Size     : {result['size']} chars")
        print(f"Updated  : {result['updated']}")
        print("=" * 70)
        return 0

    # Default : enrich
    result = enrich_user_guide()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())
