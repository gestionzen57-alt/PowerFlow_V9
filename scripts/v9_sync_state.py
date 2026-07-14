#!/usr/bin/env python
"""v9_sync_state.py — Générateur automatique de l'état V9 depuis les sources de vérité.

Au lieu de saisir les chiffres à la main dans STATE.md / CACHE_BOARD.md / AGENT.md,
ce script lit les sources réelles (DB, pytest, git, disque) et régénère la section
<!-- AUTO:STATE --> ... <!-- /AUTO:STATE --> dans chaque document.

Les chiffres sont TOUJOURS exacts car générés depuis les sources, jamais tapés.
Doctrine : R14 (git = vérité), R26 (STATE.md à jour).

Usage :
    python scripts/v9_sync_state.py              # génère dans les docs
    python scripts/v9_sync_state.py --dry-run     # affiche sans écrire
    python scripts/v9_sync_state.py --check       # exit 1 si pas à jour
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "v9_forces.db"
DOCS_TO_SYNC = [
    ROOT / "docs" / "STATE.md",
    ROOT / "docs" / "CACHE_BOARD.md",
    ROOT / "AGENT.md",
]

AUTO_OPEN = "<!-- AUTO:STATE -->"
AUTO_CLOSE = "<!-- /AUTO:STATE -->"


def _db_stats() -> dict[str, str]:
    """Lit la DB réelle et retourne les métriques."""
    stats = {}
    if not DB_PATH.exists():
        return {"db_status": "DB absente"}
    size_bytes = DB_PATH.stat().st_size
    if size_bytes > 1_000_000_000:
        stats["db_size"] = f"{size_bytes / 1_073_741_824:.2f} GB"
    else:
        stats["db_size"] = f"{size_bytes / 1_048_576:.0f} MB"
    try:
        conn = sqlite3.connect(str(DB_PATH))
        stats["db_tables"] = str(conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0])
        stats["db_index"] = str(conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='index'"
        ).fetchone()[0])
        for table in ("decisions", "forces_snapshots", "scenes", "principle_evaluations",
                       "regime_snapshots", "paper_trades", "principle_scores", "signals"):
            try:
                n = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                stats[f"db_{table}"] = str(n)
            except sqlite3.OperationalError:
                stats[f"db_{table}"] = "N/A"
        conn.close()
    except Exception as e:
        stats["db_status"] = f"Erreur DB : {e}"
    return stats


def _pytest_count() -> dict[str, str]:
    """Compte les tests via pytest --collect-only (rapide, n'exécute pas)."""
    python = str(ROOT / ".venv" / "Scripts" / "python.exe")
    if not Path(python).exists():
        python = sys.executable
    try:
        result = subprocess.run(
            [python, "-m", "pytest", "tests/", "--collect-only", "-q", "--no-header"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60,
        )
        # Output : "N tests, M errors" ou "N tests collected"
        last_lines = result.stdout.strip().split("\n")[-1] if result.stdout.strip() else ""
        # Extract number
        import re
        m = re.search(r"(\d+) tests?", last_lines)
        if m:
            return {"tests_collected": m.group(1)}
        return {"tests_collected": "?"}
    except Exception as e:
        return {"tests_collected": f"Erreur : {e}"}


def _yaml_count() -> dict[str, str]:
    """Compte les YAML de principes sur disque."""
    yaml_dir = ROOT / "core" / "v9" / "principles"
    yamls = list(yaml_dir.glob("*.yaml"))
    import yaml
    active = 0
    shadow = 0
    for yf in yamls:
        raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
        status = raw.get("v9_status", raw.get("status", "?"))
        if status == "ACTIVE":
            active += 1
        elif status == "SHADOW":
            shadow += 1
    return {
        "yaml_total": str(len(yamls)),
        "yaml_active": str(active),
        "yaml_shadow": str(shadow),
    }


def _git_head() -> str:
    """Retourne le SHA + message du HEAD."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return "?"


def _kill_switches() -> dict[str, str]:
    """Lit les kill switches depuis le fichier env réel."""
    env_path = ROOT / "config" / "v9_kill_switches.env"
    switches = {}
    if not env_path.exists():
        return {"kill_switches": "fichier absent"}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            switches[key.strip()] = val.strip()
    return {f"sw_{k}": v for k, v in switches.items()}


def _cron_count() -> dict[str, str]:
    """Compte les crons Windows V9."""
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/fo", "csv", "/nh"],
            capture_output=True, timeout=15,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        v9_lines = [l for l in stdout.splitlines() if "V9_" in l and "Ready" in l]
        return {"crons_ready": str(len(v9_lines))}
    except Exception:
        return {"crons_ready": "?"}


def _mcp_count() -> dict[str, str]:
    """Compte les serveurs MCP sur disque."""
    mcp_dir = ROOT / "mcp_servers"
    servers = list(mcp_dir.glob("*.py"))
    # Exclude __init__ or utils
    servers = [s for s in servers if not s.name.startswith("_") and not s.name.startswith("utils")]
    return {"mcp_servers": str(len(servers))}


def generate_state_block() -> str:
    """Génère le bloc AUTO:STATE depuis les sources de vérité."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    db = _db_stats()
    tests = _pytest_count()
    yamls = _yaml_count()
    switches = _kill_switches()
    crons = _cron_count()
    mcps = _mcp_count()
    head = _git_head()

    lines = [
        AUTO_OPEN,
        f"<!-- Généré automatiquement par scripts/v9_sync_state.py — {now} -->",
        f"<!-- Ne pas éditer manuellement. Pour forcer : python scripts/v9_sync_state.py -->",
        "",
        "| Métrique | Valeur | Source |",
        "|---|---|---|",
        f"| HEAD | `{head}` | `git log --oneline -1` |",
        f"| Tests collectés | {tests.get('tests_collected', '?')} | `pytest --collect-only` |",
        f"| Tables DB | {db.get('db_tables', '?')} | `sqlite3 data/v9_forces.db` |",
        f"| Index DB | {db.get('db_index', '?')} | `sqlite3` |",
        f"| Taille DB | {db.get('db_size', '?')} | `du -h` |",
        f"| Décisions | {db.get('db_decisions', '?')} | `SELECT count(*) FROM decisions` |",
        f"| Forces snapshots | {db.get('db_forces_snapshots', '?')} | DB |",
        f"| Scènes | {db.get('db_scenes', '?')} | DB |",
        f"| Principle evals | {db.get('db_principle_evaluations', '?')} | DB |",
        f"| Régime snapshots | {db.get('db_regime_snapshots', '?')} | DB |",
        f"| Paper trades | {db.get('db_paper_trades', '?')} | DB |",
        f"| Principle scores | {db.get('db_principle_scores', '?')} | DB |",
        f"| Principes YAML | {yamls.get('yaml_total', '?')} ({yamls.get('yaml_active', '?')} ACTIVE + {yamls.get('yaml_shadow', '?')} SHADOW) | `ls core/v9/principles/*.yaml` |",
        f"| Serveurs MCP | {mcps.get('mcp_servers', '?')} | `ls mcp_servers/*.py` |",
        f"| Crons Ready | {crons.get('crons_ready', '?')} | `schtasks /query` |",
        f"| V9_TRADER_MINI_ENABLED | {switches.get('sw_V9_TRADER_MINI_ENABLED', '?')} | `config/v9_kill_switches.env` |",
        f"| V9_AUTO_CALIBRATOR_ENABLED | {switches.get('sw_V9_AUTO_CALIBRATOR_ENABLED', '?')} | env |",
        f"| V9_SHADOW_MODE_ENABLED | {switches.get('sw_V9_SHADOW_MODE_ENABLED', '?')} | env |",
        f"| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | {switches.get('sw_V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED', '?')} | env |",
        f"| V9_EXECUTION_ENABLED | {switches.get('sw_V9_EXECUTION_ENABLED', '0 (commenté)')} | env |",
        "",
        AUTO_CLOSE,
    ]
    return "\n".join(lines)


def sync_file(doc_path: Path, block: str, dry_run: bool = False) -> bool:
    """Insère/remplace le bloc AUTO:STATE dans un document. Retourne True si modifié."""
    if not doc_path.exists():
        return False
    content = doc_path.read_text(encoding="utf-8")
    # Trouve le bloc existant
    start = content.find(AUTO_OPEN)
    end = content.find(AUTO_CLOSE)
    if start == -1 or end == -1:
        # Pas de balise → on n'ajoute pas (l'utilisateur doit placer les balises)
        return False
    end_pos = end + len(AUTO_CLOSE)
    old_block = content[start:end_pos]
    if old_block.strip() == block.strip():
        return False  # déjà à jour
    new_content = content[:start] + block + content[end_pos:]
    if dry_run:
        print(f"  → {doc_path.name} : serait mis à jour")
        return True
    doc_path.write_text(new_content, encoding="utf-8")
    print(f"  ✅ {doc_path.name} : mis à jour")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronise l'état V9 depuis les sources.")
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans écrire")
    parser.add_argument("--check", action="store_true", help="Exit 1 si pas à jour")
    args = parser.parse_args()

    print("📊 Génération de l'état depuis les sources de vérité...\n")
    block = generate_state_block()
    print(block)
    print()

    if args.check:
        # Mode check : compare sans écrire
        modified = False
        for doc in DOCS_TO_SYNC:
            if doc.exists():
                content = doc.read_text(encoding="utf-8")
                start = content.find(AUTO_OPEN)
                end = content.find(AUTO_CLOSE)
                if start == -1 or end == -1:
                    continue
                old_block = content[start:end + len(AUTO_CLOSE)]
                if old_block.strip() != block.strip():
                    print(f"  ⚠️  {doc.name} n'est pas à jour")
                    modified = True
        return 1 if modified else 0

    print("📝 Synchronisation des documents...\n")
    any_changed = False
    for doc in DOCS_TO_SYNC:
        if sync_file(doc, block, dry_run=args.dry_run):
            any_changed = True
    if not any_changed:
        print("  ✅ Tous les documents sont déjà à jour.")
    return 0


if __name__ == "__main__":
    sys.exit(main())