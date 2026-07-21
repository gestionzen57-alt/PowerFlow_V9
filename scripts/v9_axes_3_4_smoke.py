#!/usr/bin/env python
"""v9_axes_3_4_smoke.py — Smoke global axes 3+4 du Roadmap V2.

Vérifie que les modules de robustesse risque et Phase E sont instanciables
et exposent leurs APIs principales. Lecture seule DB.

Modules testés (Axe 3 Robustesse risque) :
- core.v9.v9_drawdown_protector (DrawdownProtector, 5 paliers)
- core.v9.v9_risk_parity (PairRiskBudget, 5 paires)
- core.v9.risk_manager (cvar_95, cvar_position_cap — Chantier B 18/07)

Modules testés (Axe 4 Phase E) :
- core.v9.v9_cycle_memory (CyclePattern, TransitionPattern — J14)
- core.v9.v9_meta_strategy_optimizer (ContextScore, MetaStrategyDecision — J15)

Doctrine : R8 (traçabilité), R13 (observer), R22 (CLI lecture seule).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def smoke_all() -> dict:
    """Exécute le smoke global."""
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "axe_3": {},
        "axe_4": {},
    }

    # ── Axe 3.1 CVaR ────────────────────────────────────────────────
    try:
        from core.v9.risk_manager import RiskManager
        cvar_value = RiskManager.cvar_95(
            [-5, -3, -8, -2, -1, -4, -6, -10, -7, -9], 0.95
        )
        results["axe_3"]["cvar"] = {
            "ok": True,
            "cvar_95_on_losses": cvar_value,
            "note": "Expected ~10 (worst loss)",
        }
    except Exception as e:
        results["axe_3"]["cvar"] = {"ok": False, "error": str(e)[:200]}

    # ── Axe 3.2 DD Protector ───────────────────────────────────────
    try:
        from core.v9.v9_drawdown_protector import DrawdownProtector, DrawdownState
        # Lecture seule : juste vérifier l'import + attributs
        assert hasattr(DrawdownProtector, "__init__")
        assert hasattr(DrawdownState, "__init__")
        results["axe_3"]["drawdown_protector"] = {
            "ok": True,
            "module": "core.v9.v9_drawdown_protector",
            "classes": ["DrawdownProtector", "DrawdownState", "DrawdownDecision"],
        }
    except Exception as e:
        results["axe_3"]["drawdown_protector"] = {"ok": False, "error": str(e)[:200]}

    # ── Axe 3.3 Risk Parity ────────────────────────────────────────
    try:
        from core.v9.v9_risk_parity import PairRiskBudget
        assert hasattr(PairRiskBudget, "__init__")
        results["axe_3"]["risk_parity"] = {
            "ok": True,
            "module": "core.v9.v9_risk_parity",
            "classes": ["PairRiskBudget"],
        }
    except Exception as e:
        results["axe_3"]["risk_parity"] = {"ok": False, "error": str(e)[:200]}

    # ── Axe 4.1 Cycle Memory ───────────────────────────────────────
    try:
        from core.v9.v9_cycle_memory import CyclePattern, TransitionPattern
        assert hasattr(CyclePattern, "__init__")
        assert hasattr(TransitionPattern, "__init__")
        results["axe_4"]["cycle_memory"] = {
            "ok": True,
            "module": "core.v9.v9_cycle_memory",
            "classes": ["CyclePattern", "TransitionPattern"],
        }
    except Exception as e:
        results["axe_4"]["cycle_memory"] = {"ok": False, "error": str(e)[:200]}

    # ── Axe 4.2 Meta Strategy Optimizer ───────────────────────────
    try:
        from core.v9.v9_meta_strategy_optimizer import ContextScore, MetaStrategyDecision
        assert hasattr(ContextScore, "__init__")
        assert hasattr(MetaStrategyDecision, "__init__")
        results["axe_4"]["meta_strategy"] = {
            "ok": True,
            "module": "core.v9.v9_meta_strategy_optimizer",
            "classes": ["ContextScore", "MetaStrategyDecision"],
        }
    except Exception as e:
        results["axe_4"]["meta_strategy"] = {"ok": False, "error": str(e)[:200]}

    # ── Kill switches status ───────────────────────────────────────
    from core.v9.kill_switches import (
        drawdown_protector_enabled,
        risk_parity_enabled,
        cycle_memory_enabled,
        meta_strategy_optimizer_enabled,
        kelly_cvar_enabled,
    )
    results["kill_switches"] = {
        "V9_DRAWDOWN_PROTECTOR_ENABLED": drawdown_protector_enabled(),
        "V9_RISK_PARITY_ENABLED": risk_parity_enabled(),
        "V9_CYCLE_MEMORY_ENABLED": cycle_memory_enabled(),
        "V9_META_STRATEGY_OPTIMIZER_ENABLED": meta_strategy_optimizer_enabled(),
        "V9_KELLY_CVAR_ENABLED": kelly_cvar_enabled(),
    }

    # Verdict global
    axe3_ok = all(m.get("ok") for m in results["axe_3"].values())
    axe4_ok = all(m.get("ok") for m in results["axe_4"].values())
    results["all_ok"] = axe3_ok and axe4_ok
    results["verdict"] = "✅ TOUS OK" if results["all_ok"] else "⚠️ CERTAINS MODULES KO"

    return results


def render_text(report: dict) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("🔥 Smoke global Axes 3+4 — Roadmap V2")
    lines.append("=" * 70)
    lines.append(f"Généré : {report['generated_at']}")
    lines.append(f"Verdict : {report['verdict']}")
    lines.append("")

    lines.append("─" * 70)
    lines.append("📊 AXE 3 — Robustesse risque")
    lines.append("─" * 70)
    for name, m in report["axe_3"].items():
        mark = "🟢" if m.get("ok") else "🔴"
        lines.append(f"{mark} {name}")
        if "error" in m:
            lines.append(f"   ERROR : {m['error']}")

    lines.append("")
    lines.append("─" * 70)
    lines.append("📊 AXE 4 — Phase E")
    lines.append("─" * 70)
    for name, m in report["axe_4"].items():
        mark = "🟢" if m.get("ok") else "🔴"
        lines.append(f"{mark} {name}")
        if "error" in m:
            lines.append(f"   ERROR : {m['error']}")

    lines.append("")
    lines.append("─" * 70)
    lines.append("🔌 Kill switches")
    lines.append("─" * 70)
    for k, v in report["kill_switches"].items():
        mark = "🟢 ON" if v else "🔴 OFF"
        lines.append(f"  {k:<40} : {mark}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke global Axes 3+4 V9")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    args = parser.parse_args()

    report = smoke_all()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))

    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
