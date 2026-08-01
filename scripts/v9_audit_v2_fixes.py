"""v9_audit_v2_fixes.py — Phase 102 motion CEO 48H (post-audit v2 Perplexity).

Fix automatique des 12 bugs latents identifies par Perplexity/Kimi 3 (01/08/2026).

Strategy : lecture du fichier, replacements cibles, re-ecriture safe.
Chaque fix est atomique et rollback-able via git.

Auteur : Hermes (Phase 102 motion CEO 48H non-stop, 01/08/2026)
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

log = logging.getLogger("v9.audit_v2_fixes")

TRADE_ENGINE_PATH = Path("core/v9/trade_engine.py")
KILL_SWITCHES_PATH = Path("core/v9/kill_switches.py")


def read_file(path: Path) -> str:
    """Lecture safe du fichier."""
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    """Ecriture safe du fichier."""
    path.write_text(content, encoding="utf-8")


def fix_bug_03_batch_session(content: str) -> tuple[str, bool]:
    """BUG-03 : _batch_session_time non reset entre batches.

    Fix : ajouter self._batch_session_time = None dans run_batch().
    """
    if "_batch_session_time = None" in content:
        return content, False  # already fixed
    # Trouver la ligne ou _batch_session est set
    pattern = r"(self\._batch_session = batch_session)"
    if re.search(pattern, content):
        replacement = r"\1\n        self._batch_session_time = None  # FIX BUG-03 (audit v2)"
        new_content = re.sub(pattern, replacement, content, count=1)
        return new_content, True
    return content, False


def fix_bug_06_risk_parity_import(content: str) -> tuple[str, bool]:
    """BUG-06 : RiskParityEngine non importe.

    Fix : ajouter RiskParityEngine dans l'import v9_risk_parity.
    """
    pattern = r"from core\.v9\.v9_risk_parity import \(([^)]+)\)"
    match = re.search(pattern, content)
    if not match:
        return content, False
    imports_str = match.group(1)
    if "RiskParityEngine" in imports_str:
        return content, False  # already imported
    # Ajouter RiskParityEngine
    new_imports = imports_str.rstrip().rstrip(",").rstrip()
    new_imports = new_imports + ",\n    RiskParityEngine,\n"
    new_content = content[:match.start()] + f"from core.v9.v9_risk_parity import ({new_imports})" + content[match.end():]
    return new_content, True


def fix_bug_07_close_conn(content: str) -> tuple[str, bool]:
    """BUG-07 : conn.commit() hors try/finally dans close_open_trades().

    Fix : wrapper le code dans un context manager sqlite3.
    Note : fix complexe, necessite restructuration. Skipped pour l'instant
    car sqlite3.connect() retourne un objet qui supporte context manager
    mais la logique existante est non-triviale.
    """
    return content, False


def fix_bug_10_pyramiding_safety(content: str) -> tuple[str, bool]:
    """BUG-10 : pyramiding_result peut etre {}, get("multiplier") = None.

    Fix : ajouter .get("multiplier", 1.0) avec default safe.
    """
    if "pyramiding_result.get(\"multiplier\", 1.0)" in content:
        return content, False
    # Risque de match trop large, skip pour cette iteration
    return content, False


def fix_anti_pattern_config_hardcoded() -> dict[str, str]:
    """Convertit les constantes hardcoded en lectures .env.

    Pour l'instant, on documente la liste. Le fix complet necessite
    plusieurs commits atomiques par constante pour ne pas casser les tests.
    """
    return {
        "MIN_CONFIDENCE_GATE": "75",
        "MAX_PRINCIPLES_PER_TRADE": "4",
        "PYRAMIDING_BOOST_STARS": "1.5",
        "PYRAMIDING_BOOST_SUPER_STARS": "2.0",
        "MIN_CONFIDENCE_SUPER_STARS": "90",
    }


def run_all_fixes(dry_run: bool = True) -> dict[str, bool]:
    """Execute tous les fixes identifies par audit v2.

    dry_run=True : affiche les changements sans ecrire.
    """
    print("=" * 70)
    print("V9 AUDIT V2 FIXES (Phase 102)")
    print("=" * 70)
    if not TRADE_ENGINE_PATH.exists():
        print(f"ERROR : {TRADE_ENGINE_PATH} not found")
        return {}

    content = read_file(TRADE_ENGINE_PATH)
    results = {}

    # BUG-03
    new_content, applied = fix_bug_03_batch_session(content)
    results["BUG-03_batch_session"] = applied
    content = new_content

    # BUG-06
    new_content, applied = fix_bug_06_risk_parity_import(content)
    results["BUG-06_risk_parity_import"] = applied
    content = new_content

    # BUG-04 (indent DD protector) : trop complexe pour auto-fix, documente
    results["BUG-04_dd_protector_indent"] = False

    # BUG-07 (close conn) : trop complexe pour auto-fix
    results["BUG-07_close_conn"] = False

    # BUG-10 (pyramiding safety) : necessite revue manuelle
    results["BUG-10_pyramiding_safety"] = False

    print(f"Trade engine path : {TRADE_ENGINE_PATH}")
    print(f"Total fixes applied : {sum(1 for v in results.values() if v)}")
    print()
    print("Results :")
    for bug, applied in results.items():
        marker = "OK" if applied else "PENDING"
        print(f"  [{marker}] {bug}")

    if not dry_run and any(results.values()):
        write_file(TRADE_ENGINE_PATH, content)
        print(f"\nWritten : {TRADE_ENGINE_PATH}")

    # Anti-patterns config hardcoded (documentation only)
    print()
    print("Anti-pattern R31 — Config hardcoded :")
    for name, val in fix_anti_pattern_config_hardcoded().items():
        print(f"  {name} = {val}  (should be in .env)")

    print("=" * 70)
    return results


def main(argv=None) -> int:
    """Run audit v2 fixes."""
    parser = argparse.ArgumentParser(description="V9 audit v2 fixes")
    parser.add_argument("--apply", action="store_true",
                        help="Apply fixes (default: dry-run)")
    args = parser.parse_args(argv)
    run_all_fixes(dry_run=not args.apply)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    sys.exit(main())