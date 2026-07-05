#!/usr/bin/env python3
"""v9_session_resume.py — Reprise de session PowerFlow V9 (--resume).

Automatise la vérification mécanique décrite dans
`workspace/perplexity/REPRISE_TEMPLATE_CLAUDE.md` : existence et ordre de
lecture des documents de continuité, détection des checkpoints référencés
par `docs/STATE.md` mais absents du dépôt (rupture de continuité), état
git, et health snapshot système. Ne lit ni n'interprète le contenu métier
de ces documents (aucun LLM requis) — seulement leur présence et les
références de fichiers qu'ils contiennent. La lecture/synthèse de fond
reste la responsabilité de l'opérateur ou de la session Claude qui reprend
le travail.

Couche cognitive : outillage de continuité uniquement. Aucune logique de
trading, aucune décision, aucune modification de `core/v9/*`.

Doctrine reprise (rappel, voir REPRISE_TEMPLATE_CLAUDE.md) : git gagne
toujours. Ce script ne remplace pas la lecture humaine/IA des documents —
il élimine juste la friction mécanique (fichier manquant ? référence
cassée ? état git actuel ?) avant de commencer cette lecture.

Usage :
    python scripts/v9_session_resume.py --resume
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.v9_supervisor import (  # noqa: E402
    generate_mini_checkpoint,
    git_branch,
    git_last_commit,
    health_snapshot_to_observed_lines,
    read_health_snapshot,
    setup_logging,
)

# Ordre de lecture imposé par REPRISE_TEMPLATE_CLAUDE.md.
REQUIRED_READING_ORDER = [
    "workspace/perplexity/BOARD.md",
    "docs/CACHE_BOARD.md",
    "docs/STATE.md",
    "workspace/perplexity/ACTIVE_TASKS.md",
    "workspace/perplexity/memory/DECISIONS_LOG.md",
]

CHECKPOINT_REF_PATTERN = re.compile(r"docs/checkpoints/[A-Za-z0-9_\-]+\.md")


def check_required_files() -> tuple[list[str], list[str]]:
    """Retourne (presents, manquants) parmi REQUIRED_READING_ORDER."""
    present, missing = [], []
    for rel_path in REQUIRED_READING_ORDER:
        (present if (ROOT_DIR / rel_path).exists() else missing).append(rel_path)
    return present, missing


def find_referenced_checkpoints(state_md_path: Path) -> list[str]:
    """Extrait les chemins `docs/checkpoints/*.md` référencés dans STATE.md."""
    if not state_md_path.exists():
        return []
    text = state_md_path.read_text(encoding="utf-8", errors="replace")
    return sorted(set(CHECKPOINT_REF_PATTERN.findall(text)))


def check_checkpoint_references(state_md_path: Path) -> tuple[list[str], list[str]]:
    """Retourne (existants, manquants) parmi les checkpoints référencés par
    STATE.md — une référence manquante est une rupture de continuité au
    sens de REPRISE_TEMPLATE_CLAUDE.md (doc cite un fichier qui n'existe
    pas)."""
    referenced = find_referenced_checkpoints(state_md_path)
    existing, missing = [], []
    for ref in referenced:
        (existing if (ROOT_DIR / ref).exists() else missing).append(ref)
    return existing, missing


def git_log_recent(n: int = 10) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "log", "--oneline", f"-{n}"],
            cwd=str(ROOT_DIR), capture_output=True, text=True, check=True, encoding="utf-8", errors="replace",
        )
        return out.stdout.strip().splitlines()
    except Exception:  # noqa: BLE001
        return []


def git_status_dirty() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ROOT_DIR), capture_output=True, text=True, check=True, encoding="utf-8", errors="replace",
        )
        return [line for line in out.stdout.strip().splitlines() if line]
    except Exception:  # noqa: BLE001
        return []


def run_resume(write_checkpoint: bool = True) -> int:
    logger = setup_logging("v9.session_resume")
    logger.info("=== Reprise de session — verification de continuite ===")

    present, missing_files = check_required_files()
    for rel_path in present:
        logger.info(f"  [OK]   {rel_path}")
    for rel_path in missing_files:
        logger.error(f"  [ABSENT] {rel_path}")

    state_md = ROOT_DIR / "docs" / "STATE.md"
    existing_cps, missing_cps = check_checkpoint_references(state_md)
    logger.info(f"Checkpoints references par STATE.md : {len(existing_cps) + len(missing_cps)} trouves.")
    for ref in missing_cps:
        logger.error(f"  [RUPTURE] {ref} reference par STATE.md mais absent du depot.")

    branch = git_branch()
    last_commit = git_last_commit()
    recent_log = git_log_recent(10)
    dirty = git_status_dirty()

    logger.info(f"Branche courante : {branch}")
    logger.info(f"Dernier commit   : {last_commit}")
    if dirty:
        logger.warning(f"Working tree non propre : {len(dirty)} fichier(s) modifie(s)/non suivi(s).")
    else:
        logger.info("Working tree propre.")

    print("-" * 60)
    print("Git log --oneline -10 :")
    for line in recent_log:
        print(f"  {line}")
    print("-" * 60)

    snapshot = read_health_snapshot()
    observed = health_snapshot_to_observed_lines(snapshot)
    print("Health snapshot :")
    for line in observed:
        print(f"  - {line}")

    continuity_broken = bool(missing_files or missing_cps)
    if continuity_broken:
        logger.error(
            "RUPTURE DE CONTINUITE DETECTEE — reconstruire l'etat a partir de git avant "
            "de poursuivre (ne rien deviner), voir REPRISE_TEMPLATE_CLAUDE.md."
        )
    else:
        logger.info("Aucune rupture de continuite mecanique detectee.")

    if write_checkpoint:
        contexte = (
            "Reprise de session automatisee (scripts/v9_session_resume.py --resume)."
        )
        ecart = (
            "\n".join(
                [f"- Fichier de continuite absent : {p}" for p in missing_files]
                + [f"- Checkpoint reference mais absent : {p}" for p in missing_cps]
            )
            if continuity_broken
            else "Aucun ecart releve — continuite mecanique intacte."
        )
        checkpoint_path = generate_mini_checkpoint(
            kind="resume",
            contexte=contexte,
            observed_lines=observed + [f"Branche: {branch}", f"Dernier commit: {last_commit}"],
            ecart=ecart,
            suite=(
                "Reconstruire l'etat depuis git avant de poursuivre."
                if continuity_broken
                else "Poursuivre la lecture des documents dans l'ordre impose (voir REPRISE_TEMPLATE_CLAUDE.md)."
            ),
        )
        logger.info(f"Mini-checkpoint ecrit : {checkpoint_path}")

    return 2 if continuity_broken else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprise de session PowerFlow V9")
    parser.add_argument("--resume", action="store_true", help="Executer la verification de reprise (requis)")
    parser.add_argument("--no-checkpoint", action="store_true", help="Ne pas generer de mini-checkpoint")
    args = parser.parse_args()

    if not args.resume:
        parser.error("--resume est requis")
    return run_resume(write_checkpoint=not args.no_checkpoint)


if __name__ == "__main__":
    sys.exit(main())
