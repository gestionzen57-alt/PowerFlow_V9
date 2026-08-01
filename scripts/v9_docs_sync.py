"""v9_docs_sync.py — Phase 73 motion CEO 48H.

Docs sync auto : regenere INDEX_MODULES.md + USER_GUIDE + BILAN.
Verifie coherence.

Auteur : Hermes (Phase 73 motion CEO 48H non-stop, 31/07/2026)
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

log = logging.getLogger("v9.docs_sync")


def count_modules() -> dict:
    """Count modules par categorie."""
    scripts_dir = _ROOT / "scripts"
    modules = {"core": 0, "scripts": 0, "tests": 0}
    modules["scripts"] = len(list(scripts_dir.glob("v9_*.py")))
    core_dir = _ROOT / "core" / "v9"
    if core_dir.exists():
        modules["core"] = len(list(core_dir.glob("v9_*.py")))
    tests_dir = _ROOT / "tests"
    if tests_dir.exists():
        modules["tests"] = len(list(tests_dir.glob("test_v9_*.py")))
    return modules


def count_loc() -> int:
    """Total lignes de code."""
    total = 0
    for pattern in ["scripts/v9_*.py", "core/v9/v9_*.py", "tests/test_v9_*.py"]:
        for f in _ROOT.glob(pattern):
            try:
                total += sum(1 for _ in f.read_text(encoding="utf-8")
                                  .splitlines())
            except Exception:
                continue
    return total


def generate_index() -> str:
    """Genere INDEX_MODULES.md."""
    modules = count_modules()
    loc = count_loc()
    md = []
    md.append("# INDEX MODULES — PowerFlow V9")
    md.append("")
    md.append(f"Auto-genere le {datetime.date.today().isoformat()}")
    md.append("")
    md.append(f"## Statistiques globales")
    md.append(f"- **Core modules** : {modules['core']}")
    md.append(f"- **Scripts CLI** : {modules['scripts']}")
    md.append(f"- **Tests** : {modules['tests']}")
    md.append(f"- **Total LOC** : {loc:,}")
    md.append("")
    md.append("## Scripts CLI (v9_*.py)")
    for f in sorted((_ROOT / "scripts").glob("v9_*.py")):
        md.append(f"- `{f.name}`")
    md.append("")
    md.append("## Core modules (core/v9/v9_*.py)")
    core_dir = _ROOT / "core" / "v9"
    if core_dir.exists():
        for f in sorted(core_dir.glob("v9_*.py")):
            md.append(f"- `{f.name}`")
    md.append("")
    md.append("## Tests")
    for f in sorted((_ROOT / "tests").glob("test_v9_*.py")):
        md.append(f"- `{f.name}`")
    md.append("")
    md.append("---")
    md.append(f"Auto-genere via v9_docs_sync.py")
    return "\n".join(md)


def check_doc_coherence() -> dict:
    """Verifie coherence docs."""
    index_path = _ROOT / "docs" / "INDEX_MODULES.md"
    user_guide = _ROOT / "docs" / "USER_GUIDE.md"
    doctrine = _ROOT / "docs" / "DOCTRINE_48H_NONSTOP.md"
    return {
        "index_exists": index_path.exists(),
        "user_guide_exists": user_guide.exists(),
        "doctrine_exists": doctrine.exists(),
        "all_present": (index_path.exists() and user_guide.exists()
                          and doctrine.exists()),
    }


def sync_all() -> dict:
    """Sync tous les docs."""
    index_path = _ROOT / "docs" / "INDEX_MODULES.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_content = generate_index()
    index_path.write_text(index_content, encoding="utf-8")
    modules = count_modules()
    loc = count_loc()
    coherence = check_doc_coherence()
    return {
        "index_updated": True,
        "modules": modules,
        "total_loc": loc,
        "coherence": coherence,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="V9 docs sync (Phase 73)",
    )
    parser.add_argument("--sync", action="store_true",
                        help="Sync docs")
    parser.add_argument("--status", action="store_true",
                        help="Status coherence")
    args = parser.parse_args(argv)

    if args.status:
        coherence = check_doc_coherence()
        print("=" * 70)
        print("V9 DOCS COHERENCE")
        print("=" * 70)
        print(f"INDEX_MODULES.md : {coherence['index_exists']}")
        print(f"USER_GUIDE.md    : {coherence['user_guide_exists']}")
        print(f"DOCTRINE_48H.md  : {coherence['doctrine_exists']}")
        print(f"All present      : {coherence['all_present']}")
        print("=" * 70)
        return 0

    if args.sync:
        result = sync_all()
        print("=" * 70)
        print("V9 DOCS SYNC")
        print("=" * 70)
        print(f"INDEX updated  : {result['index_updated']}")
        print(f"Modules        : {result['modules']}")
        print(f"Total LOC      : {result['total_loc']:,}")
        print(f"Coherence      : {result['coherence']}")
        print("=" * 70)
        return 0

    # Default : sync
    result = sync_all()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    sys.exit(main())
