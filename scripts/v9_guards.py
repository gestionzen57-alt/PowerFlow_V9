#!/usr/bin/env python
"""v9_guards.py — Gardiens de cohérence automatisés pour PowerFlow V9.

Transforment les règles doctrinales (R7, R8, R14, R18, R26) en gates
exécutables. Au lieu de faire confiance à la discipline multi-agents,
ces gardiens vérifient mécaniquement la cohérence avant chaque commit/push.

Usage :
    python scripts/v9_guards.py all          # tous les gardiens
    python scripts/v9_guards.py no-secrets   # tokens en clair
    python scripts/v9_guards.py yaml-sync    # YAML disque = config
    python scripts/v9_guards.py scripts-exist # scripts référencés existent
    python scripts/v9_guards.py hitl-sync   # HITL_CONF cohérent entre modules
    python scripts/v9_guards.py db-sync     # DB principles = YAML disque

Exit code : 0 = OK, 1 = incohérence trouvée (liste affichée).
Doctrine : R7 (zéro régression), R14 (git = vérité), R26 (livraison complète).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Patterns de secrets ──────────────────────────────────────────────
TELEGRAM_TOKEN_RE = re.compile(r"\d{8,}:[A-Za-z0-9_-]{20,}")
GHP_TOKEN_RE = re.compile(r"ghp_[A-Za-z0-9]{10,}")


def _scan_files(patterns: list[tuple[str, re.Pattern]], tracked_only: bool = True) -> list[str]:
    """Scanne les fichiers trackés (ou tous) à la recherche de patterns."""
    issues: list[str] = []
    if tracked_only:
        import subprocess
        result = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, cwd=str(ROOT)
        )
        files = [ROOT / f for f in result.stdout.strip().split("\n") if f]
    else:
        files = list(ROOT.rglob("*"))
    # Whitelist : fichiers légitimes pouvant contenir des tokens
    whitelist = {".env", "config/telegram.json", ".env.bak.20260709_202852"}
    for f in files:
        if not f.is_file() or f.suffix not in (".py", ".md", ".env", ".json", ".yml", ".yaml", ".txt", ".bat", ".ps1"):
            continue
        rel = f.relative_to(ROOT).as_posix()
        if rel in whitelist or rel.startswith(".venv/") or rel.startswith(".git/"):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for name, pat in patterns:
            for m in pat.finditer(content):
                # Token sanitisé (avec ***) = OK, on ne flag que les complets
                matched = m.group(0)
                if "***" in content[m.start():m.start() + len(matched) + 5]:
                    continue
                issues.append(f"  {rel}:{content[:m.start()].count(chr(10)) + 1} — {name} détecté : {matched[:20]}...")
    return issues


def guard_no_secrets() -> tuple[bool, list[str]]:
    """Vérifie qu'aucun token (Telegram, GitHub) n'est en clair dans les fichiers trackés."""
    issues = _scan_files([
        ("Token Telegram", TELEGRAM_TOKEN_RE),
        ("Token GitHub", GHP_TOKEN_RE),
    ], tracked_only=True)
    ok = len(issues) == 0
    return ok, issues


def guard_yaml_sync() -> tuple[bool, list[str]]:
    """Vérifie que chaque YAML sur disque est soit dans PRINCIPLE_ACTIVE_IDS, soit SHADOW."""
    issues: list[str] = []
    yaml_dir = ROOT / "core" / "v9" / "principles"
    yaml_files = sorted(yaml_dir.glob("*.yaml"))
    yaml_ids = {f.stem for f in yaml_files}

    # Lire PRINCIPLE_ACTIVE_IDS depuis config.py
    config_path = ROOT / "core" / "v9" / "config.py"
    config_content = config_path.read_text(encoding="utf-8")
    # Extract PRINCIPLE_ACTIVE_IDS list (ignore les lignes commentées `# "..."`)
    match = re.search(
        r"PRINCIPLE_ACTIVE_IDS\s*=\s*\[(.*?)\n\]",
        config_content, re.DOTALL,
    )
    if not match:
        return False, ["  Impossible de parser PRINCIPLE_ACTIVE_IDS dans config.py"]
    block = match.group(1)
    # Filtrer les lignes commentées avant d'extraire les IDs entre guillemets.
    active_lines = [
        ln for ln in block.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    active_ids = set(re.findall(r'"([^"]+)"', "\n".join(active_lines)))

    # Chaque YAML doit être ACTIVE ou SHADOW (v9_status dans le fichier)
    for yf in yaml_files:
        import yaml
        raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
        pid = raw.get("id", yf.stem)
        status = raw.get("v9_status", raw.get("status", "?"))
        if pid in active_ids and status != "ACTIVE":
            issues.append(f"  {yf.name}: dans PRINCIPLE_ACTIVE_IDS mais v9_status={status}")
        if pid not in active_ids and status == "ACTIVE":
            issues.append(f"  {yf.name}: v9_status=ACTIVE mais absent de PRINCIPLE_ACTIVE_IDS")

    # ACTIVE_IDS doit pointer vers des YAML existants
    for aid in active_ids:
        if aid not in yaml_ids:
            issues.append(f"  {aid} dans PRINCIPLE_ACTIVE_IDS mais pas de YAML sur disque")

    ok = len(issues) == 0
    return ok, issues


def guard_scripts_exist() -> tuple[bool, list[str]]:
    """Vérifie que les scripts référencés dans mcp_servers/ existent sur disque."""
    issues: list[str] = []
    mcp_dir = ROOT / "mcp_servers"
    for mcp_file in mcp_dir.glob("*.py"):
        content = mcp_file.read_text(encoding="utf-8")
        # Cherche ALLOWED_SCRIPTS = { "v9_xxx", ... }
        match = re.search(r'ALLOWED_SCRIPTS\s*=\s*\{(.*?)\}', content, re.DOTALL)
        if not match:
            continue
        script_names = re.findall(r'"(v9_[a-z_]+)"', match.group(1))
        for sname in script_names:
            script_path = ROOT / "scripts" / f"{sname}.py"
            if not script_path.exists():
                issues.append(f"  {mcp_file.name}: référence scripts/{sname}.py — MANQUANT")
    ok = len(issues) == 0
    return ok, issues


def guard_hitl_sync() -> tuple[bool, list[str]]:
    """Vérifie que HITL_CONF_HIGH est cohérent entre decision_logger et dashboard_queries."""
    issues: list[str] = []
    modules = [
        ROOT / "core" / "v9" / "decision_logger.py",
        ROOT / "core" / "v9" / "dashboard_queries.py",
    ]
    values = {}
    for mod in modules:
        content = mod.read_text(encoding="utf-8")
        match = re.search(r"HITL_CONF_HIGH\s*=\s*(\d+)", content)
        if match:
            values[mod.relative_to(ROOT).as_posix()] = int(match.group(1))
    if len(set(values.values())) > 1:
        for mod, val in values.items():
            issues.append(f"  {mod}: HITL_CONF_HIGH={val}")
        issues.append("  → Tous les modules doivent avoir la même valeur")
    ok = len(issues) == 0
    return ok, issues


def guard_db_sync() -> tuple[bool, list[str]]:
    """Vérifie que la table DB 'principles' correspond aux YAML sur disque (pas d'archivés)."""
    issues: list[str] = []
    db_path = ROOT / "data" / "v9_forces.db"
    if not db_path.exists():
        return True, ["  DB absente — skip (env de test)"]
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT principle_id, v9_status FROM principles").fetchall()
    except sqlite3.OperationalError:
        return True, ["  Table 'principles' absente — skip"]
    finally:
        conn.close()

    yaml_dir = ROOT / "core" / "v9" / "principles"
    yaml_ids = {f.stem for f in yaml_dir.glob("*.yaml")}
    # Les archivés ne doivent pas être en DB comme actifs
    archived_dir = ROOT / "core" / "v9" / "principles" / "_archive"
    archived_ids = {f.stem for f in archived_dir.glob("*.yaml")} if archived_dir.exists() else set()
    db_ids = {row[0] for row in rows}
    for aid in archived_ids:
        if aid in db_ids:
            issues.append(f"  {aid}: archivé (_archive/) mais présent en DB principles")
    # YAML sur disque mais pas en DB (untracked → DB désynchronisée)
    not_in_db = yaml_ids - db_ids
    if not_in_db:
        issues.append(f"  YAML sur disque mais absents de la DB : {sorted(not_in_db)}")
    ok = len(issues) == 0
    return ok, issues


# ── Orchestration ────────────────────────────────────────────────────
GUARDS = {
    "no-secrets": ("Tokens en clair dans fichiers trackés", guard_no_secrets),
    "yaml-sync": ("YAML disque = PRINCIPLE_ACTIVE_IDS", guard_yaml_sync),
    "scripts-exist": ("Scripts MCP référencés existent", guard_scripts_exist),
    "hitl-sync": ("HITL_CONF_HIGH cohérent entre modules", guard_hitl_sync),
    "db-sync": ("DB principles = YAML disque", guard_db_sync),
}


def run(guard_names: list[str] | None = None) -> int:
    names = guard_names or list(GUARDS.keys())
    all_ok = True
    for name in names:
        if name not in GUARDS:
            print(f"  ⚠️  Gardien inconnu : {name}")
            continue
        desc, func = GUARDS[name]
        ok, issues = func()
        status = "✅" if ok else "❌"
        print(f"{status} {name} — {desc}")
        if not ok:
            all_ok = False
            for line in issues:
                print(f"   {line}")
    print()
    if all_ok:
        print("✅ Tous les gardiens V9 sont OK.")
    else:
        print("❌ Incohérences détectées — corriger avant commit/push (R7, R26).")
    return 0 if all_ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "all":
        sys.exit(run())
    else:
        sys.exit(run(args))