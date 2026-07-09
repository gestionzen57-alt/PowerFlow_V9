#!/usr/bin/env python3
"""v9_paper_trade_loop.py — Boucle paper-trade V9 (Phase 10).

Workflow à chaque passe :
  1. Délègue à v9_paper_trade_run.run() pour la logique métier
     (Arbiter → RiskManager → PaperTradeLogger).
  2. Logge les trades ouverts dans un fichier rapport.
  3. En mode --watch, boucle avec intervalle configurable.

Doctrine :
  - Zéro ordre réel — paper-trade = simulation uniquement.
  - Idempotent : ne rouvre jamais un trade pour le même (snapshot_id, direction).
  - Consommateur autonome : ne modifie PAS l'orchestrateur (R8 préservée).

Usage :
    # Une seule passe (cron)
    python scripts/v9_paper_trade_loop.py --once

    # Boucle continue (daemon)
    python scripts/v9_paper_trade_loop.py --watch --interval 300

    # Dry-run (aucune écriture DB)
    python scripts/v9_paper_trade_loop.py --once --dry-run

    # Rapport personnalisé
    python scripts/v9_paper_trade_loop.py --once --report reports/paper_trades.log
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from scripts import v9_paper_trade_run as ptr  # noqa: E402

# ── Constantes ────────────────────────────────────────────────
DEFAULT_INTERVAL_SECONDS = 300  # 5 min
DEFAULT_SNAPSHOT_LIMIT = 10
DEFAULT_REPORT_PATH = ROOT_DIR / "logs" / "v9_paper_trade_report.log"
LOG_PATH = ROOT_DIR / "logs" / "v9_paper_trade_loop.log"


# ── Logging ──────────────────────────────────────────────────
def _setup_logging() -> logging.Logger:
    """Configure le logger du daemon (fichier + console)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass

    logger = logging.getLogger("v9_paper_trade_loop")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


# ── Rapport ──────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_report(
    report_path: Path,
    summary: dict[str, Any],
    logger: logging.Logger,
) -> None:
    """Append un résumé de passe dans le fichier rapport.

    Format : une ligne JSON par passe, pour parsing facile.
    Ne lève jamais d'exception (catch OSError + log warning).
    """
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("Impossible de créer le dossier du rapport %s : %s", report_path.parent, e)
        return
    entry = {
        "timestamp_utc": _now_iso(),
        "snapshots_analyses": summary.get("snapshots_analyses", 0),
        "trades_ouverts": summary.get("trades_ouverts", 0),
        "trades_ignores": summary.get("trades_ignores", 0),
        "dry_run": summary.get("dry_run", False),
        "details": summary.get("details", []),
    }
    try:
        with report_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        logger.debug("Rapport écrit dans %s", report_path)
    except OSError as e:
        logger.warning("Impossible d'écrire le rapport %s : %s", report_path, e)


# ── Passe unique ────────────────────────────────────────────
def run_pass(
    limit: int = DEFAULT_SNAPSHOT_LIMIT,
    dry_run: bool = False,
    db_path: Path | str | None = None,
    report_path: Path | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Une passe du paper-trade loop.

    Délègue à v9_paper_trade_run.run() puis écrit le rapport.
    Retourne le résumé structuré.
    """
    log = logger or _setup_logging()
    log.info(
        "Passe paper-trade: limit=%d, dry_run=%s, db=%s",
        limit, dry_run, db_path or DB_PATH,
    )

    summary = ptr.run(limit=limit, dry_run=dry_run, db_path=db_path)

    log.info(
        "Résultat: %d snapshots, %d trades ouverts, %d ignorés",
        summary["snapshots_analyses"],
        summary["trades_ouverts"],
        summary["trades_ignores"],
    )

    if report_path:
        _write_report(report_path, summary, log)

    return summary


# ── Boucle ───────────────────────────────────────────────────
_stop = False


def _handle_signal(signum, frame) -> None:  # noqa: ARG001
    global _stop
    _stop = True


def run_loop(
    interval: int = DEFAULT_INTERVAL_SECONDS,
    limit: int = DEFAULT_SNAPSHOT_LIMIT,
    dry_run: bool = False,
    db_path: Path | str | None = None,
    report_path: Path | None = None,
    once: bool = False,
    logger: logging.Logger | None = None,
) -> int:
    """Boucle paper-trade.

    Args:
        interval: Secondes entre passes (mode --watch).
        limit: Nombre de snapshots par passe.
        dry_run: Si True, aucune écriture DB.
        db_path: Chemin DB personnalisé.
        report_path: Fichier rapport (optionnel).
        once: Si True, une seule passe puis exit.
        logger: Logger (créé automatiquement si None).

    Returns:
        0 si succès, 1 si erreur.
    """
    log = logger or _setup_logging()

    if not once:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
        log.info(
            "Boucle démarrée: interval=%ds, limit=%d, dry_run=%s, report=%s",
            interval, limit, dry_run, report_path or "NONE",
        )

    n_passes = 0
    while not _stop:
        try:
            summary = run_pass(
                limit=limit,
                dry_run=dry_run,
                db_path=db_path,
                report_path=report_path,
                logger=log,
            )
            n_passes += 1

            if once:
                log.info("Mode --once: terminé (%d passes)", n_passes)
                return 0

            # Backoff si rien à faire
            if summary["trades_ouverts"] == 0 and summary["snapshots_analyses"] > 0:
                sleep_s = min(interval * 2, 3600)
                log.debug("Backoff: %ds (aucun trade ouvert)", sleep_s)
            else:
                sleep_s = interval

            time.sleep(sleep_s)

        except Exception as e:  # noqa: BLE001
            log.exception("Erreur pendant la passe : %s", e)
            if once:
                return 1
            time.sleep(interval)

    log.info("Boucle arrêtée (%d passes effectuées)", n_passes)
    return 0


# ── CLI ─────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    logger = _setup_logging()
    parser = argparse.ArgumentParser(
        description="Boucle paper-trade V9 (Phase 10). "
        "Ouvre automatiquement les trades simulés via Arbiter → RiskManager → PaperTradeLogger.",
    )

    # Modes
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--once", action="store_true",
        help="Une seule passe puis exit (pour cron).",
    )
    mode.add_argument(
        "--watch", action="store_true",
        help="Boucle continue (daemon). Défaut si ni --once ni --watch.",
    )

    # Options
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL_SECONDS,
        help=f"Intervalle entre passes en secondes (défaut {DEFAULT_INTERVAL_SECONDS}). "
        "Utilisé uniquement en mode --watch.",
    )
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_SNAPSHOT_LIMIT,
        help=f"Nombre de snapshots à traiter par passe (défaut {DEFAULT_SNAPSHOT_LIMIT}).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Affiche sans écrire en DB (paper_trades intact).",
    )
    parser.add_argument(
        "--db-path", type=Path, default=None,
        help="Chemin DB personnalisé (défaut: data/v9_forces.db).",
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help=f"Fichier rapport (défaut: {DEFAULT_REPORT_PATH}). "
        "Chaque passe ajoute une ligne JSON.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Sortie JSON du résumé (avec --once uniquement).",
    )

    args = parser.parse_args(argv)

    # Défaut : --watch si aucun mode explicite
    is_watch = args.watch or not args.once

    if args.once and args.json:
        # Mode JSON : une seule passe, sortie structurée
        summary = run_pass(
            limit=args.limit,
            dry_run=args.dry_run,
            db_path=args.db_path,
            report_path=args.report,
            logger=logger,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        return 0

    return run_loop(
        interval=args.interval,
        limit=args.limit,
        dry_run=args.dry_run,
        db_path=args.db_path,
        report_path=args.report,
        once=args.once,
        logger=logger,
    )


if __name__ == "__main__":
    sys.exit(main())
