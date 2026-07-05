"""Vérification et maintenance de la cohérence doc/code — PowerFlow V9.

Lit docs/DOC_REGISTRY.yml (source de vérité pour l'état des documents, voir
docs/DOC_GOVERNANCE.md) et le confronte au code réel. N'écrit jamais dans
core/v9/ ni dans data/ — modifie uniquement docs/DOC_REGISTRY.yml, et
seulement avec --update.

Usage :
    python tools/doc_sync.py --check    # vérifie tout, code de sortie != 0 si problème
    python tools/doc_sync.py --update   # met à jour last_update dans DOC_REGISTRY.yml
    python tools/doc_sync.py --stale    # liste les docs sans modification depuis 30 jours
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "docs" / "DOC_REGISTRY.yml"
STALE_DAYS = 30

# Répertoires de code dont chaque .py doit porter un docstring de module.
CODE_DIRS = [ROOT / "core" / "v9", ROOT / "scripts"]

# Répertoires de doc scannés pour détecter les fichiers non enregistrés.
DOC_SCAN_DIRS = [ROOT / "docs"]
DOC_EXTENSIONS = {".md", ".yml", ".yaml"}


def load_registry() -> list[dict]:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    return data.get("docs", [])


def git_last_commit_date(path: Path) -> str | None:
    """Date (YYYY-MM-DD) du dernier commit touchant ce fichier, ou None si non commité."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def check_registry_paths_exist(registry: list[dict]) -> list[str]:
    problems = []
    for entry in registry:
        path = ROOT / entry["path"]
        if not path.exists():
            problems.append(f"DOC_REGISTRY.yml référence {entry['path']} — fichier absent")
    return problems


def check_unregistered_docs(registry: list[dict]) -> list[str]:
    registered = {entry["path"].replace("\\", "/") for entry in registry}
    problems = []
    for scan_dir in DOC_SCAN_DIRS:
        for path in scan_dir.rglob("*"):
            if path.suffix not in DOC_EXTENSIONS or not path.is_file():
                continue
            if path.name == "DOC_REGISTRY.yml":
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel not in registered:
                problems.append(f"{rel} — présent sur disque mais absent de DOC_REGISTRY.yml")
    return problems


def has_module_docstring(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return True  # ne bloque pas sur un fichier illisible, hors périmètre de ce script
    return ast.get_docstring(tree) is not None


def check_code_docstrings() -> list[str]:
    problems = []
    for code_dir in CODE_DIRS:
        if not code_dir.exists():
            continue
        for path in sorted(code_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            if not has_module_docstring(path):
                problems.append(f"{path.relative_to(ROOT).as_posix()} — aucun docstring de module")
    return problems


def check_state_md_freshness() -> list[str]:
    """Avertit si du code core/v9/scripts a été modifié sans que STATE.md le soit
    (working tree non commité — proxy local de la vérification CI sur diff de commit)."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    changed = [line[3:].strip() for line in out.splitlines() if line.strip()]
    code_changed = any(
        (f.startswith("core/v9/") or f.startswith("scripts/")) and f.endswith(".py")
        for f in changed
    )
    state_changed = any(f == "docs/STATE.md" for f in changed)
    if code_changed and not state_changed:
        return ["du code core/v9/ ou scripts/ est modifié (working tree) sans mise à jour de docs/STATE.md"]
    return []


def cmd_check() -> int:
    registry = load_registry()
    problems: list[str] = []
    problems += check_registry_paths_exist(registry)
    problems += check_unregistered_docs(registry)
    problems += check_code_docstrings()
    problems += check_state_md_freshness()

    if not problems:
        print(f"OK — {len(registry)} documents enregistrés, aucun problème détecté.")
        return 0

    print(f"{len(problems)} problème(s) détecté(s) :")
    for problem in problems:
        print(f"  - {problem}")
    return 1


def cmd_update() -> int:
    registry = load_registry()
    updated = 0
    for entry in registry:
        path = ROOT / entry["path"]
        if not path.exists():
            continue
        commit_date = git_last_commit_date(path)
        new_date = commit_date or date.today().isoformat()
        if entry.get("last_update") != new_date:
            print(f"{entry['path']}: {entry.get('last_update')} -> {new_date}")
            entry["last_update"] = new_date
            updated += 1

    if updated:
        header = (
            "# DOC_REGISTRY.yml — PowerFlow V9\n"
            "#\n"
            "# Source de vérité pour l'état de tous les documents du repo (voir DOC_GOVERNANCE.md).\n"
            "# Régénéré partiellement par tools/doc_sync.py --update (champ last_update uniquement).\n"
            "#\n"
        )
        body = yaml.safe_dump({"docs": registry}, allow_unicode=True, sort_keys=False, width=100)
        REGISTRY_PATH.write_text(header + "\n" + body, encoding="utf-8")

    print(f"{updated} entrée(s) mise(s) à jour." if updated else "Rien à mettre à jour.")
    return 0


def cmd_stale() -> int:
    registry = load_registry()
    threshold = date.today() - timedelta(days=STALE_DAYS)
    stale_entries = []
    for entry in registry:
        last_update = entry.get("last_update")
        if not last_update:
            continue
        try:
            d = datetime.strptime(str(last_update), "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < threshold:
            stale_entries.append(entry)

    if not stale_entries:
        print(f"Aucun document au-delà du seuil de {STALE_DAYS} jours.")
        return 0

    print(f"{len(stale_entries)} document(s) sans mise à jour depuis {STALE_DAYS}+ jours :")
    for entry in stale_entries:
        print(f"  - {entry['path']} (dernière maj : {entry['last_update']})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Vérifie la cohérence doc/code")
    group.add_argument("--update", action="store_true", help="Met à jour DOC_REGISTRY.yml")
    group.add_argument("--stale", action="store_true", help="Liste les docs périmés (30+ jours)")
    args = parser.parse_args()

    if args.check:
        return cmd_check()
    if args.update:
        return cmd_update()
    return cmd_stale()


if __name__ == "__main__":
    sys.exit(main())
