"""
scripts/run_exports_audit.py
H9 — Audit des exports core/v10/__init__.py
Génère exports_audit.json : {module, exported, referenced_in_orchestrator}
"""
from __future__ import annotations
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT_PATH    = ROOT / "core" / "v10" / "__init__.py"
ORCH_PATH    = ROOT / "core" / "v10" / "v10_orchestrator.py"
MODULES_DIR  = ROOT / "core" / "v10"

# Critical modules that MUST be exported
CRITICAL = [
    "v10_perplexity_sigma_oracle",
    "v10_behavior_rag",
    "v10_net_exposure",
    "v10_rl_promotion",
    "v10_fatman_wave_predictor",
]


def parse_init_exports(init_path: Path) -> set[str]:
    """Return set of module names imported in __init__.py."""
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    exported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                # e.g. from .v10_signal_engine import ...
                mod = node.module.lstrip(".")
                exported.add(mod)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    exported.add(alias.name.split(".")[-1])
    return exported


def parse_orchestrator_refs(orch_path: Path) -> set[str]:
    """Return set of v10_* module names referenced in orchestrator."""
    if not orch_path.exists():
        return set()
    source = orch_path.read_text(encoding="utf-8")
    refs: set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if "import" in stripped:
            for token in stripped.split():
                if token.startswith("v10_"):
                    refs.add(token.rstrip(","))
    return refs


def audit() -> list[dict]:
    exported = parse_init_exports(INIT_PATH)
    orch_refs = parse_orchestrator_refs(ORCH_PATH)
    all_modules = sorted(
        p.stem for p in MODULES_DIR.glob("v10_*.py") if p.is_file()
    )

    report = []
    for mod in all_modules:
        is_exported = mod in exported
        in_orch = mod in orch_refs
        is_critical = mod in CRITICAL
        is_legacy = "legacy" in mod or "deprecated" in mod
        report.append({
            "module": mod,
            "exported": is_exported,
            "referenced_in_orchestrator": in_orch,
            "critical": is_critical,
            "legacy_candidate": is_legacy,
            "action_needed": (
                "ADD_TO_INIT" if (is_critical and not is_exported) else
                "REVIEW_LEGACY" if is_legacy else
                "ORPHAN" if (not is_exported and not in_orch) else
                "OK"
            ),
        })
    return report


def main():
    report = audit()
    out_path = ROOT / "exports_audit.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n📋 Exports Audit — {len(report)} modules scanned")
    print("-" * 60)
    issues = [r for r in report if r["action_needed"] != "OK"]
    for r in issues:
        icon = "🔴" if r["critical"] else "🟠" if r["legacy_candidate"] else "🟡"
        print(f"{icon} {r['module']:50s} → {r['action_needed']}")
    if not issues:
        print("✅ All modules clean — no action needed.")
    print(f"\nFull report saved to: {out_path}")


if __name__ == "__main__":
    main()
