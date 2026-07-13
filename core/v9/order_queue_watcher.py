"""order_queue_watcher.py — ORDER-BRIDGE, volet lecteur V9 (2026-07-13).

Complète `core/v9/order_executor.py` (Brief Q5) : celui-ci dépose des
commandes JSON dans `data/order_queue/` pour lecture par l'EA MT4 (action
opérateur distincte, hors périmètre). Ce module ne parle JAMAIS à MT4 — il
observe uniquement le système de fichiers côté V9 pour classer et purger
les commandes déjà déposées, afin que le répertoire ne grossisse pas sans
limite.

Convention de consommation (côté EA, documentée mais non modifiée ici) :
l'EA, après avoir traité `{command_id}.json`, dépose un fichier compagnon
`{command_id}.result.json` (contenu libre, ex: `{"status": "filled"}` ou
`{"status": "rejected", "reason": "..."}`). Tant qu'aucun compagnon
n'existe, la commande est réputée `pending`. Passé `EXPIRY_HOURS` sans
compagnon, elle est réputée `expired` (EA injoignable, terminal fermé,
etc.) — jamais interprété comme un échec silencieux d'ordre.

Aucune commande n'est jamais supprimée : `purge_queue(apply=True)` les
déplace vers `archive_dir` (défaut `data/order_queue/archive/`), traçabilité
financière oblige. Dry-run par défaut, même convention que
`scripts/v9_resolve_decision_auto.py`.

R18 préservé : aucun appel réseau, uniquement du filesystem local.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from core.v9.order_executor import ORDER_QUEUE_DIR

EXPIRY_HOURS_DEFAULT = 24.0

QueueStatus = Literal["pending", "consumed", "expired"]


@dataclass
class QueueEntry:
    command_id: str
    status: QueueStatus
    command_file: Path
    result_file: Path | None = None
    result: dict[str, Any] | None = None
    age_hours: float = 0.0


def _result_file_for(command_file: Path) -> Path:
    return command_file.with_suffix("").with_suffix(".result.json")


def _age_hours(path: Path, *, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (now - mtime).total_seconds() / 3600.0


def scan_queue(
    queue_dir: Path | None = None,
    *,
    expiry_hours: float = EXPIRY_HOURS_DEFAULT,
    now: datetime | None = None,
) -> list[QueueEntry]:
    """Classe chaque commande déposée en pending / consumed / expired.

    Ne modifie rien — lecture seule. `queue_dir` absent (jamais démarré par
    order_executor) => liste vide, pas une erreur.
    """
    queue_dir = queue_dir or ORDER_QUEUE_DIR
    if not queue_dir.is_dir():
        return []

    entries: list[QueueEntry] = []
    for command_file in sorted(queue_dir.glob("*.json")):
        if command_file.name.endswith(".result.json"):
            continue
        command_id = command_file.stem
        result_file = _result_file_for(command_file)
        age = _age_hours(command_file, now=now)

        if result_file.exists():
            result = json.loads(result_file.read_text(encoding="utf-8"))
            entries.append(QueueEntry(
                command_id=command_id,
                status="consumed",
                command_file=command_file,
                result_file=result_file,
                result=result,
                age_hours=age,
            ))
        elif age >= expiry_hours:
            entries.append(QueueEntry(
                command_id=command_id,
                status="expired",
                command_file=command_file,
                age_hours=age,
            ))
        else:
            entries.append(QueueEntry(
                command_id=command_id,
                status="pending",
                command_file=command_file,
                age_hours=age,
            ))
    return entries


def purge_queue(
    queue_dir: Path | None = None,
    *,
    archive_dir: Path | None = None,
    expiry_hours: float = EXPIRY_HOURS_DEFAULT,
    apply: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Archive les commandes `consumed`/`expired`. Ne touche jamais `pending`.

    Dry-run par défaut (`apply=False`) : ne déplace rien, retourne le
    rapport que produirait l'application. Jamais de suppression — les
    commandes sont déplacées vers `archive_dir`, jamais effacées
    (traçabilité financière).
    """
    queue_dir = queue_dir or ORDER_QUEUE_DIR
    archive_dir = archive_dir or (queue_dir / "archive")
    entries = scan_queue(queue_dir, expiry_hours=expiry_hours, now=now)

    to_archive = [e for e in entries if e.status in ("consumed", "expired")]
    report: dict[str, Any] = {
        "queue_dir": str(queue_dir),
        "archive_dir": str(archive_dir),
        "applied": apply,
        "pending": sum(1 for e in entries if e.status == "pending"),
        "consumed_archived": sum(1 for e in to_archive if e.status == "consumed"),
        "expired_archived": sum(1 for e in to_archive if e.status == "expired"),
        "archived_command_ids": [e.command_id for e in to_archive],
    }

    if apply and to_archive:
        archive_dir.mkdir(parents=True, exist_ok=True)
        for entry in to_archive:
            shutil.move(str(entry.command_file), str(archive_dir / entry.command_file.name))
            if entry.result_file is not None and entry.result_file.exists():
                shutil.move(str(entry.result_file), str(archive_dir / entry.result_file.name))

    return report
