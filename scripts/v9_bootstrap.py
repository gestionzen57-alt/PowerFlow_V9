#!/usr/bin/env python3
"""v9_bootstrap.py — Procédure de reboot machine PowerFlow V9 (--boot).

Automatise la séquence manuelle décrite dans
`docs/deployment/V9_DEPLOYMENT_GUIDE.md` étape 3 et
`workspace/perplexity/assets/MARKET_OPEN_TEMPLATE.md` §T-30 : vérifications
bloquantes (reprises de `scripts/deploy_v9.py`, non dupliquées), nettoyage
d'un éventuel process de capture stale sur le port d'écoute (incident
récurrent, voir `workspace/perplexity/INCIDENTS.md` 2026-07-05), démarrage
du serveur de capture en arrière-plan, observation initiale, puis
mini-checkpoint automatique.

Couche cognitive : outillage de déploiement uniquement. Aucune logique de
trading, aucune décision, aucune modification de `core/v9/*`.

Usage :
    python scripts/v9_bootstrap.py --boot
    python scripts/v9_bootstrap.py --boot --dry-run
    python scripts/v9_bootstrap.py --boot --skip-start
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import LISTEN_PORT  # noqa: E402
from scripts.v9_supervisor import (  # noqa: E402
    ensure_port_free,
    generate_mini_checkpoint,
    health_snapshot_to_observed_lines,
    is_server_running,
    read_health_snapshot,
    setup_logging,
    start_capture_server_background,
)


def run_boot(
    dry_run: bool = False,
    skip_start: bool = False,
    wait_s: float = 2.0,
    write_checkpoint: bool = True,
) -> int:
    """`write_checkpoint=False` permet à un appelant (ex. `v9_market_open.py`)
    de réutiliser cette séquence sans générer un mini-checkpoint "boot"
    redondant avec son propre mini-checkpoint plus spécifique."""
    logger = setup_logging("v9.bootstrap")
    logger.info("=== Demarrage procedure --boot ===")

    snapshot = read_health_snapshot()
    blocking_ok = snapshot["python_ok"] and snapshot["modules_ok"] and snapshot["db_ok"]
    if not blocking_ok:
        logger.error("Verification bloquante en echec (Python/modules/DB) — arret de --boot.")
        return 1
    logger.info("Verifications bloquantes (Python/modules/DB) : OK.")

    if dry_run:
        logger.info("--dry-run : aucune action de demarrage effectuee.")
        print(f"Port {LISTEN_PORT} disponible : {snapshot['port_available']}")
        print(f"Serveur deja actif : {snapshot['server_running']}")
        return 0

    port_freed = ensure_port_free(LISTEN_PORT, logger)
    if not port_freed:
        logger.error(
            f"Port {LISTEN_PORT} indisponible et non liberable automatiquement — "
            f"intervention manuelle requise avant de continuer."
        )
        return 1

    already_running, existing_pid = is_server_running()
    if already_running:
        logger.info(f"Serveur de capture deja actif (PID {existing_pid}) — pas de redemarrage.")
    elif skip_start:
        logger.info("--skip-start : demarrage du serveur de capture ignore (demande explicite).")
    else:
        start_capture_server_background(logger)
        time.sleep(wait_s)
        running, pid = is_server_running()
        if not running:
            logger.error("Le serveur de capture ne repond pas apres demarrage — verifier logs/v9_capture.log.")
            return 1
        logger.info(f"Serveur de capture confirme actif (PID {pid}) apres {wait_s:.0f}s.")

    logger.info("Observation initiale (health snapshot post-boot)...")
    post_snapshot = read_health_snapshot()
    observed = health_snapshot_to_observed_lines(post_snapshot)
    for line in observed:
        logger.info(f"  - {line}")

    if write_checkpoint:
        checkpoint_path = generate_mini_checkpoint(
            kind="boot",
            contexte="Reboot machine automatise (scripts/v9_bootstrap.py --boot).",
            observed_lines=observed,
        )
        logger.info(f"Mini-checkpoint ecrit : {checkpoint_path}")
    logger.info("=== --boot termine avec succes ===")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Procedure de reboot machine PowerFlow V9")
    parser.add_argument("--boot", action="store_true", help="Executer la procedure de boot (requis)")
    parser.add_argument("--dry-run", action="store_true", help="Verifier sans demarrer le serveur")
    parser.add_argument("--skip-start", action="store_true", help="Ne pas demarrer le serveur meme s'il est inactif")
    args = parser.parse_args()

    if not args.boot:
        parser.error("--boot est requis")
    return run_boot(dry_run=args.dry_run, skip_start=args.skip_start)


if __name__ == "__main__":
    sys.exit(main())
