#!/usr/bin/env python3
"""v9_resolve_decision_auto_daemon.py — Boucle auto WIN/LOSS (Phase 9.10).

Tourne en arrière-plan et résout périodiquement les décisions
`action='preparer_entree'` non résolues dont le timestamp est antérieur
à un seuil (défaut 24h, le temps que la fenêtre d'observation 4h soit
complète). Délègue toute la logique à `v9_resolve_decision_auto.run()`.

Doctrine :
- Aucun LLM dans la boucle (R8, R18 préservées).
- Idempotent : un daemon qui résout 2× la même décision = no-op (UPDATE
  WHERE is_win IS NULL côté apply_resolutions).
- Intervalle par défaut 5 min (configurable). Cible la commande de
  pipeline à intervalle 5min typique (cf. cron `*/5`).
- Backoff si 0 résolutions (évite spin CPU).
- Log structuré dans logs/v9_resolve_daemon.log.

Usage :
    # Daemon en avant-plan (Ctrl-C pour arrêter)
    python scripts/v9_resolve_decision_auto_daemon.py

    # Custom intervalle + âge minimum
    python scripts/v9_resolve_decision_auto_daemon.py \\
        --interval 60 --min-age-hours 12

    # Daemon une seule fois (utile en cron)
    python scripts/v9_resolve_decision_auto_daemon.py --once

    # Backup MD5 + dry-run avant de lancer en prod
    python scripts/v9_resolve_decision_auto_daemon.py --once --backup backups/2026-07-08/

    # JSON pour intégration orchestrator
    python scripts/v9_resolve_decision_auto_daemon.py --once --json

Sécurité :
- Backup MD5 obligatoire (sauf --dry-run explicite).
- Refuse de tourner si la DB n'existe pas ou si le port capture est
  inactif (suggère que le pipeline est down → risque d'incohérence).
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import socket
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.v9.config import DB_PATH  # noqa: E402
from scripts import v9_resolve_decision_auto as res_auto  # noqa: E402

CAPTURE_PORT = 31685
DEFAULT_INTERVAL_SECONDS = 300  # 5 min
DEFAULT_MIN_AGE_HOURS = 24
LOG_PATH = ROOT_DIR / "logs" / "v9_resolve_daemon.log"


# ── Logging ────────────────────────────────────────────────────
def _setup_logging() -> logging.Logger:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logger = logging.getLogger("v9_resolve_daemon")
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


# ── Helpers ────────────────────────────────────────────────────
def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Teste si le port de capture_server est ouvert (pipeline live actif)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_pass(
    db_path: Path,
    min_age_hours: float,
    backup: Path | None,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Une passe de résolution. Retourne un dict avec les compteurs."""
    # 1. Filtrer les décisions éligibles (timestamp < now - min_age)
    cutoff = (datetime.now(timezone.utc)
              - __import__("datetime").timedelta(hours=min_age_hours))
    cutoff_iso = cutoff.isoformat()
    conn = res_auto._connect(db_path)
    try:
        rows = conn.execute(
            "SELECT decision_id, timestamp, symbol, timeframe, direction, "
            "       snapshot_id, confiance "
            "FROM decisions "
            "WHERE action='preparer_entree' AND is_win IS NULL "
            "AND timestamp IS NOT NULL AND timestamp < ?",
            (cutoff_iso,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return {
            "timestamp_utc": _now_iso(),
            "n_eligible": 0,
            "n_resolved": 0,
            "n_no_future": 0,
            "n_skipped": 0,
        }

    # 2. Résoudre via le module auto (réutilise toute la logique)
    conn = res_auto._connect(db_path)
    try:
        resolutions = []
        for dec in rows:
            r = res_auto.resolve_one(
                conn, dec,
                horizon_hours=res_auto.DEFAULT_HORIZON_HOURS,
                skip_no_future=True,
            )
            resolutions.append(r)
        # Apply
        to_apply = [r for r in resolutions if r["resolved"]]
        if to_apply and backup is not None:
            # Mode --apply : transaction
            applied = res_auto.apply_resolutions(conn, to_apply)
        elif to_apply and backup is None:
            # Mode dry-run
            applied = 0
            logger.info("dry-run : %d résolutions NON appliquées (backup manquant)", len(to_apply))
        else:
            applied = 0
    finally:
        conn.close()

    return {
        "timestamp_utc": _now_iso(),
        "n_eligible": len(rows),
        "n_resolved": applied,
        "n_no_future": sum(1 for r in resolutions if not r["resolved"]),
        "n_skipped": sum(1 for r in resolutions if r["resolved"] and r["n_future_prices"] == 0),
    }


# ── Daemon loop ───────────────────────────────────────────────
_stop = False


def _handle_signal(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def run_daemon(
    interval: int,
    min_age_hours: float,
    backup: Path | None,
    require_capture: bool,
    once: bool,
    logger: logging.Logger,
) -> int:
    """Boucle infinie (ou une seule passe si --once)."""
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    logger.info(
        "Daemon start: interval=%ds, min_age=%fh, backup=%s, once=%s",
        interval, min_age_hours, backup or "NONE", once,
    )
    n_passes = 0
    while not _stop:
        # Garde-fou : si pipeline down et require_capture, on attend
        if require_capture and not _port_in_use(CAPTURE_PORT):
            logger.warning(
                "Port %d inactif, daemon en attente (--no-require-capture pour désactiver)",
                CAPTURE_PORT,
            )
            time.sleep(interval)
            continue

        try:
            result = _resolve_pass(DB_PATH, min_age_hours, backup, logger)
            n_passes += 1
            logger.info(
                "Passe #%d: eligible=%d, resolved=%d, no_future=%d",
                n_passes, result["n_eligible"], result["n_resolved"],
                result["n_no_future"],
            )
            if once:
                return 0
            # Backoff si rien à faire : on double l'intervalle (max 1h)
            if result["n_resolved"] == 0 and result["n_eligible"] > 0:
                sleep_s = min(interval * 2, 3600)
            elif result["n_eligible"] == 0:
                sleep_s = interval  # rien à faire, on attend
            else:
                sleep_s = interval
            time.sleep(sleep_s)
        except Exception as e:  # noqa: BLE001
            logger.exception("Erreur pendant la passe : %s", e)
            if once:
                return 1
            time.sleep(interval)
    logger.info("Daemon stop (signal reçu, %d passes effectuées)", n_passes)
    return 0


# ── CLI ────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    logger = _setup_logging()
    parser = argparse.ArgumentParser(
        description="Daemon WIN/LOSS auto (Phase 9.10). Boucle infinie sauf --once."
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL_SECONDS,
        help=f"Intervalle entre passes en secondes (défaut {DEFAULT_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--min-age-hours", type=float, default=DEFAULT_MIN_AGE_HOURS,
        help=f"Âge minimum décision avant résolution (défaut {DEFAULT_MIN_AGE_HOURS}h)",
    )
    parser.add_argument(
        "--backup", type=Path, default=None,
        help="Dossier backup MD5 (obligatoire pour --apply, ignoré en --dry-run)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Calcule les résolutions mais ne les applique pas (backup non requis)",
    )
    parser.add_argument(
        "--no-require-capture", action="store_true",
        help="Ne pas exiger que le port capture_server soit actif",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Une seule passe puis exit (utile en cron)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Sortie JSON de la passe (avec --once)",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not args.backup:
        print(
            "ERREUR: backup MD5 requis (ou --dry-run). "
            "Voir --help.",
            file=sys.stderr,
        )
        return 2

    if args.once and args.json:
        # Mode JSON : une seule passe, sortie structurée
        result = _resolve_pass(DB_PATH, args.min_age_hours, args.backup, logger)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    return run_daemon(
        interval=args.interval,
        min_age_hours=args.min_age_hours,
        backup=args.backup,
        require_capture=not args.no_require_capture,
        once=args.once,
        logger=logger,
    )


if __name__ == "__main__":
    sys.exit(main())
