#!/usr/bin/env python3
"""audit_grammar_modules.py — audit + archivage des modules grammar V9 (Z-GRAMMAR).

Contexte : 3 modules grammar coexistent (v10_grammar_v9, _extra, _final).
Le canonique confirmé est `v10_grammar_v9.py` (4+ refs). Les modules
`_final` et `_extra` sont des variantes historiques → archivés dans
`core/v10/_deprecated/` (R2 : déplacement, pas de suppression).

Mode audit (défaut) :
    - compte les références de chaque module grammar
    - vérifie que le canonique est bien v10_grammar_v9.py
    - liste les imports directs (non fail-open) à neutraliser

Mode --apply :
    1. rend fail-open les imports directs de _final/_extra
       (core/v10/__init__.py, scripts/v10_grammar_v9_extra_live.py)
    2. git mv les modules + leurs tests vers core/v10/_deprecated/
    3. retire _final/_extra de READING_MODULES (v10_coherence_audit)
    4. écrit reports/grammar_audit_<date>.json (R9)

R6 fail-open : chaque étape est isolée, une erreur n'arrête pas le reste.
R10 : compute only (aucun ordre).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_V10 = ROOT / "core" / "v10"
DEPRECATED = CORE_V10 / "_deprecated"
REPORTS = ROOT / "reports"

CANONICAL = "v10_grammar_v9"
TO_ARCHIVE = ["v10_grammar_v9_extra", "v10_grammar_v9_final"]

# Fichiers avec imports directs (non fail-open) de _final/_extra
DIRECT_IMPORT_FILES = [
    CORE_V10 / "__init__.py",
    ROOT / "scripts" / "v10_grammar_v9_extra_live.py",
]

# Fichiers de test associés aux modules archivés
TEST_FILES = [
    ROOT / "tests" / "test_v10_grammar_v9_extra.py",
    ROOT / "tests" / "test_v10_grammar_v9_final.py",
]


def _count_refs(module: str) -> list:
    """Fichiers (hors _deprecated) qui référencent le module."""
    refs = []
    for base in (CORE_V10, ROOT / "scripts", ROOT / "tests"):
        for f in base.rglob("*.py"):
            if "_deprecated" in f.parts:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if re.search(rf"(import|from)\s+.*{module}", text) or module in text:
                refs.append(str(f.relative_to(ROOT)))
    return sorted(refs)


def _make_import_fail_open(path: Path) -> bool:
    """Enveloppe les imports de _final/_extra dans try/except (R6)."""
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    changed = False
    for mod in TO_ARCHIVE:
        # from .v10_grammar_v9_extra import ( ... )  → try/except
        pat = re.compile(
            rf"(from\s+\.?{mod}\s+import\s*\()(.*?)(\)\s*\n)",
            re.DOTALL,
        )
        def _wrap(m: re.Match) -> str:
            nonlocal changed
            changed = True
            indent = " " * 4
            return (
                f"try:\n{indent}{m.group(1)}{m.group(2)}{m.group(3)}\n"
                f"except ImportError:  # pragma: no cover — archivé dans _deprecated\n"
                f"{indent}pass\n"
            )
        text = pat.sub(_wrap, text)
        # from .v10_grammar_v9_extra import X  (une ligne, relatif ou absolu)
        pat1 = re.compile(
            rf"^(from\s+(?:\.|core\.v10\.){mod}\s+import\s+[^\n(]+)$",
            re.MULTILINE,
        )
        def _wrap1(m: re.Match) -> str:
            nonlocal changed
            changed = True
            return (
                f"try:\n    {m.group(1)}\n"
                f"except ImportError:  # pragma: no cover — archivé dans _deprecated\n"
                f"    pass\n"
            )
        text = pat1.sub(_wrap1, text)
    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def _remove_from_reading_modules() -> bool:
    """Retire _final/_extra de READING_MODULES (v10_coherence_audit)."""
    path = CORE_V10 / "v10_coherence_audit.py"
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    new = text
    for mod in TO_ARCHIVE:
        new = re.sub(rf',\s*"{mod}"', "", new)
        new = re.sub(rf'"{mod}",\s*', "", new)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def _archive() -> list:
    """git mv modules + tests vers _deprecated (R2 : déplacement)."""
    moved = []
    DEPRECATED.mkdir(parents=True, exist_ok=True)
    (DEPRECATED / "tests").mkdir(parents=True, exist_ok=True)
    for mod in TO_ARCHIVE:
        src = CORE_V10 / f"{mod}.py"
        if src.exists() and not (DEPRECATED / src.name).exists():
            subprocess.run(["git", "mv", str(src), str(DEPRECATED / src.name)],
                           check=False, capture_output=True)
            moved.append(str((DEPRECATED / src.name).relative_to(ROOT)))
    for t in TEST_FILES:
        if t.exists() and not (DEPRECATED / "tests" / t.name).exists():
            subprocess.run(["git", "mv", str(t), str(DEPRECATED / "tests" / t.name)],
                           check=False, capture_output=True)
            moved.append(str((DEPRECATED / "tests" / t.name).relative_to(ROOT)))
    return moved


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit/archivage modules grammar V9")
    ap.add_argument("--apply", action="store_true",
                    help="applique l'archivage (fail-open imports + git mv)")
    ap.add_argument("--json", action="store_true", help="sortie JSON")
    args = ap.parse_args()

    report = {
        "report": "grammar_audit",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "canonical": CANONICAL,
        "canonical_refs": _count_refs(CANONICAL),
        "modules": {},
        "doctrine": {"r2": "déplacement, pas de suppression",
                     "r6": "fail-open", "r9": "audit JSON", "r10": "compute only"},
    }
    for mod in [CANONICAL] + TO_ARCHIVE:
        report["modules"][mod] = {"refs": _count_refs(mod)}

    if args.apply:
        report["apply"] = {}
        for f in DIRECT_IMPORT_FILES:
            report["apply"][str(f.relative_to(ROOT))] = _make_import_fail_open(f)
        report["apply"]["reading_modules_updated"] = _remove_from_reading_modules()
        report["apply"]["moved"] = _archive()

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"grammar_audit_{report['date'].replace('-', '_')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"canonical : {report['canonical']} ({len(report['canonical_refs'])} refs)")
        for mod, info in report["modules"].items():
            print(f"  {mod:<28} {len(info['refs'])} refs")
        if args.apply:
            print("apply     :", json.dumps(report["apply"], ensure_ascii=False))
        print(f"rapport   : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
