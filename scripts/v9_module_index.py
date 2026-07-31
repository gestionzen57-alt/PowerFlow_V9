"""v9_module_index.py — Phase 35 motion CEO 48h autopilote.

Genere un index structure de tous les scripts et modules V9.
Output : docs/INDEX_MODULES.md (auto-genere)

Auteur : Hermes (Phase 35 motion CEO 48h, 31/07/2026)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("v9.module_index")

INDEX_PATH = Path(r"C:\projet\V9\docs\INDEX_MODULES.md")


def extract_docstring(path: Path) -> str:
    """Extrait la premiere ligne du docstring."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r'"""([^"\n]+)', content[:500])
        return match.group(1).strip() if match else "(no docstring)"
    except Exception:
        return "(read error)"


def extract_cli_info(path: Path) -> str:
    """Extrait info CLI (argparse description)."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        # Cherche argparse.ArgumentParser(description=...)
        match = re.search(
            r'ArgumentParser\(\s*(?:description=)?\s*[\'"]([^\'"]+)[\'"]',
            content,
        )
        if match:
            return match.group(1).strip()
        # Cherche description=...
        match = re.search(r'description=["\']([^"\']+)["\']', content)
        if match:
            return match.group(1).strip()
        return ""
    except Exception:
        return ""


def has_tests(path: Path, tests_dir: Path) -> bool:
    """Verifie si un test existe pour ce module."""
    test_name = f"test_{path.stem}.py"
    return (tests_dir / test_name).exists()


def generate_index(scripts_dir: Path, tests_dir: Path,
                    output_path: Path) -> dict:
    """Genere l'index complet."""
    if not scripts_dir.exists():
        return {"error": "scripts_dir_missing"}
    modules = []
    for script in sorted(scripts_dir.glob("v9_*.py")):
        test_exists = has_tests(script, tests_dir)
        test_name = f"test_{script.stem}.py"
        modules.append({
            "name": script.stem,
            "path": str(script.relative_to(_ROOT)),
            "docstring": extract_docstring(script),
            "cli_description": extract_cli_info(script),
            "test_exists": test_exists,
            "test_name": test_name if test_exists else "",
            "size_lines": sum(1 for _ in script.open(encoding="utf-8", errors="ignore")),
        })

    # Generer markdown
    lines = []
    lines.append("# V9 — INDEX DES MODULES")
    lines.append("")
    lines.append(f"**Genere le** : {datetime.now(timezone.utc).isoformat()[:19]}")
    lines.append(f"**N modules** : {len(modules)}")
    lines.append(f"**Avec tests** : {sum(1 for m in modules if m['test_exists'])}")
    lines.append("")

    # Par categorie
    categories = {
        "Quantique": ["monte_carlo", "kelly_criterion", "bayesian_posterior",
                       "walk_forward_monte_carlo", "expectancy_comparison",
                       "hurst_exponent", "var_live", "dd_recovery",
                       "kelly_uncertainty", "feature_importance",
                       "regime_detector"],
        "Operations": ["quick_audit", "status_dashboard", "auto_rollback",
                        "daily_paper_audit", "paper_runner", "post_mortem",
                        "self_improving_loop", "perf_profiler",
                        "alert_engine", "stress_test"],
        "LIVE motion": ["token_auto_setup", "token_rotation",
                         "paper_runner_continuous", "log_human_trade",
                         "mirror_auto_activate", "mirror_check",
                         "check_orderbridge", "pre_live_check"],
        "Reporting": ["daily_summary", "trade_journal", "edge_momentum",
                       "paper_performance", "mega_edge_optimizer",
                       "win_streak"],
        "Phase 14+": ["heartbeat_capture", "principle_audit",
                       "spread_simulator", "boot_alerts", "cron_pipeline",
                       "close_time_exit", "walk_forward", "auto_promote_stars"],
        "Autres": [],  # fallback
    }

    # Classer les modules
    by_category = {cat: [] for cat in categories}
    for m in modules:
        categorized = False
        for cat, keywords in categories.items():
            if cat == "Autres":
                continue
            if any(kw in m["name"] for kw in keywords):
                by_category[cat].append(m)
                categorized = True
                break
        if not categorized:
            by_category["Autres"].append(m)

    for cat, mods in by_category.items():
        lines.append(f"## {cat} ({len(mods)} modules)")
        lines.append("")
        if not mods:
            lines.append("_Aucun module._")
            lines.append("")
            continue
        lines.append("| Module | Description | CLI | Tests |")
        lines.append("|---|---|:---:|:---:|")
        for m in mods:
            cli = m["cli_description"][:60] if m["cli_description"] else "—"
            test_status = "✓" if m["test_exists"] else "✗"
            docstring = m["docstring"][:80].replace("|", "\\|")
            lines.append(
                f"| `{m['name']}.py` | {docstring} | {cli} | {test_status} |"
            )
        lines.append("")

    # Statistiques
    lines.append("## STATISTIQUES")
    lines.append("")
    total_lines = sum(m["size_lines"] for m in modules)
    lines.append(f"- **Total modules** : {len(modules)}")
    lines.append(f"- **Avec tests** : {sum(1 for m in modules if m['test_exists'])}")
    lines.append(f"- **Sans tests** : {sum(1 for m in modules if not m['test_exists'])}")
    lines.append(f"- **Total lignes** : {total_lines}")
    lines.append(f"- **Lignes / module (moyenne)** : "
                  f"{total_lines // max(len(modules), 1)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "n_modules": len(modules),
        "n_with_tests": sum(1 for m in modules if m["test_exists"]),
        "total_lines": total_lines,
        "output_path": str(output_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 module index generator (Phase 35)",
    )
    args = parser.parse_args(argv)
    scripts_dir = _ROOT / "scripts"
    tests_dir = _ROOT / "tests"
    result = generate_index(scripts_dir, tests_dir, INDEX_PATH)
    print("=" * 70)
    print("PHASE 35 — MODULE INDEX GENERATOR")
    print("=" * 70)
    print(f"N modules       : {result.get('n_modules', 0)}")
    print(f"Avec tests      : {result.get('n_with_tests', 0)}")
    print(f"Total lignes    : {result.get('total_lines', 0)}")
    print(f"Sortie          : {result.get('output_path', '')}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())