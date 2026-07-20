#!/usr/bin/env python3
"""_resolve_pending.py — Helper fail-safe de résolution des décisions en attente.

Contexte (incident 2026-07-20 13h55 UTC) :
Le daemon `v9_resolve_decision_auto_daemon.py` n'était PAS schedulé en cron Windows.
Conséquence : ~70k décisions `preparer_entree` non résolues, ce qui bloquait
`TradeEngine.close_open_trades()` (filtre `d.is_win IS NOT NULL` ligne 862) →
8 paper_trades ouverts depuis 10:50 UTC, jamais fermés.

Doctrine :
- Additif (R2) : helper séparé, n'altère pas v9_resolve_decision_auto.run()
- Défensif (R6) : toute erreur est loggée, ne lève JAMAIS à l'appelant
- Zéro LLM (R18) : pure logique de résolution prix-based
- Backup MD5 obligatoire avant apply (cohérent avec le CLI)

Usage :
    from scripts._resolve_pending import resolve_pending
    result = resolve_pending(limit=50, logger=logger)
    # → {"applied": 12, "skipped": 0, "errors": 0, "dry_run": False}
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT_DIR / "backups" / "resolve_pending_auto"

DEFAULT_LIMIT = 50  # Sécurité : évite de bloquer le cron si gros backlog
DEFAULT_HORIZON_HOURS = 4.0


def _ensure_backup_md5(db_path: Path, logger: logging.Logger) -> Path | None:
    """Crée un backup MD5 de la DB si pas déjà fait aujourd'hui.

    Stratégie : 1 backup/jour suffixé date UTC. Réutilise si déjà présent.
    Retourne le chemin du dossier backup, ou None si échec (non-bloquant).
    """
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        marker = BACKUP_DIR / f"md5_{date_str}.txt"
        if marker.exists():
            logger.debug("Backup MD5 du jour déjà présent : %s", marker)
            return BACKUP_DIR
        # Calcule MD5 de la DB prod
        h = hashlib.md5()
        with open(db_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        marker.write_text(
            f"{h.hexdigest()} *{db_path.name}\n",
            encoding="utf-8",
        )
        logger.info("Backup MD5 capturé : %s (%s)", marker, h.hexdigest()[:12])
        return BACKUP_DIR
    except Exception as exc:  # noqa: BLE001
        logger.warning("Backup MD5 impossible (best-effort) : %s", exc)
        return None


def _connect(db_path: Path) -> sqlite3.Connection:
    from scripts.v9_resolve_decision_auto import _connect as _ra_connect
    return _ra_connect(db_path)


def resolve_pending(
    db_path: Path | None = None,
    limit: int = DEFAULT_LIMIT,
    horizon_hours: float = DEFAULT_HORIZON_HOURS,
    min_age_minutes: int = 30,  # pas de résolution sur décisions trop fraîches (R6)
    logger: logging.Logger | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Résout les décisions `preparer_entree` en attente.

    Args:
        db_path: chemin DB (défaut : config.DB_PATH)
        limit: max de décisions à tenter (sécurité)
        horizon_hours: fenêtre d'observation prix futurs
        min_age_minutes: ne pas résoudre les décisions de moins de N minutes
        logger: logger pour traçabilité
        dry_run: si True, calcule sans écrire

    Returns:
        dict {applied, skipped, errors, dry_run, eligible}
    """
    from core.v9.config import DB_PATH
    from scripts import v9_resolve_decision_auto as res_auto

    if db_path is None:
        db_path = DB_PATH
    if logger is None:
        logger = logging.getLogger("v9.resolve_pending")

    result = {
        "applied": 0,
        "skipped": 0,
        "errors": 0,
        "eligible": 0,
        "dry_run": dry_run,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # 1. Backup MD5 (sauf dry_run)
        backup = None
        if not dry_run:
            backup = _ensure_backup_md5(db_path, logger)

        # 2. Filtrer décisions éligibles (age >= min_age_minutes, is_win IS NULL)
        conn = _connect(db_path)
        try:
            from datetime import timedelta
            cutoff = (
                datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)
            ).isoformat()
            rows = conn.execute(
                "SELECT decision_id, timestamp, symbol, timeframe, direction, "
                "       snapshot_id, confiance "
                "FROM decisions "
                "WHERE action='preparer_entree' AND is_win IS NULL "
                "AND timestamp IS NOT NULL AND timestamp < ? "
                f"ORDER BY timestamp ASC LIMIT {int(limit)}",
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()

        result["eligible"] = len(rows)
        if not rows:
            logger.debug("resolve_pending: 0 décision éligible")
            return result

        # 3. Résoudre via le module auto
        skip_sessions = [
            s.strip()
            for s in res_auto.DEFAULT_SKIP_SESSIONS.split(",")
            if s.strip()
        ]
        conn = _connect(db_path)
        try:
            resolutions: list[dict] = []
            for dec in rows:
                try:
                    r = res_auto.resolve_one(
                        conn, dec,
                        horizon_hours=horizon_hours,
                        skip_no_future=True,
                        skip_sessions=skip_sessions,
                    )
                    resolutions.append(r)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("resolve_one fail on %s: %s",
                                 dec["decision_id"], exc)
                    result["errors"] += 1
            to_apply = [r for r in resolutions if r["resolved"]]
            result["skipped"] = sum(1 for r in resolutions if not r["resolved"])

            # 4. Apply (sauf dry_run OU backup KO)
            if not dry_run and backup is not None and to_apply:
                applied = res_auto.apply_resolutions(
                    conn, to_apply, db_path=db_path,
                )
                result["applied"] = applied
            elif to_apply and backup is None and not dry_run:
                logger.warning(
                    "resolve_pending: %d résolutions calculées mais "
                    "backup MD5 KO — skip apply (sécurité).",
                    len(to_apply),
                )
        finally:
            conn.close()

        logger.info(
            "resolve_pending: eligible=%d applied=%d skipped=%d errors=%d",
            result["eligible"], result["applied"],
            result["skipped"], result["errors"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("resolve_pending exception: %s", exc)
        result["errors"] += 1

    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    r = resolve_pending(limit=int(sys.argv[1]) if len(sys.argv) > 1 else 50)
    print(r)
